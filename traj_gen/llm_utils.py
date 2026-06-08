import traceback
import base64
import json
import requests
import time
import logging
import os
import re
from io import BytesIO

from PIL import Image


class CredentialException(Exception):
    pass


def _model_name(args):
    return os.getenv("MODEL_NAME", args.deployment)


def _convert_claude_compatible_content(content):
    if isinstance(content, str):
        return content

    converted = []
    has_text = False
    for block in content:
        if block.get("type") != "image_url":
            if block.get("type") == "text" and block.get("text", "").strip():
                has_text = True
            converted.append(block)
            continue

        image_url = block.get("image_url", {})
        if isinstance(image_url, dict):
            image_url = image_url.get("url", "")

        match = re.match(r"data:(.*?);base64,(.*)", image_url)
        if not match:
            converted.append(block)
            continue
        media_type = match.group(1)
        image_data = match.group(2)

        converted.append(
            {
                "type": "image",
                "source": {
                    "type": "base64",
                    "media_type": media_type,
                    "data": image_data,
                },
            }
        )

    has_image = any(block.get("type") == "image" for block in converted)
    if has_image and not has_text:
        converted.insert(0, {"type": "text", "text": "Please analyze the provided image(s)."})

    return converted


def _convert_claude_compatible_messages(messages):
    return [
        {
            **message,
            "content": _convert_claude_compatible_content(message["content"]),
        }
        for message in messages
    ]


def _limit_claude_compatible_text(messages, max_chars=60000):
    remaining = max_chars
    limited_messages = []

    for message in messages:
        content = message["content"]
        if isinstance(content, str):
            limited = content[:remaining]
            remaining -= len(limited)
            limited_messages.append({**message, "content": limited})
            continue

        limited_content = []
        for block in content:
            if block.get("type") != "text":
                limited_content.append(block)
                continue

            text = block.get("text", "")
            if remaining <= 0:
                text = "\n[Text omitted because Claude-compatible request text limit was reached.]"
            else:
                text = text[:remaining]
                remaining -= len(text)
            limited_content.append({**block, "text": text})

        limited_messages.append({**message, "content": limited_content})

    return limited_messages


def _call_openai_compatible(args, messages, max_tokens, temperature):
    api_key = (
        os.getenv("DASHSCOPE_API_KEY")
        or os.getenv("OPENAI_API_KEY")
        or os.getenv("API_KEY")
    )
    if not api_key:
        raise CredentialException(
            "DASHSCOPE_API_KEY, OPENAI_API_KEY, or API_KEY is required"
        )

    base_url = os.getenv("API_BASE_URL", "https://api.openai.com/v1").rstrip("/")
    model = _model_name(args)
    if model.startswith("claude"):
        max_chars = int(os.getenv("CLAUDE_COMPAT_MAX_TEXT_CHARS", "60000"))
        messages = _limit_claude_compatible_text(messages, max_chars=max_chars)
        messages = _convert_claude_compatible_messages(messages)

    headers = {"Content-Type": "application/json", "Authorization": f"Bearer {api_key}"}
    payload = {
        "model": model,
        "messages": messages,
        "max_tokens": max_tokens,
        "temperature": temperature,
    }

    response = requests.post(
        f"{base_url}/chat/completions", headers=headers, json=payload, timeout=120
    )
    if response.status_code >= 400:
        logging.info("API error response: {}".format(response.text[:2000]))
    response.raise_for_status()
    data = response.json()
    _log_usage(args, data, model)
    return data["choices"][0]["message"]["content"]


def _log_usage(args, data, model):
    usage = data.get("usage")
    if not usage:
        return

    log_dir = getattr(args, "model_dir", None)
    if not log_dir:
        return

    try:
        os.makedirs(log_dir, exist_ok=True)
        record = {
            "ts": time.time(),
            "model": model,
            "usage": usage,
            "id": data.get("id"),
            "finish_reason": (data.get("choices") or [{}])[0].get("finish_reason"),
        }
        with open(os.path.join(log_dir, "llm_usage.jsonl"), "a", encoding="utf-8") as f:
            f.write(json.dumps(record, ensure_ascii=True) + "\n")
    except Exception:
        logging.info("failed to write llm usage log")
        logging.info(traceback.format_exc())


def call_gpt4v(args, messages, max_tokens=2048, temperature=0.01):
    max_num_trial = 3
    num_trial = 0
    call_api_success = True

    while num_trial < max_num_trial:
        try:
            ans_1st_pass = _call_openai_compatible(
                args, messages, max_tokens, temperature
            )
            break
        except Exception:
            logging.info("retry call gptv {}".format(num_trial))
            logging.info(traceback.format_exc())
            num_trial += 1
            ans_1st_pass = ""
            time.sleep(10)

    if num_trial == max_num_trial:
        call_api_success = False

    return ans_1st_pass, call_api_success
