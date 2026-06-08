#!/usr/bin/env python3
import argparse
import json
import os
import re
import subprocess
import sys
import time
from pathlib import Path


URLS = [
    "https://news.ycombinator.com/",
    "https://news.ycombinator.com/news?p=2",
    "https://news.ycombinator.com/ask",
    "https://news.ycombinator.com/show",
]


def status_from_verifier(text):
    match = re.search(r'Status:\s*["“]?(success|failure)', text or "", re.I)
    return match.group(1).lower() if match else "unknown"


def classify_failure(run_dir, data):
    reasons = []
    log_path = run_dir / "step_simulator_flow.log"
    log = log_path.read_text(errors="ignore") if log_path.exists() else ""
    verifier = data.get("verifier_agent_response", "")
    actions = data.get("actions", [])
    if len(actions) < 15:
        reasons.append("short")
    if "Timeout" in log:
        reasons.append("timeout")
    if "regex fail" in log or "regex fail" in json.dumps(data):
        reasons.append("regex")
    if "Traceback" in log:
        reasons.append("traceback")
    if 'Status: "failure"' in verifier or "Status: failure" in verifier:
        reasons.append("verifier_failure")
    return ",".join(reasons) or "unknown"


def run_one(args, attempt, url):
    run_dir = args.output_dir / f"attempt_{attempt:03d}_{re.sub(r'[^a-zA-Z0-9]+', '_', url).strip('_')}"
    run_dir.mkdir(parents=True, exist_ok=True)
    env = os.environ.copy()
    env.setdefault("MODEL_NAME", args.model)
    env.setdefault("API_BASE_URL", args.api_base_url)
    env.setdefault("CLAUDE_COMPAT_MAX_TEXT_CHARS", "60000")

    cmd = [
        "conda",
        "run",
        "-n",
        args.conda_env,
        "python",
        "-m",
        "traj_gen.main",
        "--model-dir",
        str(run_dir),
        "--init-url",
        url,
        "--max-steps",
        str(args.max_steps),
        "--deployment",
        args.model,
        "--viewport-width",
        str(args.viewport_width),
        "--viewport-height",
        str(args.viewport_height),
        "--refiner-image-history-steps",
        "0",
        "--summarization-max-screenshots",
        str(args.summarization_max_screenshots),
        "--min-actions-before-stop",
        str(args.min_actions),
        "--verifier-intent-source",
        args.verifier_intent_source,
    ]

    started = time.time()
    with (run_dir / "run.log").open("w", encoding="utf-8") as log:
        proc = subprocess.run(
            cmd,
            cwd=args.repo_dir,
            env=env,
            stdout=log,
            stderr=subprocess.STDOUT,
            timeout=args.timeout_seconds,
        )
    elapsed = time.time() - started

    data_path = run_dir / "task_trajectory_data.json"
    if not data_path.exists():
        return {
            "run_dir": str(run_dir),
            "url": url,
            "exit_code": proc.returncode,
            "elapsed_sec": round(elapsed, 1),
            "accepted": False,
            "reason": "no_json",
        }

    data = json.loads(data_path.read_text())
    actions = len(data.get("actions", []))
    verifier = status_from_verifier(data.get("verifier_agent_response", ""))
    accepted = args.min_actions <= actions <= args.max_accept_actions and verifier == "success"
    return {
        "run_dir": str(run_dir),
        "url": url,
        "exit_code": proc.returncode,
        "elapsed_sec": round(elapsed, 1),
        "actions": actions,
        "verifier": verifier,
        "accepted": accepted,
        "reason": "" if accepted else classify_failure(run_dir, data),
        "summary": data.get("task_summary", ""),
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo-dir", type=Path, default=Path.cwd())
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--target-successes", type=int, default=5)
    parser.add_argument("--max-attempts", type=int, default=30)
    parser.add_argument("--min-actions", type=int, default=15)
    parser.add_argument("--max-accept-actions", type=int, default=30)
    parser.add_argument("--max-steps", type=int, default=30)
    parser.add_argument("--model", default="claude-opus-4-7")
    parser.add_argument("--api-base-url", default="https://api-int.memtensor.cn/v1")
    parser.add_argument("--conda-env", default="osworld")
    parser.add_argument("--viewport-width", type=int, default=1920)
    parser.add_argument("--viewport-height", type=int, default=1080)
    parser.add_argument("--summarization-max-screenshots", type=int, default=8)
    parser.add_argument("--timeout-seconds", type=int, default=1800)
    parser.add_argument("--urls-file", type=Path)
    parser.add_argument("--verifier-intent-source", choices=["summary", "original"], default="summary")
    args = parser.parse_args()

    args.output_dir.mkdir(parents=True, exist_ok=True)
    urls = URLS
    if args.urls_file:
        urls = [
            line.strip()
            for line in args.urls_file.read_text(encoding="utf-8").splitlines()
            if line.strip() and not line.strip().startswith("#")
        ]
    successes = []
    results = []
    for attempt in range(1, args.max_attempts + 1):
        url = urls[(attempt - 1) % len(urls)]
        result = run_one(args, attempt, url)
        results.append(result)
        with (args.output_dir / "rollout_results.jsonl").open("a", encoding="utf-8") as f:
            f.write(json.dumps(result, ensure_ascii=True) + "\n")
        print(json.dumps(result, ensure_ascii=True), flush=True)
        if result["accepted"]:
            successes.append(result)
            if len(successes) >= args.target_successes:
                break

    report = {
        "target_successes": args.target_successes,
        "successes": successes,
        "attempts": results,
    }
    (args.output_dir / "summary.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    return 0 if len(successes) >= args.target_successes else 1


if __name__ == "__main__":
    sys.exit(main())
