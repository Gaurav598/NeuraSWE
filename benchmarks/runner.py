"""Small reproducible local evaluator for controlled repositories."""

from __future__ import annotations

import argparse
import json
import shlex
import subprocess
import time
from pathlib import Path


def run_command(command: str, cwd: Path, timeout: int) -> dict:
    started = time.monotonic()
    try:
        result = subprocess.run(
            shlex.split(command), cwd=cwd, capture_output=True, text=True,
            timeout=timeout, check=False,
        )
        return {"exit_code": result.returncode, "duration_ms": int((time.monotonic() - started) * 1000), "output_tail": (result.stdout + result.stderr)[-4000:]}
    except subprocess.TimeoutExpired as exc:
        return {"exit_code": 124, "duration_ms": int((time.monotonic() - started) * 1000), "output_tail": str(exc), "timed_out": True}


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--cases", required=True)
    parser.add_argument("--output", required=True)
    args = parser.parse_args()
    cases = json.loads(Path(args.cases).read_text())
    outcomes = []
    for case in cases:
        cwd = Path(case["repository"]).resolve()
        timeout = int(case.get("timeout_seconds", 300))
        started = time.monotonic()
        baseline = run_command(case["setup"], cwd, timeout) if case.get("setup") else None
        validation = run_command(case["validate"], cwd, timeout)
        changed = subprocess.run(
            ["git", "diff", "--name-only"], cwd=cwd, capture_output=True, text=True, check=False
        ).stdout.splitlines()
        expected = set(case.get("expected_paths", []))
        allowed = set(case.get("allowed_paths", case.get("expected_paths", [])))
        metrics = {}
        if case.get("run_metrics_file"):
            metrics = json.loads(Path(case["run_metrics_file"]).read_text())
        tool_counts = metrics.get("tool_counts") or case.get("tool_counts")
        outcomes.append({
            "id": case["id"], "attempted": True, "resolved": validation["exit_code"] == 0,
            "incorrect_patch": bool(
                (expected and not expected.issubset(set(changed)))
                or (allowed and set(changed) - allowed)
            ),
            "validation_failure": validation["exit_code"] not in {0, 124},
            "execution_time_ms": int((time.monotonic() - started) * 1000),
            "changed_paths": changed, "baseline": baseline, "validation": validation,
            "tool_calls": (
                sum(int(value) for value in tool_counts.values()) if tool_counts else None
            ),
            "tool_counts": tool_counts,
            "model_requests": metrics.get("model_requests"),
            "tokens": metrics.get("total_tokens"),
            "estimated_cost": metrics.get("estimated_cost"),
            "pr_creation_failure": (
                metrics.get("pr_status") == "FAILED" if "pr_status" in metrics else None
            ),
        })
    Path(args.output).write_text(json.dumps({"cases": outcomes}, indent=2) + "\n")


if __name__ == "__main__":
    main()
