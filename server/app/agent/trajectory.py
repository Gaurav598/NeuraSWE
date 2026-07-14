"""Trajectory storage and serialization."""

from __future__ import annotations

import json

from app.agent.types import TrajectoryStep
from app.utils.token_counter import count_tokens


class Trajectory:
    def __init__(self) -> None:
        self.steps: list[TrajectoryStep] = []
        self.summary: str = ""

    def add(self, step: TrajectoryStep) -> None:
        self.steps.append(step)

    def __len__(self) -> int:
        return len(self.steps)

    @staticmethod
    def render_step(step: TrajectoryStep) -> str:
        parts = [f"--- Step {step.step_number} ---", f"THOUGHT: {step.thought}"]
        if step.action is not None:
            action_json = json.dumps({"tool": step.action.tool, "args": step.action.args})
            parts.append(f"ACTION: {action_json}")
        parts.append(f"OBSERVATION: {step.observation}")
        return "\n".join(parts)

    def render(self, steps: list[TrajectoryStep] | None = None) -> str:
        steps = self.steps if steps is None else steps
        blocks = []
        if self.summary:
            blocks.append(f"[EARLIER PROGRESS SUMMARY]\n{self.summary}")
        blocks.extend(self.render_step(s) for s in steps)
        return "\n\n".join(blocks)

    def token_estimate(self) -> int:
        return count_tokens(self.render())
