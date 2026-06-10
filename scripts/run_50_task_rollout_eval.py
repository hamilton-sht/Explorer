#!/usr/bin/env python3
import argparse
import concurrent.futures
import json
import os
import re
import statistics
import subprocess
import time
from collections import Counter
from pathlib import Path


DEFAULT_URLS = [
    "https://news.ycombinator.com/item?id=48434312",
    "https://news.ycombinator.com/item?id=48425528",
    "https://news.ycombinator.com/item?id=48389368",
    "https://news.ycombinator.com/item?id=48416264",
    "https://news.ycombinator.com/item?id=48431085",
    "https://news.ycombinator.com/item?id=48424605",
    "https://news.ycombinator.com/item?id=48428025",
    "https://news.ycombinator.com/item?id=48431461",
    "https://news.ycombinator.com/item?id=48432199",
    "https://news.ycombinator.com/item?id=48434436",
]


STOPWORDS = {
    "the", "and", "for", "with", "about", "through", "from", "this", "that",
    "into", "then", "read", "browse", "find", "view", "discussion", "comments",
    "comment", "hacker", "news", "news.ycombinator.com", "on", "in", "to",
    "of", "a", "an", "by", "including", "specific", "community",
}


def verifier_status(text):
    match = re.search(r'Status[*\s]*[:：][*\s]*["“]?(success|failure)', text or "", re.I)
    return match.group(1).lower() if match else "unknown"


def tokenize_task(text):
    return [
        token
        for token in re.findall(r"[a-zA-Z][a-zA-Z0-9_+-]{2,}", (text or "").lower())
        if token not in STOPWORDS
    ]


def task_family(text):
    lower = (text or "").lower()
    if any(x in lower for x in ["reply", "respond", "post", "upvote"]):
        return "write_or_vote_requested"
    if any(x in lower for x in ["article", "blog post", "full article"]):
        return "article_reading"
    if any(x in lower for x in ["compare", "perspective", "opinions", "viewpoints"]):
        return "discussion_comparison"
    if any(x in lower for x in ["user", "author", "commenter"]):
        return "user_or_commenter_research"
    return "general_browsing"


def run_one(args, index, url):
    run_dir = args.output_dir / f"task_{index:03d}"
    run_dir.mkdir(parents=True, exist_ok=True)
    env = os.environ.copy()
    env.setdefault("MODEL_NAME", args.model)
    env.setdefault("API_BASE_URL", args.api_base_url)
    env.setdefault("CLAUDE_COMPAT_MAX_TEXT_CHARS", str(args.max_text_chars))

    python_cmd = ["python"] if args.conda_env == "none" else ["conda", "run", "-n", args.conda_env, "python"]
    cmd = python_cmd + [
        "-m", "traj_gen.main",
        "--model-dir", str(run_dir),
        "--init-url", url,
        "--max-steps", str(args.max_steps),
        "--deployment", args.model,
        "--viewport-width", str(args.viewport_width),
        "--viewport-height", str(args.viewport_height),
        "--refiner-image-history-steps", str(args.refiner_image_history_steps),
        "--summarization-max-screenshots", str(args.summarization_max_screenshots),
        "--min-actions-before-stop", str(args.min_actions_before_stop),
        "--verifier-intent-source", args.verifier_intent_source,
    ]

    started = time.time()
    with (run_dir / "run.log").open("w", encoding="utf-8") as log:
        try:
            proc = subprocess.run(
                cmd,
                cwd=args.repo_dir,
                env=env,
                stdout=log,
                stderr=subprocess.STDOUT,
                timeout=args.timeout_seconds,
            )
            exit_code = proc.returncode
            timed_out = False
        except subprocess.TimeoutExpired:
            exit_code = -1
            timed_out = True
            log.write("\nTIMEOUT\n")
    elapsed = round(time.time() - started, 1)

    result = {
        "index": index,
        "url": url,
        "run_dir": str(run_dir),
        "exit_code": exit_code,
        "timed_out": timed_out,
        "elapsed_sec": elapsed,
    }

    data_path = run_dir / "task_trajectory_data.json"
    if not data_path.exists():
        result.update({"json": False, "actions": 0, "verifier": "missing"})
        return result

    data = json.loads(data_path.read_text())
    log_text = (run_dir / "step_simulator_flow.log").read_text(errors="ignore") if (run_dir / "step_simulator_flow.log").exists() else ""
    usage_path = run_dir / "llm_usage.jsonl"
    usage_rows = [
        json.loads(line)
        for line in usage_path.read_text().splitlines()
        if line.strip()
    ] if usage_path.exists() else []
    actions = data.get("actions", [])
    original_task = data.get("original_task") or ""
    task_summary = data.get("task_summary") or ""
    status = verifier_status(data.get("verifier_agent_response", ""))

    result.update(
        {
            "json": True,
            "actions": len(actions),
            "verifier": status,
            "original_task": original_task,
            "task_summary": task_summary,
            "task_family": task_family(original_task or task_summary),
            "unique_action_types": sorted(
                set((a.get("new_action_grounded") or "").split("[", 1)[0].strip() for a in actions)
            ),
            "final_url": actions[-1].get("URL_after") if actions else "",
            "tracebacks": log_text.count("Traceback (most recent call last):"),
            "regex_fail": "regex fail" in log_text or "regex fail" in json.dumps(data),
            "history_count_max": max([int(x) for x in re.findall(r"refiner image history count = (\d+)", log_text)] or [0]),
            "api_calls": len(usage_rows),
            "total_tokens": sum((row.get("usage") or {}).get("total_tokens", 0) for row in usage_rows),
        }
    )
    return result


