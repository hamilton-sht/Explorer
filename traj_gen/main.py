import os
import random
import shutil
import traceback
from .task_proposal_agent import TaskProposalAgent
from .task_refiner_agent import TaskRefinerAgent
from .task_summarization_flow import TaskSummarizationAgent
import json
from .trajectory_verifier import TrajectoryVerifierAgent
from .captcha_detection_agent import CaptchaDetectionAgent
from PIL import Image, ImageDraw, ImageFont
import argparse
import logging
import io
from tqdm import tqdm
import requests
from bs4 import BeautifulSoup
from .browser_env import ScriptBrowserEnv
from .processors import ImageObservationProcessor
import re
from .actions import ActionTypes, create_id_based_action, _id2key
import numpy as np

logger = logging.getLogger("__main__")

TOOL_CALL_START = "<|tool_call>"
TOOL_CALL_END = "<tool_call|>"
COORDINATE_SPACE = "image_pixel"


def _decode_action_text(action):
    return "".join(_id2key[i] for i in action.get("text", []))


def verifier_status(verifier_response):
    match = re.search(r'Status[*\s]*[:：][*\s]*["“]?(success|failure)', verifier_response or "", re.I)
    if not match:
        return "unknown"
    return match.group(1).lower()


def action_to_protocol(action, bounding_box_coord, viewport_size):
    action_type = action["action_type"]
    center = None
    if bounding_box_coord is not None:
        center = [
            float(bounding_box_coord["x"]),
            float(bounding_box_coord["y"]),
        ]

    def point_args():
        return {"x": center[0], "y": center[1]} if center else {}

    if action_type in (ActionTypes.CLICK, ActionTypes.MOUSE_CLICK):
        point = center or [float(action["coords"][0]), float(action["coords"][1])]
        return {
            "name": "click",
            "args": {"x": point[0], "y": point[1]},
            "text": f"click({point[0]:.2f}, {point[1]:.2f})",
            "target_actions": [
                {"name": "click", "args": {"point": point}},
            ],
        }
    if action_type == ActionTypes.MOUSE_DOUBLE_CLICK:
        point = [float(action["coords"][0]), float(action["coords"][1])]
        return {
            "name": "doubleclick",
            "args": {"x": point[0], "y": point[1]},
            "text": f"doubleclick({point[0]:.2f}, {point[1]:.2f})",
            "target_actions": [{"name": "doubleclick", "args": {"point": point}}],
        }
    if action_type == ActionTypes.MOUSE_RIGHT_CLICK:
        point = [float(action["coords"][0]), float(action["coords"][1])]
        return {
            "name": "rightclick",
            "args": {"x": point[0], "y": point[1]},
            "text": f"rightclick({point[0]:.2f}, {point[1]:.2f})",
            "target_actions": [{"name": "rightclick", "args": {"point": point}}],
        }
    if action_type == ActionTypes.MOUSE_MOVE:
        point = [float(action["coords"][0]), float(action["coords"][1])]
        return {
            "name": "move",
            "args": {"x": point[0], "y": point[1]},
            "text": f"move({point[0]:.2f}, {point[1]:.2f})",
            "target_actions": [{"name": "move", "args": {"point": point}}],
        }
    if action_type in (ActionTypes.HOVER, ActionTypes.MOUSE_HOVER):
        point = center or [float(action["coords"][0]), float(action["coords"][1])]
        return {
            "name": "hover",
            "args": {"x": point[0], "y": point[1]},
            "text": f"hover({point[0]:.2f}, {point[1]:.2f})",
            "target_actions": [
                {"name": "hover", "args": {"point": point}},
            ],
        }
    if action_type in (ActionTypes.TYPE, ActionTypes.KEYBOARD_TYPE):
        text = _decode_action_text(action)
        return {
            "name": "type",
            "args": {"text": text},
            "text": f"type({json.dumps(text, ensure_ascii=False)})",
            "target_actions": [
                {"name": "type", "args": {"content": text}},
            ],
        }
    if action_type == ActionTypes.SELECT:
        text = action.get("fill_text") or _decode_action_text(action)
        return {
            "name": "select",
            "args": {"option": text},
            "text": f"select({json.dumps(text, ensure_ascii=False)})",
            "target_actions": [
                {"name": "type", "args": {"content": text}},
            ],
        }
    if action_type == ActionTypes.KEY_PRESS:
        key = action["key_comb"]
        return {
            "name": "press",
            "args": {"key": key},
            "text": f"press({json.dumps(key, ensure_ascii=False)})",
            "target_actions": [
                {"name": "press", "args": {"key": key}},
            ],
        }
    if action_type == ActionTypes.KEY_UP:
        key = action["key_comb"]
        return {
            "name": "keyup",
            "args": {"key": key},
            "text": f"keyup({json.dumps(key, ensure_ascii=False)})",
            "target_actions": [{"name": "keyup", "args": {"key": key}}],
        }
    if action_type == ActionTypes.DRAG:
        start = [float(action["start_coords"][0]), float(action["start_coords"][1])]
        end = [float(action["end_coords"][0]), float(action["end_coords"][1])]
        return {
            "name": "drag",
            "args": {"x1": start[0], "y1": start[1], "x2": end[0], "y2": end[1]},
            "text": f"drag({start[0]:.2f}, {start[1]:.2f}, {end[0]:.2f}, {end[1]:.2f})",
            "target_actions": [{"name": "drag", "args": {"start": start, "end": end}}],
        }
    if action_type == ActionTypes.SCROLL:
        direction = "up" if "up" in action["direction"] else "down"
        amount = float(action.get("amount", 600))
        return {
            "name": "scroll",
            "args": {"direction": direction, "amount": amount},
            "text": f"scroll({json.dumps(direction)}, {amount:g})",
            "target_actions": [
                {"name": "scroll", "args": {"direction": direction, "amount": amount}},
            ],
        }
    if action_type == ActionTypes.GO_BACK:
        return {"name": "go_back", "args": {}, "text": "go_back()", "target_actions": [{"name": "go_back", "args": {}}]}
    if action_type == ActionTypes.GO_FORWARD:
        return {"name": "go_forward", "args": {}, "text": "go_forward()", "target_actions": [{"name": "go_forward", "args": {}}]}
    if action_type == ActionTypes.GOTO_URL:
        url = action["url"]
        return {
            "name": "navigate",
            "args": {"url": url},
            "text": f"navigate({json.dumps(url, ensure_ascii=False)})",
            "target_actions": [
                {"name": "navigate", "args": {"url": url}},
            ],
        }
    if action_type == ActionTypes.STOP:
        answer = action.get("answer", "")
        # Doc spec: `answer("...")` for completed task; `stop()` for unsolvable task
        # (login wall, CAPTCHA, content doesn't exist on this site).
        if answer:
            return {
                "name": "answer",
                "args": {"answer": answer},
                "text": f"answer({json.dumps(answer, ensure_ascii=False)})",
                "target_actions": [{"name": "answer", "args": {"content": answer}}],
            }
        return {
            "name": "stop",
            "args": {},
            "text": "stop()",
            "target_actions": [{"name": "stop", "args": {}}],
        }
    if action_type == ActionTypes.ZOOM_REGION:
        box = [float(v) for v in action["box"]]
        return {
            "name": "zoom_region",
            "args": {"x": box[0], "y": box[1], "w": box[2], "h": box[3]},
            "text": f"zoom_region({box[0]:.2f}, {box[1]:.2f}, {box[2]:.2f}, {box[3]:.2f})",
            "target_actions": [{"name": "zoom_region", "args": {"box": box}}],
        }
    if action_type == ActionTypes.ZOOM_OUT:
        return {"name": "zoom_out", "args": {}, "text": "zoom_out()", "target_actions": [{"name": "zoom_out", "args": {}}]}
    if action_type == ActionTypes.NONE:
        return {"name": "wait", "args": {}, "text": "wait()", "target_actions": [{"name": "wait", "args": {}}]}

    return {
        "name": "unsupported",
        "args": {"native_action_type": str(ActionTypes(action_type))},
        "text": "wait()",
        "target_actions": [{"name": "wait", "args": {}}],
    }


