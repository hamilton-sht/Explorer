#!/usr/bin/env python3
"""Re-judge a finished Track A/B run with the current verifier prompt.

Reads task_trajectory_data.json + saved screenshots from each task dir,
calls TrajectoryVerifierAgent.act() afresh, writes new judgement to
re_verifier_response.txt, and prints a new SR.
"""
import argparse
import json
import os
import re
import sys
from pathlib import Path

sys.path.insert(0, "/home/haotingshi/Explorer")
from traj_gen.trajectory_verifier import TrajectoryVerifierAgent


class _Args:
    """Minimal args object expected by TrajectoryVerifierAgent."""
    def __init__(self, model, base_url, api_key):
        self.deployment = model
        self.temp_summ_verf = 0.01
        self.use_all_screenshots_verifier = True
        self.print_num_toks = False
        self.model_dir = None
        os.environ["MODEL_NAME"] = model
        os.environ["API_BASE_URL"] = base_url
        os.environ["API_KEY"] = api_key


def _verifier_status(text: str) -> str:
    m = re.search(r'Status[*\s]*[:：][*\s]*["“]?(success|failure)', text or "", re.I)
    return m.group(1).lower() if m else "unknown"


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--run-dir", required=True, help="e.g. /home/.../webgym_eval_TRACK_A_v6_*/A")
    p.add_argument("--model", default="claude-opus-4-7")
    p.add_argument("--api-base-url", default="https://api-int.memtensor.cn/v1")
    p.add_argument("--api-key", default=os.environ.get("API_KEY", ""))
    args = p.parse_args()

    if not args.api_key:
        print("ERROR: --api-key or env API_KEY required", file=sys.stderr); sys.exit(2)

    agent = TrajectoryVerifierAgent(_Args(args.model, args.api_base_url, args.api_key))

    run = Path(args.run_dir)
    task_dirs = sorted([d for d in run.iterdir() if d.is_dir() and d.name.startswith("task_")])
    print(f"Re-judging {len(task_dirs)} tasks under {run}")
    print()

    results = []
    counts = {"success": 0, "failure": 0, "unknown": 0, "skipped": 0}
    for d in task_dirs:
        traj_path = d / "task_trajectory_data.json"
        if not traj_path.exists():
            counts["skipped"] += 1
            print(f"  {d.name:<24} SKIP no trajectory")
            continue
        td = json.loads(traj_path.read_text())
        intent = td.get("original_task") or td.get("task", {}).get("instruction") or ""
        if not intent:
            counts["skipped"] += 1
            print(f"  {d.name:<24} SKIP no intent")
            continue

        history = [a.get("step_action_nl", "") for a in td.get("actions", [])]
        n_steps = len(history)

        # Collect ordered screenshots: screenshot_0..N then screenshot_final
        screenshots = []
        for i in range(n_steps + 1):
            p1 = d / f"screenshot_{i}.png"
            if p1.exists():
                screenshots.append(str(p1))
        final_p = d / "screenshot_final.png"
        if final_p.exists():
            screenshots.append(str(final_p))

        # last_page_md: use the persisted HTML if any
        last_page_md = ""
        try:
            html_files = sorted(
                d.glob("html_*.html"),
                key=lambda p: int(re.search(r"\d+", p.stem).group()),
            )
            if html_files:
                from bs4 import BeautifulSoup
                soup = BeautifulSoup(html_files[-1].read_text(errors="ignore"), "html.parser")
                last_page_md = "\n".join(l for l in soup.get_text("\n").splitlines() if l.strip())[:20000]
        except Exception as e:
            print(f"  WARN {d.name}: html load failed: {e}")

        try:
            response = agent.act(intent, history, screenshots, last_page_md)
        except Exception as e:
            print(f"  {d.name:<24} ERR {e}")
            counts["unknown"] += 1
            continue

        status = _verifier_status(response)
        counts[status] = counts.get(status, 0) + 1
        # Save under task dir
        (d / "re_verifier_response.txt").write_text(response or "")
        old_status = _verifier_status(td.get("verifier_agent_response", ""))
        flip = ""
        if old_status != status:
            flip = f"  CHANGED  {old_status}→{status}"
        print(f"  {d.name:<24} {status:<8} (was {old_status:<8}) n={n_steps:>2}{flip}")
        results.append({"task": d.name, "status": status, "old_status": old_status, "n_steps": n_steps})

    n = len(results)
    sr = counts["success"] / max(1, n)
    print()
    print(f"=== Re-judged SR: {sr*100:.1f}% ({counts['success']}/{n}) ===")
    print(f"  success={counts['success']} failure={counts['failure']} unknown={counts['unknown']} skipped={counts['skipped']}")
    out = {"sr": sr, "counts": counts, "tasks": results, "run_dir": str(run)}
    (run / "re_verifier_summary.json").write_text(json.dumps(out, indent=2, ensure_ascii=False))
    print(f"\nSaved: {run / 're_verifier_summary.json'}")


if __name__ == "__main__":
    main()
