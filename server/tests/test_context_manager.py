"""Tests for context management: observation truncation and compaction trigger.

Uses a fake LLM so no network is required.
"""

import pytest

from app.agent.context_manager import ContextManager
from app.agent.trajectory import Trajectory
from app.agent.types import Action, TrajectoryStep


class FakeLLM:
    async def summarize(self, text: str, instruction: str) -> str:
        return "SUMMARY: explored auth module, root cause in login.py:34."


def _step(n: int, big: bool = False) -> TrajectoryStep:
    obs = ("x" * 4000) if big else f"observation {n}"
    return TrajectoryStep(n, f"thought {n}", Action("read_file", {"path": f"f{n}.py"}), obs)


def test_truncate_observation_marks_truncation():
    cm = ContextManager(FakeLLM())
    long_obs = "line\n" * 5000
    out = cm.truncate_observation(long_obs)
    assert "truncated" in out.lower()
    assert len(out) < len(long_obs)


def test_short_observation_unchanged():
    cm = ContextManager(FakeLLM())
    out = cm.truncate_observation("short result")
    assert out == "short result"


@pytest.mark.asyncio
async def test_compaction_triggers_and_summarizes():
    cm = ContextManager(FakeLLM())
    cm.max_context = 2000  # force a tight budget
    cm.full_steps = 4
    traj = Trajectory()
    for i in range(1, 21):
        traj.add(_step(i, big=True))

    await cm.maybe_compact(traj)
    assert traj.summary.startswith("SUMMARY:")
    # Head (3) + tail (7) kept verbatim.
    assert len(traj.steps) <= 10


@pytest.mark.asyncio
async def test_no_compaction_when_small():
    cm = ContextManager(FakeLLM())
    traj = Trajectory()
    for i in range(1, 4):
        traj.add(_step(i))
    await cm.maybe_compact(traj)
    assert traj.summary == ""
    assert len(traj.steps) == 3
