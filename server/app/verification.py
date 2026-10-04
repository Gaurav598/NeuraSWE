"""Deterministic baseline/final verification classification."""

from __future__ import annotations

from typing import Any


def compare_verification(baseline: dict[str, Any] | None, final: dict[str, Any] | None) -> dict[str, Any]:
    baseline = baseline or {"classification": "UNEXECUTED", "failed_tests": []}
    final = final or {"classification": "UNEXECUTED", "failed_tests": []}
    baseline_failures = set(baseline.get("failed_tests") or [])
    final_failures = set(final.get("failed_tests") or [])
    new_failures = sorted(final_failures - baseline_failures)
    fixed_failures = sorted(baseline_failures - final_failures)
    regression = bool(new_failures)
    if not new_failures and not final_failures and final.get("success") is False:
        # Unknown identities: count equality is not proof of non-regression.
        regression = True
    return {
        "baseline_classification": baseline.get("classification", "UNKNOWN"),
        "final_classification": final.get("classification", "UNKNOWN"),
        "new_failures": new_failures,
        "fixed_failures": fixed_failures,
        "regression": regression,
    }
