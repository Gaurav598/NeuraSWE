"""jira and multi-agent visibility fields

Revision ID: 0002_jira_multi_agent_fields
Revises: 0001_initial
Create Date: 2026-06-17
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0002_jira_multi_agent_fields"
down_revision: str | None = "0001_initial"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("runs", sa.Column("source", sa.String(length=32), nullable=False, server_default="github"))
    op.add_column("runs", sa.Column("external_issue_key", sa.String(length=64), nullable=True))
    op.add_column("runs", sa.Column("external_issue_url", sa.String(length=512), nullable=True))
    op.add_column("steps", sa.Column("agent_name", sa.String(length=64), nullable=True))


def downgrade() -> None:
    op.drop_column("steps", "agent_name")
    op.drop_column("runs", "external_issue_url")
    op.drop_column("runs", "external_issue_key")
    op.drop_column("runs", "source")
