"""Single authoritative run lifecycle and terminal-state rules."""

from __future__ import annotations

from app.db.models import RunStatus

TERMINAL = {
    RunStatus.COMPLETED, RunStatus.FAILED, RunStatus.CANCELLED,
    RunStatus.TIMED_OUT, RunStatus.REJECTED, RunStatus.SOLVED, RunStatus.TIMEOUT,
}

TRANSITIONS: dict[RunStatus, set[RunStatus]] = {
    RunStatus.QUEUED: {RunStatus.PREPARING, RunStatus.CANCELLED, RunStatus.FAILED, RunStatus.TIMED_OUT},
    RunStatus.PREPARING: {RunStatus.QUEUED, RunStatus.ANALYZING, RunStatus.CANCELLED, RunStatus.FAILED, RunStatus.TIMED_OUT},
    RunStatus.ANALYZING: {RunStatus.QUEUED, RunStatus.PLANNING, RunStatus.CANCELLED, RunStatus.FAILED, RunStatus.TIMED_OUT},
    RunStatus.PLANNING: {RunStatus.QUEUED, RunStatus.IMPLEMENTING, RunStatus.CANCELLED, RunStatus.FAILED, RunStatus.TIMED_OUT},
    RunStatus.IMPLEMENTING: {RunStatus.QUEUED, RunStatus.VALIDATING, RunStatus.CANCELLED, RunStatus.FAILED, RunStatus.TIMED_OUT},
    RunStatus.VALIDATING: {RunStatus.QUEUED, RunStatus.AWAITING_APPROVAL, RunStatus.CANCELLED, RunStatus.FAILED, RunStatus.TIMED_OUT},
    RunStatus.AWAITING_APPROVAL: {RunStatus.PR_CREATING, RunStatus.REJECTED, RunStatus.CHANGES_REQUESTED, RunStatus.CANCELLED},
    RunStatus.CHANGES_REQUESTED: {RunStatus.QUEUED, RunStatus.CANCELLED},
    RunStatus.PR_CREATING: {RunStatus.COMPLETED, RunStatus.AWAITING_APPROVAL, RunStatus.FAILED, RunStatus.CANCELLED},
    # Legacy execution state may advance into the upgraded flow.
    RunStatus.RUNNING: {RunStatus.QUEUED, RunStatus.IMPLEMENTING, RunStatus.VALIDATING, RunStatus.AWAITING_APPROVAL, RunStatus.FAILED, RunStatus.CANCELLED, RunStatus.TIMED_OUT},
}


class InvalidTransition(ValueError):
    pass


def assert_transition(current: RunStatus, target: RunStatus) -> None:
    if current == target:
        return
    if current in TERMINAL or target not in TRANSITIONS.get(current, set()):
        raise InvalidTransition(f"Invalid run transition: {current.value} -> {target.value}")


def is_active(status: RunStatus) -> bool:
    return status not in TERMINAL