def make_step_record(
    trajectory_id,
    step,
    current_url,
    next_url,
    viewport_size,
    action_nl,
    grounded_action,
    parsed_action,
    protocol_action,
    execution_success,
):
    current_obs_id = f"{trajectory_id}_{step:03d}"
    next_obs_id = f"{trajectory_id}_{step + 1:03d}"
    cot = action_nl or ""
    tool_text = protocol_action["text"] if protocol_action else "wait()"
    return {
        "t": step,
        "x_t": {"image": f"screenshot_{step}.png"},
        "env_meta_current": {
            "observation_id": current_obs_id,
            "url": current_url,
            "viewport": viewport_size,
            "screen_size": viewport_size,
            "coordinate_space": COORDINATE_SPACE,
        },
        "CoT": cot,
        "w_t": f"{cot}{TOOL_CALL_START}{tool_text}{TOOL_CALL_END}",
        "tool_call_token": TOOL_CALL_END,
        "parsed_action": parsed_action,
        "raw_grounded_action": grounded_action,
        "x_next": {"image": f"screenshot_{step + 1}.png"},
        "env_meta_next": {
            "observation_id": next_obs_id,
            "url": next_url,
            "viewport": viewport_size,
            "screen_size": viewport_size,
            "coordinate_space": COORDINATE_SPACE,
            "execution_success": bool(execution_success),
        },
    }


def safe_screenshot(page, path, fallback_path=None, timeout=15000, full_page=False):
    """Take a screenshot with timeout; if it fails, copy a fallback file if provided.

    Returns True if a fresh screenshot was saved, False if we degraded to fallback or
    no file was produced.
    """
    try:
        page.screenshot(path=path, timeout=timeout, full_page=full_page)
        return True
    except Exception as e:
        logging.warning(f"screenshot failed for {path}: {e}")
        if fallback_path and os.path.exists(fallback_path) and fallback_path != path:
            try:
                shutil.copy(fallback_path, path)
                logging.info(f"degraded: copied {fallback_path} -> {path}")
            except Exception as copy_err:
                logging.warning(f"fallback copy failed: {copy_err}")
        return False


