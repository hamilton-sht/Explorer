#!/usr/bin/env python3
"""Run Track A trajectory generation over a list of websites.

Track A semantics:
  - Explorer is given only a URL.
  - TaskProposalAgent auto-proposes a task on step 0 from the homepage.
  - TaskRefinerAgent grounds actions step by step.
  - On budget exhaustion (no answer/stop within --max-steps), the trajectory
    is RELABELED via TaskSummarizationAgent so it can be kept as
    short-horizon training data. See certificate.relabeled in the output JSON.

Sample-file format: JSONL with at least {"task_id", "website"} per line.
"""
import argparse
import concurrent.futures
import json
import os
import re
import subprocess
import sys
import time
from pathlib import Path

EXPLORER = Path(__file__).resolve().parent.parent
DEFAULT_SAMPLE = EXPLORER / "data" / "webgym_sites_sample_30.jsonl"


def verifier_status(text: str) -> str:
    m = re.search(r'Status[*\s]*[:：][*\s]*["“]?(success|failure)', text or "", re.I)
    return m.group(1).lower() if m else "unknown"


def _read_traj_verdict(out_dir: Path) -> str:
    p = out_dir / "task_trajectory_data.json"
    if p.exists():
        try:
            d = json.loads(p.read_text())
            return verifier_status(d.get("verifier_agent_response", ""))
        except Exception:
            pass
    return "unknown"


def run_one(idx: int, task: dict, args) -> dict:
    out_dir = Path(args.output_root) / f"task_{idx:02d}_{task['task_id']}"
    out_dir.mkdir(parents=True, exist_ok=True)
    env = os.environ.copy()
    env["MODEL_NAME"] = args.model
    env["API_BASE_URL"] = args.api_base_url
    env["API_KEY"] = args.api_key
    env["DISPLAY"] = env.get("DISPLAY", ":99")

    cmd = [
        sys.executable, "-m", "traj_gen.main",
        "--model-dir", str(out_dir),
        "--init-url", task["website"],
        "--max-steps", str(args.max_steps),
        "--deployment", args.model,
        "--viewport-width", "1920",
        "--viewport-height", "1080",
        "--refiner-image-history-steps", str(args.max_steps),
        "--summarization-max-screenshots", "10",
        "--min-actions-before-stop", "3",
    ]

    log_path = out_dir / "run.log"
    t0 = time.time()
    with open(log_path, "w") as logf:
        proc = subprocess.run(
            cmd, cwd=str(EXPLORER), env=env, stdout=logf, stderr=subprocess.STDOUT,
            timeout=args.timeout,
        )
    dt = time.time() - t0

    status = _read_traj_verdict(out_dir)
    if status == "unknown":
        status = verifier_status(log_path.read_text(errors="ignore"))
    return {
        "idx": idx,
        "task_id": task["task_id"],
        "url": task["website"],
        "returncode": proc.returncode,
        "elapsed_s": round(dt, 1),
        "status": status,
        "out_dir": str(out_dir),
    }


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--output-root", default=str(EXPLORER / "trajectories" / f"trackA_{time.strftime('%Y%m%d_%H%M%S')}"))
    p.add_argument("--workers", type=int, default=4)
    p.add_argument("--model", default="gpt-5.5")
    p.add_argument("--api-base-url", default="https://api-int.memtensor.cn/v1")
    p.add_argument("--api-key", default=os.environ.get("API_KEY", ""))
    p.add_argument("--max-steps", type=int, default=8)
    p.add_argument("--timeout", type=int, default=900)
    p.add_argument("--sample-file", default=str(DEFAULT_SAMPLE), help="JSONL with one site per line: {task_id, website}")
    args = p.parse_args()
    if not args.api_key:
        print("ERROR: --api-key or API_KEY env required", file=sys.stderr)
        sys.exit(2)

    tasks = [json.loads(l) for l in open(args.sample_file)]
    print(f"Running Track A on {len(tasks)} sites, {args.workers} workers, max_steps={args.max_steps}")
    print(f"Output: {args.output_root}\n")

    results = []
    with concurrent.futures.ThreadPoolExecutor(max_workers=args.workers) as pool:
        futs = {pool.submit(run_one, i, t, args): (i, t) for i, t in enumerate(tasks)}
        for fut in concurrent.futures.as_completed(futs):
            i, t = futs[fut]
            try:
                r = fut.result()
                print(f"[#{r['idx']:02d}] {r['status']:8s} rc={r['returncode']} {r['elapsed_s']}s {r['url'][:50]}")
            except Exception as e:
                r = {"idx": i, "task_id": t["task_id"], "error": str(e), "status": "error"}
                print(f"[#{i:02d}] ERROR {e}")
            results.append(r)

    counts = {"success": 0, "failure": 0, "unknown": 0, "error": 0}
    for r in results:
        counts[r.get("status", "unknown")] = counts.get(r.get("status", "unknown"), 0) + 1
    sr = counts["success"] / max(1, len(results))
    summary = {"n": len(results), "SR": round(sr, 3), **counts, "tasks": results, "config": vars(args)}

    Path(args.output_root).mkdir(parents=True, exist_ok=True)
    with open(Path(args.output_root) / "summary.json", "w") as f:
        json.dump(summary, f, indent=2, ensure_ascii=False)

    print(f"\n=== Track A SR: {sr*100:.1f}% ({counts['success']}/{len(results)}) ===")
    print(f"  success={counts['success']} failure={counts['failure']} unknown={counts['unknown']} error={counts['error']}")
    print(f"\nFull summary: {args.output_root}/summary.json")


if __name__ == "__main__":
    main()