def summarize(results, output_dir):
    completed = [r for r in results if r.get("json")]
    actions = [r["actions"] for r in completed]
    successes = [r for r in completed if r.get("verifier") == "success"]
    task_texts = [(r.get("original_task") or r.get("task_summary") or "") for r in completed]
    unique_tasks = len(set(task_texts))
    token_counter = Counter()
    for text in task_texts:
        token_counter.update(tokenize_task(text))

    summary = {
        "total": len(results),
        "completed_json": len(completed),
        "success": len(successes),
        "success_rate": round(len(successes) / len(completed), 4) if completed else 0,
        "length": {
            "min": min(actions) if actions else 0,
            "max": max(actions) if actions else 0,
            "mean": round(statistics.mean(actions), 2) if actions else 0,
            "median": round(statistics.median(actions), 2) if actions else 0,
            "p25": sorted(actions)[len(actions) // 4] if actions else 0,
            "p75": sorted(actions)[(len(actions) * 3) // 4] if actions else 0,
        },
        "unique_task_texts": unique_tasks,
        "task_families": dict(Counter(r.get("task_family", "unknown") for r in completed)),
        "top_task_terms": token_counter.most_common(25),
        "verifier_counts": dict(Counter(r.get("verifier", "missing") for r in results)),
        "traceback_tasks": sum(1 for r in completed if r.get("tracebacks", 0) > 0),
        "regex_fail_tasks": sum(1 for r in completed if r.get("regex_fail")),
        "total_api_calls": sum(r.get("api_calls", 0) for r in completed),
        "total_tokens": sum(r.get("total_tokens", 0) for r in completed),
    }

    (output_dir / "results.jsonl").write_text(
        "\n".join(json.dumps(r, ensure_ascii=True) for r in results) + "\n",
        encoding="utf-8",
    )
    (output_dir / "summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")

    lines = [
        "# 50 Task Rollout Evaluation",
        "",
        f"- Total tasks: {summary['total']}",
        f"- Completed JSON: {summary['completed_json']}",
        f"- Verifier success: {summary['success']} ({summary['success_rate']:.1%})",
        f"- Trajectory length: min {summary['length']['min']}, p25 {summary['length']['p25']}, median {summary['length']['median']}, mean {summary['length']['mean']}, p75 {summary['length']['p75']}, max {summary['length']['max']}",
        f"- Unique task texts: {summary['unique_task_texts']}",
        f"- Task families: {summary['task_families']}",
        f"- Top task terms: {summary['top_task_terms']}",
        f"- Traceback tasks: {summary['traceback_tasks']}",
        f"- Regex-fail tasks: {summary['regex_fail_tasks']}",
        f"- Total API calls: {summary['total_api_calls']}",
        f"- Total tokens: {summary['total_tokens']}",
        "",
        "## Per Task",
        "",
    ]
    for r in results:
        lines.append(
            f"- task_{r['index']:03d}: actions={r.get('actions', 0)}, verifier={r.get('verifier')}, family={r.get('task_family')}, url={r.get('url')}"
        )
    (output_dir / "REPORT.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    return summary


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo-dir", type=Path, default=Path.cwd())
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--urls-file", type=Path)
    parser.add_argument("--num-tasks", type=int, default=50)
    parser.add_argument("--workers", type=int, default=5)
    parser.add_argument("--max-steps", type=int, default=12)
    parser.add_argument("--min-actions-before-stop", type=int, default=12)
    parser.add_argument("--refiner-image-history-steps", type=int, default=5)
    parser.add_argument("--summarization-max-screenshots", type=int, default=8)
    parser.add_argument("--verifier-intent-source", choices=["summary", "original"], default="summary")
    parser.add_argument("--model", default="claude-opus-4-7")
    parser.add_argument("--api-base-url", default="https://api-int.memtensor.cn/v1")
    parser.add_argument("--conda-env", default="osworld")
    parser.add_argument("--viewport-width", type=int, default=1920)
    parser.add_argument("--viewport-height", type=int, default=1080)
    parser.add_argument("--timeout-seconds", type=int, default=1200)
    parser.add_argument("--max-text-chars", type=int, default=60000)
    args = parser.parse_args()

    args.output_dir.mkdir(parents=True, exist_ok=True)
    urls = DEFAULT_URLS
    if args.urls_file:
        urls = [
            line.strip()
            for line in args.urls_file.read_text(encoding="utf-8").splitlines()
            if line.strip() and not line.startswith("#")
        ]
    task_urls = [urls[i % len(urls)] for i in range(args.num_tasks)]

    results = []
    with concurrent.futures.ThreadPoolExecutor(max_workers=args.workers) as executor:
        futures = [
            executor.submit(run_one, args, index, url)
            for index, url in enumerate(task_urls, 1)
        ]
        for future in concurrent.futures.as_completed(futures):
            result = future.result()
            results.append(result)
            print(json.dumps(result, ensure_ascii=True), flush=True)

    results.sort(key=lambda r: r["index"])
    summary = summarize(results, args.output_dir)
    print(json.dumps(summary, indent=2), flush=True)


if __name__ == "__main__":
    main()
