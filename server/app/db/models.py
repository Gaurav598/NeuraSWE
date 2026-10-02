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
    PREPARING = "PREPARING"
    ANALYZING = "ANALYZING"
    PLANNING = "PLANNING"
    IMPLEMENTING = "IMPLEMENTING"
    VALIDATING = "VALIDATING"
    AWAITING_APPROVAL = "AWAITING_APPROVAL"
    CHANGES_REQUESTED = "CHANGES_REQUESTED"
    PR_CREATING = "PR_CREATING"
    COMPLETED = "COMPLETED"
    CANCELLED = "CANCELLED"
    TIMED_OUT = "TIMED_OUT"
    REJECTED = "REJECTED"
    # Legacy values retained so existing installations migrate without data loss.
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
    __table_args__ = (UniqueConstraint("owner_id", "owner", "name", name="uq_repo_owner_name"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    owner_id: Mapped[str] = mapped_column(String(128), default="local", nullable=False, index=True)
    owner: Mapped[str] = mapped_column(String(255), nullable=False)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    installation_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    index_status: Mapped[IndexStatus] = mapped_column(
        Enum(IndexStatus, name="index_status"), default=IndexStatus.PENDING, nullable=False
    )
    last_indexed_sha: Mapped[str | None] = mapped_column(String(64), nullable=True)
    files_indexed: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    index_error: Mapped[str | None] = mapped_column(Text, nullable=True)
    indexing_progress: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
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
    __table_args__ = (
        Index("ix_run_repo_issue", "repository_id", "issue_number"),
        UniqueConstraint("owner_id", "idempotency_key", name="uq_runs_owner_idempotency"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    owner_id: Mapped[str] = mapped_column(String(128), default="local", nullable=False, index=True)
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
    model_requests: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    total_tokens: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    estimated_cost: Mapped[float | None] = mapped_column(nullable=True)
    tool_counts: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)
    duration_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    pr_number: Mapped[int | None] = mapped_column(Integer, nullable=True)
    pr_url: Mapped[str | None] = mapped_column(String(512), nullable=True)
    baseline_tests: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    final_tests: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    state_version: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    event_sequence: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    idempotency_key: Mapped[str | None] = mapped_column(String(255), nullable=True)
    cancellation_requested_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    worker_id: Mapped[str | None] = mapped_column(String(128), nullable=True)
    worker_attempt: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    lease_expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True, index=True)
    heartbeat_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    phase_started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    phase_timestamps: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)
    approval_status: Mapped[str] = mapped_column(String(32), default="NOT_REQUESTED", nullable=False)
    approval_comment: Mapped[str | None] = mapped_column(Text, nullable=True)
    approved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    patch_diff: Mapped[str | None] = mapped_column(Text, nullable=True)
    review_summary: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    pr_status: Mapped[str] = mapped_column(String(32), default="NOT_REQUESTED", nullable=False)
    remote_branch: Mapped[str | None] = mapped_column(String(255), nullable=True)
    commit_sha: Mapped[str | None] = mapped_column(String(64), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    repository: Mapped[Repository] = relationship(back_populates="runs")
    steps: Mapped[list[Step]] = relationship(
        back_populates="run", cascade="all, delete-orphan", order_by="Step.step_number"
    )
    events: Mapped[list[RunEvent]] = relationship(
        back_populates="run", cascade="all, delete-orphan", order_by="RunEvent.sequence"
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


class RunEvent(Base):
    __tablename__ = "run_events"
    __table_args__ = (UniqueConstraint("run_id", "sequence", name="uq_run_event_sequence"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    run_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("runs.id", ondelete="CASCADE"), nullable=False, index=True
    )
    sequence: Mapped[int] = mapped_column(Integer, nullable=False)
    event_type: Mapped[str] = mapped_column(String(64), nullable=False)
    payload: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    run: Mapped[Run] = relationship(back_populates="events")


class WebhookDelivery(Base):
    __tablename__ = "webhook_deliveries"
    __table_args__ = (UniqueConstraint("provider", "delivery_id", name="uq_webhook_delivery"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    provider: Mapped[str] = mapped_column(String(32), nullable=False)
    delivery_id: Mapped[str] = mapped_column(String(255), nullable=False)
    run_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