def save_action_som(raw_screenshot_path, output_path, bounding_box_coord, label=None, viewport_size=None):
    img = Image.open(raw_screenshot_path).convert("RGB")

    # If raw screenshot is full-page (taller than viewport), crop to viewport so
    # the action SOM annotation stays viewport-sized and aligns with viewport-relative
    # bounding box coordinates produced by SOM extraction.
    if viewport_size is not None:
        vp_w = int(viewport_size.get("width", img.width))
        vp_h = int(viewport_size.get("height", img.height))
        if img.height > vp_h or img.width > vp_w:
            img = img.crop((0, 0, min(vp_w, img.width), min(vp_h, img.height)))

    if bounding_box_coord is None:
        img.save(output_path)
        return

    center_x = bounding_box_coord["x"]
    center_y = bounding_box_coord["y"]
    width = bounding_box_coord["width"]
    height = bounding_box_coord["height"]

    left = max(0, center_x - width / 2)
    top = max(0, center_y - height / 2)
    right = min(img.width - 1, center_x + width / 2)
    bottom = min(img.height - 1, center_y + height / 2)
    if right < left:
        left, right = right, left
    if bottom < top:
        top, bottom = bottom, top

    draw = ImageDraw.Draw(img)
    color = (255, 0, 0)
    draw.rectangle([left, top, right, bottom], outline=color, width=4)

    if label:
        font = ImageFont.load_default()
        text = str(label)
        text_bbox = draw.textbbox((0, 0), text, font=font)
        text_width = text_bbox[2] - text_bbox[0]
        text_height = text_bbox[3] - text_bbox[1]
        label_left = int(left)
        label_top = max(0, int(top) - text_height - 8)
        draw.rectangle(
            [
                label_left,
                label_top,
                label_left + text_width + 8,
                label_top + text_height + 6,
            ],
            fill=color,
        )
        draw.text(
            (label_left + 4, label_top + 3),
            text,
            fill=(255, 255, 255),
            font=font,
        )

    img.save(output_path)


