"""reliable lifecycle, ownership, approval, events, and webhook idempotency

Revision ID: 0003_reliable_platform
Revises: 0002_jira_multi_agent_fields
Create Date: 2026-09-25
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0003_reliable_platform"
down_revision: str | None = "0002_jira_multi_agent_fields"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


NEW_STATUSES = (
    "PREPARING", "ANALYZING", "PLANNING", "IMPLEMENTING", "VALIDATING",
    "AWAITING_APPROVAL", "CHANGES_REQUESTED", "PR_CREATING", "COMPLETED",
    "CANCELLED", "TIMED_OUT", "REJECTED",
)


def upgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name == "postgresql":
        for status in NEW_STATUSES:
            op.execute(sa.text(f"ALTER TYPE run_status ADD VALUE IF NOT EXISTS '{status}'"))

    op.add_column("repositories", sa.Column("owner_id", sa.String(128), nullable=False, server_default="local"))
    op.add_column("repositories", sa.Column("index_error", sa.Text(), nullable=True))
    op.add_column("repositories", sa.Column("indexing_progress", sa.Integer(), nullable=False, server_default="0"))
    op.create_index("ix_repositories_owner_id", "repositories", ["owner_id"])
    op.drop_constraint("uq_repo_owner_name", "repositories", type_="unique")
    op.create_unique_constraint("uq_repo_owner_name", "repositories", ["owner_id", "owner", "name"])

    columns = [
        sa.Column("owner_id", sa.String(128), nullable=False, server_default="local"),
        sa.Column("model_requests", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("total_tokens", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("estimated_cost", sa.Float(), nullable=True),
        sa.Column("tool_counts", sa.JSON(), nullable=False, server_default="{}"),
        sa.Column("state_version", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("event_sequence", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("idempotency_key", sa.String(255), nullable=True),
        sa.Column("cancellation_requested_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("worker_id", sa.String(128), nullable=True),
        sa.Column("worker_attempt", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("lease_expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("heartbeat_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("phase_started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("phase_timestamps", sa.JSON(), nullable=False, server_default="{}"),
        sa.Column("approval_status", sa.String(32), nullable=False, server_default="NOT_REQUESTED"),
        sa.Column("approval_comment", sa.Text(), nullable=True),
        sa.Column("approved_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("patch_diff", sa.Text(), nullable=True),
        sa.Column("review_summary", sa.JSON(), nullable=True),
        sa.Column("pr_status", sa.String(32), nullable=False, server_default="NOT_REQUESTED"),
        sa.Column("remote_branch", sa.String(255), nullable=True),
        sa.Column("commit_sha", sa.String(64), nullable=True),
    ]
    for column in columns:
        op.add_column("runs", column)
    op.create_index("ix_runs_owner_id", "runs", ["owner_id"])
    op.create_index("ix_runs_lease_expires_at", "runs", ["lease_expires_at"])
    op.create_unique_constraint("uq_runs_owner_idempotency", "runs", ["owner_id", "idempotency_key"])

    op.create_table(
        "run_events",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("run_id", sa.String(36), sa.ForeignKey("runs.id", ondelete="CASCADE"), nullable=False),
        sa.Column("sequence", sa.Integer(), nullable=False),
        sa.Column("event_type", sa.String(64), nullable=False),
        sa.Column("payload", sa.JSON(), nullable=False, server_default="{}"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint("run_id", "sequence", name="uq_run_event_sequence"),
    )
    op.create_index("ix_run_events_run_id", "run_events", ["run_id"])
    op.create_table(
        "webhook_deliveries",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("provider", sa.String(32), nullable=False),
        sa.Column("delivery_id", sa.String(255), nullable=False),
        sa.Column("run_id", sa.String(36), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint("provider", "delivery_id", name="uq_webhook_delivery"),
    )


def downgrade() -> None:
    op.drop_table("webhook_deliveries")
    op.drop_index("ix_run_events_run_id", table_name="run_events")
    op.drop_table("run_events")
    op.drop_constraint("uq_runs_owner_idempotency", "runs", type_="unique")
    op.drop_index("ix_runs_lease_expires_at", table_name="runs")
    op.drop_index("ix_runs_owner_id", table_name="runs")
    for name in (
        "commit_sha", "remote_branch", "pr_status", "review_summary", "patch_diff",
        "approved_at", "approval_comment", "approval_status", "phase_timestamps", "phase_started_at",
        "heartbeat_at", "lease_expires_at", "worker_attempt", "worker_id",
        "cancellation_requested_at", "idempotency_key", "event_sequence", "state_version",
        "tool_counts", "estimated_cost", "total_tokens", "model_requests", "owner_id",
    ):
        op.drop_column("runs", name)
    op.drop_index("ix_repositories_owner_id", table_name="repositories")
    op.drop_constraint("uq_repo_owner_name", "repositories", type_="unique")
    op.create_unique_constraint("uq_repo_owner_name", "repositories", ["owner", "name"])
    op.drop_column("repositories", "indexing_progress")
    op.drop_column("repositories", "index_error")
    op.drop_column("repositories", "owner_id")
