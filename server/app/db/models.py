"""ORM models — direct translation of the Prisma schema in the spec.

Repository 1—* Run 1—* Step.
"""

from __future__ import annotations

import enum
import uuid
from datetime import datetime

from sqlalchemy import (
    JSON,
    DateTime,
    Enum,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base


def _uuid() -> str:
    return str(uuid.uuid4())


class RunStatus(str, enum.Enum):
    QUEUED = "QUEUED"
    RUNNING = "RUNNING"
    SOLVED = "SOLVED"
    FAILED = "FAILED"
    TIMEOUT = "TIMEOUT"


class IndexStatus(str, enum.Enum):
    PENDING = "PENDING"
    INDEXING = "INDEXING"
    READY = "READY"
    FAILED = "FAILED"


class Repository(Base):
    __tablename__ = "repositories"
    __table_args__ = (UniqueConstraint("owner", "name", name="uq_repo_owner_name"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    owner: Mapped[str] = mapped_column(String(255), nullable=False)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    installation_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    index_status: Mapped[IndexStatus] = mapped_column(
        Enum(IndexStatus, name="index_status"), default=IndexStatus.PENDING, nullable=False
    )
    last_indexed_sha: Mapped[str | None] = mapped_column(String(64), nullable=True)
    files_indexed: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    config: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )

    runs: Mapped[list[Run]] = relationship(
        back_populates="repository", cascade="all, delete-orphan"
    )

    @property
    def full_name(self) -> str:
        return f"{self.owner}/{self.name}"


class Run(Base):
    __tablename__ = "runs"
    __table_args__ = (Index("ix_run_repo_issue", "repository_id", "issue_number"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    repository_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("repositories.id", ondelete="CASCADE"), nullable=False
    )
    issue_number: Mapped[int] = mapped_column(Integer, nullable=False)
    issue_title: Mapped[str] = mapped_column(Text, nullable=False)
    issue_body: Mapped[str] = mapped_column(Text, default="", nullable=False)
    source: Mapped[str] = mapped_column(String(32), default="github", nullable=False)
    external_issue_key: Mapped[str | None] = mapped_column(String(64), nullable=True)
    external_issue_url: Mapped[str | None] = mapped_column(String(512), nullable=True)
    status: Mapped[RunStatus] = mapped_column(
        Enum(RunStatus, name="run_status"), default=RunStatus.QUEUED, nullable=False
    )
    model: Mapped[str] = mapped_column(String(128), default="", nullable=False)
    total_steps: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    duration_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    pr_number: Mapped[int | None] = mapped_column(Integer, nullable=True)
    pr_url: Mapped[str | None] = mapped_column(String(512), nullable=True)
    baseline_tests: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    final_tests: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    repository: Mapped[Repository] = relationship(back_populates="runs")
    steps: Mapped[list[Step]] = relationship(
        back_populates="run", cascade="all, delete-orphan", order_by="Step.step_number"
    )


class Step(Base):
    __tablename__ = "steps"
    __table_args__ = (Index("ix_step_run_number", "run_id", "step_number"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    run_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("runs.id", ondelete="CASCADE"), nullable=False
    )
    step_number: Mapped[int] = mapped_column(Integer, nullable=False)
    agent_name: Mapped[str | None] = mapped_column(String(64), nullable=True)
    thought: Mapped[str | None] = mapped_column(Text, nullable=True)
    tool_name: Mapped[str | None] = mapped_column(String(64), nullable=True)
    tool_args: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    observation: Mapped[str | None] = mapped_column(Text, nullable=True)
    duration_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    token_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    run: Mapped[Run] = relationship(back_populates="steps")
