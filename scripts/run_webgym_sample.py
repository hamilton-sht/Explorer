#!/usr/bin/env python3
"""Run sampled webgym tasks through Explorer.

Tracks:
  A: only use webgym URL; Explorer auto-proposes its own task (no --task)
  B: pass webgym task_name via --task (task-following mode)

Concurrency 3. Reads /home/haotingshi/Explorer/webgym_sample_10.jsonl.
Writes per-task dirs under output_root/{A,B}/task_NN_<id>/ and a summary.json.
"""
import argparse, concurrent.futures, json, os, re, subprocess, sys, time
from pathlib import Path

EXPLORER = Path("/home/haotingshi/Explorer")
SAMPLE = EXPLORER / "webgym_sample_30.jsonl"


def verifier_status(text: str) -> str:
    m = re.search(r'Status:\s*["“]?(success|failure)', text or "", re.I)
    return m.group(1).lower() if m else "unknown"


def _read_traj_verdict(out_dir: Path) -> str:
    """Prefer task_trajectory_data.json's verifier_agent_response; fall back to log."""
    p = out_dir / "task_trajectory_data.json"
    if p.exists():
        try:
            d = json.loads(p.read_text())
            return verifier_status(d.get("verifier_agent_response", ""))
        except Exception:
            pass
    return "unknown"


def run_one(track: str, idx: int, task: dict, args) -> dict:
    out_dir = Path(args.output_root) / track / f"task_{idx:02d}_{task['task_id']}"
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
        "--refiner-image-history-steps", "3",
        "--summarization-max-screenshots", "10",
        "--min-actions-before-stop", "3",
    ]
    if track == "B":
        cmd += ["--task", task["task_name"]]
        # Pass webgym ground-truth reference as the trajectory certificate.
        cert = {
            "source_benchmark": "webgym",
            "task_id": task["task_id"],
            "difficulty": task.get("difficulty"),
            "evaluator_reference": task.get("evaluator_reference"),
            "definite_answer": task.get("definite_answer"),
            "domain": task.get("domain"),
            "subdomain": task.get("subdomain"),
        }
        cmd += ["--certificate-json", json.dumps(cert, ensure_ascii=False)]

    log_path = out_dir / "run.log"
    t0 = time.time()
    with open(log_path, "w") as logf:
        proc = subprocess.run(
            cmd, cwd=str(EXPLORER), env=env, stdout=logf, stderr=subprocess.STDOUT,
            timeout=args.timeout,
        )
    dt = time.time() - t0

    log_text = log_path.read_text(errors="ignore")
    status = _read_traj_verdict(out_dir)
    if status == "unknown":
        status = verifier_status(log_text)
    return {
        "track": track, "idx": idx, "task_id": task["task_id"],
        "difficulty": task.get("difficulty"), "url": task["website"],
        "task_name": task["task_name"][:120],
        "returncode": proc.returncode, "elapsed_s": round(dt, 1),
        "status": status, "out_dir": str(out_dir),
    }


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--output-root", default=str(EXPLORER / "trajectories" / f"webgym_eval_{time.strftime('%Y%m%d_%H%M%S')}"))
    p.add_argument("--tracks", default="A,B")
    p.add_argument("--workers", type=int, default=3)
    p.add_argument("--model", default="claude-opus-4-7")
    p.add_argument("--api-base-url", default="https://api-int.memtensor.cn/v1")
    p.add_argument("--api-key", default=os.environ.get("API_KEY", ""))
    p.add_argument("--max-steps", type=int, default=15)
    p.add_argument("--timeout", type=int, default=1200)
    p.add_argument("--sample-file", default=str(SAMPLE), help="JSONL file with tasks/sites")
    args = p.parse_args()
    if not args.api_key:
        print("ERROR: --api-key or API_KEY env required", file=sys.stderr); sys.exit(2)

    tasks = [json.loads(l) for l in open(args.sample_file)]
    tracks = [t.strip() for t in args.tracks.split(",") if t.strip()]
    jobs = [(track, i, task) for track in tracks for i, task in enumerate(tasks)]
    print(f"Running {len(jobs)} jobs ({len(tasks)} tasks × {len(tracks)} tracks) with {args.workers} workers")
    print(f"Output: {args.output_root}\n")

    results = []
    with concurrent.futures.ThreadPoolExecutor(max_workers=args.workers) as pool:
        futs = {pool.submit(run_one, tr, i, t, args): (tr, i, t) for (tr, i, t) in jobs}
        for fut in concurrent.futures.as_completed(futs):
            tr, i, t = futs[fut]
            try:
                r = fut.result()
                print(f"[{r['track']}#{r['idx']:02d}] {r['status']:8s} rc={r['returncode']} {r['elapsed_s']}s diff={r['difficulty']} {r['url'][:40]}")
            except Exception as e:
                r = {"track": tr, "idx": i, "task_id": t["task_id"], "error": str(e), "status": "error"}
                print(f"[{tr}#{i:02d}] ERROR {e}")
            results.append(r)

    summary = {"tracks": {}, "tasks": results, "config": vars(args)}
    for tr in tracks:
        rs = [r for r in results if r["track"] == tr]
        counts = {"success": 0, "failure": 0, "unknown": 0, "error": 0}
        for r in rs: counts[r.get("status", "unknown")] = counts.get(r.get("status", "unknown"), 0) + 1
        sr = counts["success"] / max(1, len(rs))
        summary["tracks"][tr] = {"n": len(rs), "SR": round(sr, 3), **counts}

    Path(args.output_root).mkdir(parents=True, exist_ok=True)
    with open(Path(args.output_root) / "summary.json", "w") as f:
        json.dump(summary, f, indent=2, ensure_ascii=False)

    print("\n=== Summary ===")
    for tr, s in summary["tracks"].items():
        print(f"Track {tr}: SR={s['SR']*100:.1f}% ({s['success']}/{s['n']}) | success={s['success']} fail={s['failure']} unknown={s['unknown']} error={s['error']}")
    print(f"\nFull summary: {args.output_root}/summary.json")


if __name__ == "__main__":
    main()
