"""Agent domain types."""

from __future__ import annotations

import enum
import time
from dataclasses import dataclass, field
from typing import Any


class AgentStatus(str, enum.Enum):
    SOLVED = "SOLVED"
    FAILED = "FAILED"
    TIMEOUT = "TIMEOUT"  # max steps reached
    GAVE_UP = "GAVE_UP"  # agent declared it cannot solve


@dataclass
class Action:
    tool: str
    args: dict[str, Any] = field(default_factory=dict)


@dataclass
class TrajectoryStep:
    step_number: int
    thought: str
    action: Action | None
    observation: str
    duration_ms: int = 0
    token_count: int = 0
    timestamp: float = field(default_factory=time.time)