def save_click_marker(raw_screenshot_path, output_path, point, viewport_size=None):
    img = Image.open(raw_screenshot_path).convert("RGB")

    if viewport_size is not None:
        vp_w = int(viewport_size.get("width", img.width))
        vp_h = int(viewport_size.get("height", img.height))
        if img.height > vp_h or img.width > vp_w:
            img = img.crop((0, 0, min(vp_w, img.width), min(vp_h, img.height)))

    if point is None:
        img.save(output_path)
        return

    x, y = float(point[0]), float(point[1])
    radius = max(8, min(img.width, img.height) // 100)
    left = max(0, x - radius)
    top = max(0, y - radius)
    right = min(img.width - 1, x + radius)
    bottom = min(img.height - 1, y + radius)

    draw = ImageDraw.Draw(img)
    draw.ellipse([left, top, right, bottom], fill=(255, 0, 0), outline=(255, 255, 255), width=3)
    img.save(output_path)


def select_refiner_image_history(image_history, max_images):
    if max_images <= 0 or not image_history:
        return []

    selected = [image_history[0]]
    for image_path in image_history[-(max_images - 1) :]:
        if image_path not in selected:
            selected.append(image_path)
    return selected


def select_summarization_screenshots(screenshot_history, max_images):
    if max_images <= 0 or not screenshot_history:
        return []
    if len(screenshot_history) <= max_images:
        return list(screenshot_history)

    last_count = min(3, max_images - 1)
    middle_count = max_images - 1 - last_count
    last_images = screenshot_history[-last_count:]
    middle_pool = screenshot_history[1:-last_count] if last_count else screenshot_history[1:]

    selected = [screenshot_history[0]]
    if middle_count > 0 and middle_pool:
        if len(middle_pool) <= middle_count:
            selected.extend(middle_pool)
        else:
            for i in range(middle_count):
                idx = round(i * (len(middle_pool) - 1) / (middle_count - 1)) if middle_count > 1 else len(middle_pool) // 2
                selected.append(middle_pool[idx])

    selected.extend(last_images)

    deduped = []
    for image_path in selected:
        if image_path not in deduped:
            deduped.append(image_path)
    return deduped[:max_images]


class Explorer:
    def __init__(self, args):
        self.args = args

        self.viewport_size = {
            "width": args.viewport_width,
            "height": args.viewport_height,
        }
        self.image_observation_type = "image_som"

        self.browser_env = ScriptBrowserEnv(
            args, browser_type="chrome", viewport_size=self.viewport_size
        )

        self.init_setup_error = False
        try:
            self.browser_env.setup(args.init_url)
        except:
            self.init_setup_error = True
            logging.info("Error in setting up the environment. Exiting...")
            logging.info(traceback.format_exc())
            return
        self.image_processor = ImageObservationProcessor(
            args, self.image_observation_type, self.viewport_size
        )

        self.task_proposal_agent = TaskProposalAgent(
            args, self.browser_env, self.image_processor
        )
        self.task_refiner_agent = TaskRefinerAgent(
            args, self.browser_env, self.image_processor
        )
        self.summarization_agent = TaskSummarizationAgent(
            args, self.browser_env, self.image_processor
        )
        self.verifier_agent = TrajectoryVerifierAgent(args)

        self.captcha_detection_agent = CaptchaDetectionAgent(args)
        self.zoom_region_box = None

    def apply_zoom_to_observation(self, raw_image_obs):
        if self.zoom_region_box is None:
            return raw_image_obs

        img = Image.fromarray(raw_image_obs)
        x, y, w, h = self.zoom_region_box
        left = max(0, int(round(x)))
        top = max(0, int(round(y)))
        right = min(img.width, int(round(x + w)))
        bottom = min(img.height, int(round(y + h)))
        if right <= left or bottom <= top:
            logging.warning("invalid zoom_region_box=%s; using full screenshot", self.zoom_region_box)
            self.zoom_region_box = None
            return raw_image_obs

        cropped = img.crop((left, top, right, bottom))
        resized = cropped.resize(
            (self.viewport_size["width"], self.viewport_size["height"]),
            Image.Resampling.LANCZOS,
        )
        return np.array(resized.convert("RGB"))

    def update_zoom_state(self, parsed_runtime_action):
        action_type = parsed_runtime_action["action_type"]
        if action_type == ActionTypes.ZOOM_REGION:
            self.zoom_region_box = [float(v) for v in parsed_runtime_action["box"]]
        elif action_type == ActionTypes.ZOOM_OUT:
            self.zoom_region_box = None

    def get_state(self):
        page = self.browser_env.page
        # CDP fallback: page.screenshot() can hang on document.fonts.ready on
        # sites with slow/blocked font CDNs. Bypass via CDP Page.captureScreenshot.
        try:
            raw_png = page.screenshot(full_page=False, timeout=15000)
        except Exception as e:
            msg = str(e).lower()
            if "fonts" not in msg and "timeout" not in msg:
                raise
            import base64 as _b64
            logging.warning(f"page.screenshot timed out in get_state ({e}); CDP fallback")
            client = getattr(page, "client", None) or page.context.new_cdp_session(page)
            result = client.send("Page.captureScreenshot", {"format": "png"})
            raw_png = _b64.b64decode(result["data"])
        raw_image_obs = np.array(Image.open(io.BytesIO(raw_png)).convert("RGB"))
        agent_image_obs = self.apply_zoom_to_observation(raw_image_obs)

        html = self.browser_env.page.content()

        return {
            "page": self.browser_env.page,
            "client": self.browser_env.page.client,
            "raw_image_obs": raw_image_obs,
            "agent_image_obs": agent_image_obs,
            "html": html,
        }

    def run(self, ex_log_dir="."):
        if self.init_setup_error:
            return [], "Error in setting up the environment", False

        task_trajectory_data = {}
        trajectory_id = os.path.basename(os.path.abspath(ex_log_dir))
        viewport_size = {
            "width": self.args.viewport_width,
            "height": self.args.viewport_height,
        }
        task_trajectory_data["trajectory_id"] = trajectory_id
        task_trajectory_data["sample_id"] = trajectory_id
        task_trajectory_data["stage"] = self.args.data_stage
        task_trajectory_data["split"] = self.args.data_split
        task_trajectory_data["quality_tier"] = self.args.quality_tier
        task_trajectory_data["data_type"] = self.args.data_type
        task_trajectory_data["source_dataset"] = self.args.source_dataset
        task_trajectory_data["benchmark_family"] = self.args.benchmark_family
        task_trajectory_data["instruction"] = None
        task_trajectory_data["resolution"] = viewport_size
        task_trajectory_data["coordinate_space"] = COORDINATE_SPACE
        task_trajectory_data["screen_size"] = viewport_size
        task_trajectory_data["protocol"] = "active_lifting_browser_v1"
        task_trajectory_data["init_url"] = self.args.init_url
        task_trajectory_data["viewport-width"] = self.args.viewport_width
        task_trajectory_data["viewport-height"] = self.args.viewport_height
        task_trajectory_data["task"] = {
            "task_id": trajectory_id,
            "feasibility": "true",
            "instruction": None,
            "start_url": self.args.init_url,
        }
        task_trajectory_data["observation_refs"] = []
        task_trajectory_data["steps"] = []

        task_trajectory_data["actions"] = []
        completed = False

        task_refinement_history = []
        action_history = []
        action_screenshot_history = []
        refiner_image_history = []
        original_task = None
        step = 0
        execution_id = 0
        refined_goal = None

        try:
            while step < self.args.max_steps and execution_id <= 2:
                action = {}
                logging.info(f"Step {step}:\n")
                if completed:
                    break
                if self.browser_env.page is not None and any(
                    self.browser_env.page.url.startswith(prefix)
                    for prefix in self.args.abort_on_url_prefix
                ):
                    logging.info(
                        "aborting trajectory because current URL starts with blocked prefix: %s",
                        self.browser_env.page.url,
                    )
                    break

                # get state of the environment
                if self.browser_env.page is not None:
                    state_attempt = 0
                    browser_env_state = None
                    while state_attempt < 3:
                        try:
                            browser_env_state = self.get_state()
                            break
                        except Exception as state_err:
                            state_attempt += 1
                            logging.warning(
                                f"get_state() failed (attempt {state_attempt}/3): {state_err}"
                            )
                            logging.info(traceback.format_exc())
                            # Wait briefly for any in-flight navigation to settle,
                            # then retry without wiping the trajectory.
                            try:
                                self.browser_env.page.wait_for_load_state(
                                    "domcontentloaded", timeout=5000
                                )
                            except Exception:
                                pass
                    if browser_env_state is None:
                        # Hard failure after 3 retries — keep what we have and stop.
                        logging.error(
                            "get_state() failed 3 times; ending trajectory with current actions intact"
                        )
                        break

                    current_url_before = browser_env_state["page"].url
                    # action['html_before'] = browser_env_state['html']
                    with open(
                        os.path.join(ex_log_dir, f"html_{step}.html"),
                        "w",
                        encoding="utf-8",
                    ) as f1:
                        f1.write(browser_env_state["html"])

                    if not self.args.no_dump_screenshots:
                        current_screenshot_path = os.path.join(
                            ex_log_dir, f"screenshot_{step}.png"
                        )
                        prev_screenshot_path = (
                            os.path.join(ex_log_dir, f"screenshot_{step - 1}.png")
                            if step > 0
                            else None
                        )
                        safe_screenshot(
                            self.browser_env.page,
                            current_screenshot_path,
                            fallback_path=prev_screenshot_path,
                        )

                        task_trajectory_data["observation_refs"].append(
                            f"screenshot_{step}.png"
                        )
                else:
                    browser_env_state = None

                # check if current page contains a captcha
                if step == 0:
                    captcha_response = self.captcha_detection_agent.act(
                        os.path.join(ex_log_dir, f"screenshot_{step}.png")
                    )
                    logging.info("captcha_response = {}".format(captcha_response))

                    is_captcha = captcha_response.split("Answer:")[-1].strip().lower()

                    if is_captcha == "yes":
                        logging.info("Captcha detected. Terminating the traj.")
                        return [], "Captcha detected", False

                if step == 0:
                    response, pred, is_action_valid = self.task_proposal_agent.act(
                        browser_env_state["agent_image_obs"]
                    )
                else:
                    response, pred, is_action_valid = self.task_refiner_agent.act(
                        browser_env_state["agent_image_obs"],
                        action_history,
                        refined_goal,
                        image_history=select_refiner_image_history(
                            refiner_image_history,
                            self.args.refiner_image_history_steps,
                        ),
                    )

                logging.info(f"pred = {pred}")

                new_action_nl, new_action_grounded, refined_goal = (
                    pred["action_in_natural_language"],
                    pred["grounded_action"],
                    pred["task"],
                )
                step_answer = pred.get("answer", "") if isinstance(pred, dict) else ""
                # If refiner/proposal parser failed, do NOT let the "regex fail"
                # sentinel propagate as a real goal — fall back to the last good one.
                # Otherwise the agent literally types "regex fail" into the page and
                # the relabel step happily packages that nonsense as the new task.
                if refined_goal == "regex fail":
                    refined_goal = original_task or (
                        task_refinement_history[-1] if task_refinement_history else "regex fail"
                    )
                if step_answer and new_action_grounded in ("stop", "stop()"):
                    new_action_nl = f"{new_action_nl} | FINAL ANSWER: {step_answer}"
                if original_task is None and refined_goal != "regex fail":
                    original_task = refined_goal

                element_id = None
                bounding_box_coord = None

                logging.info("Agent response: {}".format(response))

                logging.info("Action (NL): {}\n".format(new_action_nl))
                logging.info("Action (grounded): {}\n".format(new_action_grounded))

                logging.info(f"refined_goal: {refined_goal}\n")

                # Dead-page detection: proposal flagged the homepage as unreachable
                # (4xx/5xx/Access Denied/Cloudflare/CAPTCHA). Respect stop() — don't
                # force scrolling on an error page. The trajectory ends; verifier
                # gets an empty trajectory which judges as failure (or unknown).
                is_dead_page = isinstance(refined_goal, str) and (
                    "site unreachable" in refined_goal.lower()
                    or "unreachable" in refined_goal.lower()
                )
                if (
                    new_action_grounded in ("stop", "stop()")
                    and not step_answer
                    and not is_dead_page
                    and len(task_trajectory_data["actions"]) < self.args.min_actions_before_stop
                ):
                    logging.info(
                        "overriding early stop before min_actions_before_stop=%s",
                        self.args.min_actions_before_stop,
                    )
                    new_action_nl = "Scroll down to continue exploring relevant public content"
                    new_action_grounded = 'scroll("down", 600)'
                    bounding_box_coord = None
                    is_action_valid = self.browser_env.step(
                        create_id_based_action(new_action_grounded)
                    )

                protocol_action = None
                parsed_action = None
                try:
                    parsed_runtime_action = create_id_based_action(new_action_grounded)
                    protocol_action = action_to_protocol(
                        parsed_runtime_action,
                        bounding_box_coord,
                        viewport_size,
                    )
                    if is_action_valid:
                        self.update_zoom_state(parsed_runtime_action)
                    parsed_action = {
                        "name": protocol_action["name"],
                        "args": protocol_action["args"],
                        "coordinate_space": COORDINATE_SPACE,
                        "screen_size": viewport_size,
                        "source_action": new_action_grounded,
                        "source_protocol": "visual_function_v1",
                        "target_protocol": "visual_function_v1",
                        "target_actions": protocol_action.get("target_actions", []),
                        "migration_status": "ok",
                    }
                    if bounding_box_coord is not None:
                        parsed_action["ref_resolution"] = {
                            "ref": element_id,
                            "bbox": [
                                float(bounding_box_coord["x"] - bounding_box_coord["width"] / 2),
                                float(bounding_box_coord["y"] - bounding_box_coord["height"] / 2),
                                float(bounding_box_coord["x"] + bounding_box_coord["width"] / 2),
                                float(bounding_box_coord["y"] + bounding_box_coord["height"] / 2),
                            ],
                            "center": [
                                float(bounding_box_coord["x"]),
                                float(bounding_box_coord["y"]),
                            ],
                            "source": "som_snapshot",
                        }
                except Exception:
                    logging.info("failed to convert action to protocol format")
                    logging.info(traceback.format_exc())

                click_marker_ref = None
                if (
                    protocol_action
                    and protocol_action["name"] in ("click", "doubleclick", "rightclick")
                    and protocol_action.get("target_actions")
                    and not self.args.no_dump_screenshots
                ):
                    raw_screenshot_path = os.path.join(ex_log_dir, f"screenshot_{step}.png")
                    marker_path = os.path.join(ex_log_dir, f"screenshot_action_{step}.png")
                    point = protocol_action["target_actions"][0].get("args", {}).get("point")
                    try:
                        save_click_marker(
                            raw_screenshot_path,
                            marker_path,
                            point,
                            viewport_size=viewport_size,
                        )
                        click_marker_ref = f"screenshot_action_{step}.png"
                    except Exception:
                        logging.info("failed to save click marker screenshot")
                        logging.info(traceback.format_exc())

                action["step_action_nl"] = new_action_nl
                action["new_action_grounded"] = new_action_grounded
                action["parsed_action"] = parsed_action
                action["step_refined_goal"] = refined_goal
                if click_marker_ref:
                    action["action_screenshot"] = click_marker_ref

                task_refinement_history.append(refined_goal)
                action_history.append(new_action_nl)

                # ground / execute the action
                current_url = current_url_before if browser_env_state else ""
                next_url = self.browser_env.page.url if self.browser_env.page else current_url

                step_record = make_step_record(
                    trajectory_id=trajectory_id,
                    step=step,
                    current_url=current_url,
                    next_url=next_url,
                    viewport_size=viewport_size,
                    action_nl=new_action_nl,
                    grounded_action=new_action_grounded,
                    parsed_action=parsed_action,
                    protocol_action=protocol_action,
                    execution_success=is_action_valid,
                )
                if click_marker_ref:
                    step_record["action_screenshot"] = click_marker_ref
                task_trajectory_data["steps"].append(step_record)

                if new_action_grounded in ("stop", "stop()") or new_action_grounded.startswith("answer("):
                    action["URL_after"] = next_url
                    task_trajectory_data["actions"].append(action)
                    completed = True
                    break

                logging.info("URL: {}".format(self.browser_env.page.url))

                if is_action_valid:
                    action["URL_after"] = self.browser_env.page.url
                    task_trajectory_data["actions"].append(action)
                    raw_screenshot_path = os.path.join(ex_log_dir, f"screenshot_{step}.png")
                    action_screenshot_history.append(raw_screenshot_path)
                    refiner_image_history.append(raw_screenshot_path)

                logging.info("##############################\n\n")
                step += 1
        except:
            logging.info("Error in step {}".format(step))

            # put traceback in logging log
            logging.error("{}".format(traceback.format_exc()))
            step += 1

        # summarize the task description using history
        screenshot_history = select_summarization_screenshots(
            action_screenshot_history,
            self.args.summarization_max_screenshots,
        )
        summarization_response, summarization_pred = self.summarization_agent.act(
            action_history, screenshot_history
        )
        if summarization_pred == "regex fail":
            fallback_task = original_task or (task_refinement_history[-1] if task_refinement_history else None)
            if fallback_task and fallback_task != "regex fail":
                logging.info(
                    "summarization failed; falling back to task = {}".format(
                        fallback_task
                    )
                )
                summarization_pred = fallback_task

        # Verify against the summarized intent so long trajectories are judged
        # by the task actually implied by the full action sequence.
        # Determine the verifier intent.
        # - Natural termination (agent issued answer/stop within budget):
        #     use the proposal task as written.
        # - Budget exhausted (no answer/stop): RELABEL the task to what
        #     the agent actually accomplished, using the summarization output.
        #     This yields valid short-horizon training data instead of failure.
        last_action_grounded = ""
        if task_trajectory_data.get("actions"):
            last_action_grounded = (
                task_trajectory_data["actions"][-1].get("new_action_grounded", "") or ""
            )
        agent_terminated_naturally = (
            last_action_grounded in ("stop", "stop()")
            or last_action_grounded.startswith("answer(")
        )
        n_substantive = sum(
            1
            for a in task_trajectory_data.get("actions", [])
            if not (a.get("new_action_grounded", "") or "").startswith(
                ("wait", "stop")
            )
        )
        budget_hit_relabel = (
            not agent_terminated_naturally
            and n_substantive >= 2  # at least 2 real interactions to be worth relabeling
            and summarization_pred
            and summarization_pred != "regex fail"
            and "regex fail" not in (summarization_pred or "").lower()
            and len(summarization_pred or "") >= 20  # nonsense is usually short
        )

        if budget_hit_relabel:
            logging.info(
                f"Budget exhausted without natural termination. Relabeling task: "
                f"{original_task!r} -> {summarization_pred!r}"
            )
            user_intent = summarization_pred
            original_task = summarization_pred  # so downstream sees relabeled
        elif (
            getattr(self.args, "verifier_intent_source", "original") == "original"
            and original_task
        ):
            user_intent = original_task
        else:
            user_intent = summarization_pred

        history = [
            action["step_action_nl"] for action in task_trajectory_data["actions"]
        ]
        img_path = os.path.join(ex_log_dir, "screenshot_final.png")

        logging.info("user_intent = {}".format(user_intent))
        logging.info("history = {}".format(history))

        last_step_screenshot = os.path.join(ex_log_dir, f"screenshot_{step}.png")
        fallback_for_final = (
            last_step_screenshot if os.path.exists(last_step_screenshot) else None
        )
        safe_screenshot(
            self.browser_env.page,
            img_path,
            fallback_path=fallback_for_final,
        )
        task_trajectory_data["observation_refs"].append("screenshot_final.png")

        try:
            last_page_html = self.browser_env.page.content()
            soup = BeautifulSoup(last_page_html, "html.parser")
            for tag in soup(["script", "style", "noscript"]):
                tag.decompose()
            last_page_md = "\n".join(
                line.strip()
                for line in soup.get_text("\n").splitlines()
                if line.strip()
            )[:20000]
        except:
            logging.info("failed to extract final page text for verifier")
            logging.info(traceback.format_exc())
            last_page_md = None

        self.browser_env.close()

        if self.args.use_all_screenshots_verifier:
            screenshot_history = [
                os.path.join(ex_log_dir, f"screenshot_{i}.png") for i in range(step + 1)
            ] + [img_path]
            try:
                verifier_agent_response = self.verifier_agent.act(
                    user_intent, history, screenshot_history, last_page_md
                )
            except Exception as verifier_err:
                logging.error("verifier crashed: %s", verifier_err)
                logging.info(traceback.format_exc())
                verifier_agent_response = "Thoughts: verifier crashed.\nStatus: unknown"
        else:
            try:
                verifier_agent_response = self.verifier_agent.act(
                    user_intent, history, img_path, last_page_md
                )
            except Exception as verifier_err:
                logging.error("verifier crashed: %s", verifier_err)
                logging.info(traceback.format_exc())
                verifier_agent_response = "Thoughts: verifier crashed.\nStatus: unknown"

        logging.info("verifier_agent_response = {}".format(verifier_agent_response))

        task_trajectory_data["task_summary"] = user_intent
        task_trajectory_data["original_task"] = original_task
        task_trajectory_data["task"]["instruction"] = original_task or user_intent
        task_trajectory_data["instruction"] = original_task or user_intent
        task_trajectory_data["summarization_agent_response"] = summarization_response
        task_trajectory_data["verifier_agent_response"] = verifier_agent_response
        status = verifier_status(verifier_agent_response)
        completion_status = "success" if status == "success" else "failed"
        factuality_status = "factually_valid" if status in {"success", "failure"} else "terminate"

        # Extract the agent's actual answer (from FINAL ANSWER tag injected on stop).
        agent_answer = ""
        for act in reversed(task_trajectory_data.get("actions", [])):
            nl = act.get("step_action_nl") or ""
            m = re.search(r"FINAL ANSWER:\s*(.+)$", nl, re.S)
            if m:
                agent_answer = m.group(1).strip()
                break

        task_trajectory_data["final"] = {
            "completion_status": completion_status,
            "factuality_status": factuality_status,
            "answer": agent_answer,
            "verifier": {
                "type": "trajectory_verifier",
                "version": "claude_compatible_summary_image_v1",
                "status": "correct" if status == "success" else "incorrect" if status == "failure" else "unknown",
                "raw_response": verifier_agent_response,
            },
        }
        task_trajectory_data["gold_output"] = {
            "task_summary": user_intent,
            "answer": agent_answer,
            "completion_status": completion_status,
        }
        # certificate holds HIDDEN ground truth for the verifier (webgym evaluator_reference, etc.).
        # The judge response goes under final.verifier, NOT here.
        cert = {}
        if getattr(self.args, "certificate_json", None):
            try:
                cert = json.loads(self.args.certificate_json)
            except Exception:
                logging.warning("certificate_json failed to parse; storing raw string")
                cert = {"raw": self.args.certificate_json}
        # Always include the summarization for downstream tooling, but as auxiliary info.
        cert.setdefault("aux_summarization_response", summarization_response)
        # Note whether the task was relabeled from proposal -> summarization
        # (this happens on Track A when the agent ran out of budget without
        # answer/stop, but did real work worth keeping as training data).
        if budget_hit_relabel:
            cert["relabeled"] = True
            cert["relabel_reason"] = "budget_exhausted_no_natural_termination"
        else:
            cert["relabeled"] = False
        task_trajectory_data["certificate"] = cert
        task_trajectory_data["verifier"] = task_trajectory_data["final"]["verifier"]
        task_trajectory_data["license"] = "unknown"
        task_trajectory_data["contamination"] = {
            "official_eval_excluded": False,
            "dedup_version": "not_run",
        }

        # Compute effective token count over w_t (the model-visible text).
        try:
            import tiktoken
            enc = tiktoken.get_encoding("cl100k_base")
            n_tok = sum(len(enc.encode(s.get("w_t") or "")) for s in task_trajectory_data.get("steps", []))
            task_trajectory_data["token_count"] = int(n_tok)
        except Exception:
            task_trajectory_data["token_count"] = sum(
                len((s.get("w_t") or "").split()) for s in task_trajectory_data.get("steps", [])
            )

        return task_trajectory_data, verifier_agent_response, True


def to_raw_string(s):
    return s.replace("\\", "\\\\")


def setup_logging(ex_log_dir):
    # Clear existing handlers
    for handler in logging.root.handlers[:]:
        logging.root.removeHandler(handler)

    # Create a new file handler
    log_file = os.path.join(ex_log_dir, "step_simulator_flow.log")
    logging.basicConfig(
        level=logging.INFO,
        filename=log_file,
        filemode="w",
        format="%(asctime)s - %(message)s",
    )


def main(args):
    # set seed
    random.seed(args.seed)

    # create a default unique model dir if not specified
    if args.model_dir is None:
        args.model_dir = "model_" + str(random.randint(0, 1000000))

    if not os.path.exists(args.model_dir):
        os.makedirs(args.model_dir, exist_ok=True)

    flow = Explorer(args)

    setup_logging(args.model_dir)

    if getattr(flow, "init_setup_error", False):
        # Setup failed (bad URL / cert / timeout). Write a stub trajectory so the
        # subprocess exits cleanly instead of hanging or producing nothing.
        stub = {
            "setup_error": True,
            "trajectory_id": os.path.basename(os.path.abspath(args.model_dir)),
            "init_url": args.init_url,
            "instruction": None,
            "actions": [],
            "steps": [],
            "observation_refs": [],
        }
        with open(os.path.join(args.model_dir, "task_trajectory_data.json"), "w") as f:
            json.dump(stub, f, indent=4)
        return

    try:
        task_trajectory_data, verifier_agent_response, is_traj_success = flow.run(
            args.model_dir
        )
    except Exception as run_err:
        # Last-resort safety net: never leave the task without a JSON on disk.
        logging.error("flow.run() crashed unexpectedly: %s", run_err)
        logging.info(traceback.format_exc())
        stub = {
            "run_error": True,
            "error_message": str(run_err),
            "trajectory_id": os.path.basename(os.path.abspath(args.model_dir)),
            "init_url": args.init_url,
            "instruction": None,
            "actions": [],
            "steps": [],
            "observation_refs": [],
        }
        with open(os.path.join(args.model_dir, "task_trajectory_data.json"), "w") as f:
            json.dump(stub, f, indent=4)
        return

    if not is_traj_success:
        return

    # dump the task trajectory data
    with open(os.path.join(args.model_dir, "task_trajectory_data.json"), "w") as f:
        json.dump(task_trajectory_data, f, indent=4)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--max-steps", type=int, default=5, help="Maximum number of steps to simulate"
    )
    parser.add_argument(
        "--print-parsed-tree",
        action="store_true",
        help="Print the parsed tree in stdout",
    )
    parser.add_argument(
        "--no-dump-screenshots",
        action="store_true",
        help="Do NOT dump screenshots of each step in screenshots/",
    )
    parser.add_argument(
        "--model-dir", type=str, default=None, help="Directory to save the models"
    )
    parser.add_argument("--seed", type=int, default=736537, help="Random seed")
    parser.add_argument(
        "--init-url",
        type=str,
        default="https://www.amazon.com/",
        help="initial url for the browser env",
    )
    parser.add_argument(
        "--certificate-json",
        type=str,
        default=None,
        help="JSON string with hidden ground-truth reference (e.g. webgym evaluator_reference). Stored under certificate.",
    )
    parser.add_argument(
        "--temp-refiner",
        type=float,
        default=0.01,
        help="temperature for the refiner agent",
    )
    parser.add_argument(
        "--omit-acc-tree", action="store_true", help="omit the accessibility tree"
    )
    parser.add_argument(
        "--viewport-width", type=int, default=1920, help="viewport width"
    )
    parser.add_argument(
        "--viewport-height", type=int, default=1080, help="viewport height"
    )
    parser.add_argument(
        "--print-num-toks",
        action="store_true",
        help="print the token count for each module",
        default=False,
    )
    parser.add_argument(
        "--deployment",
        type=str,
        default="gpt-4o",
        help="API model deployment",
    )
    parser.add_argument(
        "--use-all-screenshots-verifier",
        action=argparse.BooleanOptionalAction,
        help="use all screenshots for verifier",
        default=True,
    )
    parser.add_argument(
        "--temp-summ-verf",
        type=float,
        default=0.01,
        help="temperature for the summarizer and verifier agents",
    )
    parser.add_argument(
        "--refiner-image-history-steps",
        type=int,
        default=5,
        help="number of previous SOM screenshots to include in each refiner request",
    )
    parser.add_argument(
        "--summarization-max-screenshots",
        type=int,
        default=8,
        help="maximum number of action-focused screenshots to send to summarization",
    )
    parser.add_argument(
        "--min-actions-before-stop",
        type=int,
        default=0,
        help="replace stop with scroll down until this many valid actions are collected",
    )
    parser.add_argument(
        "--abort-on-url-prefix",
        nargs="*",
        default=["chrome-error://"],
        help="stop rollout when the current URL starts with any of these prefixes",
    )
    parser.add_argument(
        "--verifier-intent-source",
        choices=["summary", "original"],
        default="original",
        help="which task text to use as verifier intent",
    )
    parser.add_argument("--data-stage", default="sft")
    parser.add_argument("--data-split", default="internal_eval")
    parser.add_argument("--quality-tier", default="clean")
    parser.add_argument("--data-type", default="browser_trajectory")
    parser.add_argument("--source-dataset", default="synthetic_explorer")
    parser.add_argument("--benchmark-family", default="browser")

    args = parser.parse_args()
    print(args)

    main(args)
