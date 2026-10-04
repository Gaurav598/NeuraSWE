import pytest

from app.db.models import RunStatus
from app.run_state import InvalidTransition, assert_transition


def test_happy_path_transitions() -> None:
    path = [
        RunStatus.QUEUED, RunStatus.PREPARING, RunStatus.ANALYZING,
        RunStatus.PLANNING, RunStatus.IMPLEMENTING, RunStatus.VALIDATING,
        RunStatus.AWAITING_APPROVAL, RunStatus.PR_CREATING, RunStatus.COMPLETED,
    ]
    for current, target in zip(path, path[1:], strict=True):
        assert_transition(current, target)


def test_terminal_state_cannot_be_overwritten() -> None:
    with pytest.raises(InvalidTransition):
        assert_transition(RunStatus.CANCELLED, RunStatus.COMPLETED)


def test_safe_worker_phase_can_be_requeued_after_lease_expiry() -> None:
    assert_transition(RunStatus.IMPLEMENTING, RunStatus.QUEUED)
