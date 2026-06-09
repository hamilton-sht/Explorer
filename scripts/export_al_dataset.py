#!/usr/bin/env python3
import argparse
import json
import re
import shutil
from datetime import datetime, timezone
from pathlib import Path


def verifier_status(text):
    match = re.search(r'Status:\s*["“]?(success|failure)', text or "", re.I)
    return match.group(1).lower() if match else "unknown"


def reject_reasons(traj):
    reasons = []
    if not traj.get("steps"):
        reasons.append("missing_steps")
    for step in traj.get("steps", []):
        if "x_t" not in step or "x_next" not in step:
            reasons.append("missing_observation")
            break
        if step.get("parsed_action") is None:
            reasons.append("missing_parsed_action")
            break
        if not step.get("w_t") or "<|tool_call>" not in step["w_t"]:
            reasons.append("missing_tool_call")
            break
    if not traj.get("coordinate_space") or not traj.get("screen_size"):
        reasons.append("missing_coordinate_metadata")
    status = verifier_status(traj.get("verifier_agent_response", ""))
    if status != "success":
        reasons.append(f"verifier_{status}")
    return sorted(set(reasons))


def task_record(traj):
    return {
        "sample_id": traj.get("sample_id"),
        "trajectory_id": traj.get("trajectory_id"),
        "stage": traj.get("stage"),
        "split": traj.get("split"),
        "quality_tier": traj.get("quality_tier"),
        "data_type": traj.get("data_type"),
        "source_dataset": traj.get("source_dataset"),
        "benchmark_family": traj.get("benchmark_family"),
        "instruction": traj.get("instruction"),
        "start_url": traj.get("init_url"),
        "feasibility": traj.get("task", {}).get("feasibility", "true"),
        "license": traj.get("license", "unknown"),
        "contamination": traj.get("contamination", {}),
    }


def trajectory_record(traj, artifact_prefix):
    copied = dict(traj)
    copied["observation_refs"] = [
        str(Path(artifact_prefix) / ref) for ref in traj.get("observation_refs", [])
    ]
    for step in copied.get("steps", []):
        for obs_key in ("x_t", "x_next"):
            image = step.get(obs_key, {}).get("image")
            if image:
                step[obs_key]["image"] = str(Path(artifact_prefix) / image)
    return copied


def link_or_copy_artifacts(src_dir, dst_dir, copy_artifacts):
    if dst_dir.exists() or dst_dir.is_symlink():
        if dst_dir.is_symlink() or dst_dir.is_file():
            dst_dir.unlink()
        else:
            shutil.rmtree(dst_dir)
    if copy_artifacts:
        shutil.copytree(src_dir, dst_dir)
    else:
        dst_dir.symlink_to(src_dir.resolve(), target_is_directory=True)


def write_jsonl(path, rows):
    with path.open("w", encoding="utf-8") as f:
        for row in rows:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("rollout_dir", type=Path)
    parser.add_argument("output_dir", type=Path)
    parser.add_argument("--dataset-version", default="active_lifting_browser_v1")
    parser.add_argument("--copy-artifacts", action="store_true")
    args = parser.parse_args()

    args.output_dir.mkdir(parents=True, exist_ok=True)
    artifacts_dir = args.output_dir / "artifacts"
    artifacts_dir.mkdir(exist_ok=True)

    tasks = []
    trajectories = []
    rejected = []
    qa_items = []

    for path in sorted(args.rollout_dir.rglob("task_trajectory_data.json")):
        traj = json.loads(path.read_text(encoding="utf-8"))
        traj_id = traj.get("trajectory_id") or path.parent.name
        traj["trajectory_id"] = traj_id
        traj["sample_id"] = traj.get("sample_id") or traj_id

        artifact_prefix = Path("artifacts") / traj_id
        link_or_copy_artifacts(path.parent, artifacts_dir / traj_id, args.copy_artifacts)

        reasons = reject_reasons(traj)
        status = verifier_status(traj.get("verifier_agent_response", ""))
        qa_items.append(
            {
                "trajectory_id": traj_id,
                "verifier_status": status,
                "num_steps": len(traj.get("steps", [])),
                "reject_reasons": reasons,
            }
        )

        if reasons:
            rejected.append(
                {
                    "sample_id": traj.get("sample_id"),
                    "trajectory_id": traj_id,
                    "reasons": reasons,
                    "source_path": str(path),
                }
            )
            continue

        tasks.append(task_record(traj))
        trajectories.append(trajectory_record(traj, artifact_prefix))

    manifest = {
        "dataset_version": args.dataset_version,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "source_rollout_dir": str(args.rollout_dir),
        "split_counts": {
            "tasks": len(tasks),
            "trajectories": len(trajectories),
            "rejected": len(rejected),
        },
        "protocol": "active_lifting_browser_v1",
        "coordinate_space": "image_pixel",
        "verifier_version": "trajectory_verifier",
        "artifacts": "artifacts/",
    }

    (args.output_dir / "manifest.json").write_text(
        json.dumps(manifest, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    write_jsonl(args.output_dir / "tasks.jsonl", tasks)
    write_jsonl(args.output_dir / "trajectories.jsonl", trajectories)
    write_jsonl(args.output_dir / "rejected.jsonl", rejected)
    (args.output_dir / "qa_report.json").write_text(
        json.dumps(
            {
                "total_seen": len(qa_items),
                "accepted": len(trajectories),
                "rejected": len(rejected),
                "items": qa_items,
            },
            indent=2,
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )


if __name__ == "__main__":
    main()
