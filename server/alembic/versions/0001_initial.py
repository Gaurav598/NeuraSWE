"""initial schema

Revision ID: 0001_initial
Revises:
Create Date: 2026-06-12
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0001_initial"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

run_status = sa.Enum("QUEUED", "RUNNING", "SOLVED", "FAILED", "TIMEOUT", name="run_status")
index_status = sa.Enum("PENDING", "INDEXING", "READY", "FAILED", name="index_status")


def upgrade() -> None:
    op.create_table(
        "repositories",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("owner", sa.String(length=255), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("installation_id", sa.Integer(), nullable=True),
        sa.Column("index_status", index_status, nullable=False, server_default="PENDING"),
        sa.Column("last_indexed_sha", sa.String(length=64), nullable=True),
        sa.Column("files_indexed", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("config", sa.JSON(), nullable=False, server_default="{}"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.UniqueConstraint("owner", "name", name="uq_repo_owner_name"),
    )
    op.create_table(
        "runs",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column(
            "repository_id",
            sa.String(length=36),
            sa.ForeignKey("repositories.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("issue_number", sa.Integer(), nullable=False),
        sa.Column("issue_title", sa.Text(), nullable=False),
        sa.Column("issue_body", sa.Text(), nullable=False, server_default=""),
        sa.Column("status", run_status, nullable=False, server_default="QUEUED"),
        sa.Column("model", sa.String(length=128), nullable=False, server_default=""),
        sa.Column("total_steps", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("duration_ms", sa.Integer(), nullable=True),
        sa.Column("pr_number", sa.Integer(), nullable=True),
        sa.Column("pr_url", sa.String(length=512), nullable=True),
        sa.Column("baseline_tests", sa.JSON(), nullable=True),
        sa.Column("final_tests", sa.JSON(), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_run_repo_issue", "runs", ["repository_id", "issue_number"])
    op.create_table(
        "steps",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column(
            "run_id",
            sa.String(length=36),
            sa.ForeignKey("runs.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("step_number", sa.Integer(), nullable=False),
        sa.Column("thought", sa.Text(), nullable=True),
        sa.Column("tool_name", sa.String(length=64), nullable=True),
        sa.Column("tool_args", sa.JSON(), nullable=True),
        sa.Column("observation", sa.Text(), nullable=True),
        sa.Column("duration_ms", sa.Integer(), nullable=True),
        sa.Column("token_count", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index("ix_step_run_number", "steps", ["run_id", "step_number"])


def downgrade() -> None:
    op.drop_index("ix_step_run_number", table_name="steps")
    op.drop_table("steps")
    op.drop_index("ix_run_repo_issue", table_name="runs")
    op.drop_table("runs")
    op.drop_table("repositories")
    run_status.drop(op.get_bind(), checkfirst=True)
    index_status.drop(op.get_bind(), checkfirst=True)
