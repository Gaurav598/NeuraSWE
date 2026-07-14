"""Pydantic schemas for API serialization (the Zod equivalent)."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from app.db.models import IndexStatus, RunStatus


class StepOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    step_number: int
    agent_name: str | None = None
    thought: str | None = None
    tool_name: str | None = None
    tool_args: dict[str, Any] | None = None
    observation: str | None = None
    duration_ms: int | None = None
    token_count: int | None = None
    created_at: datetime


class RunSummary(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    repository_id: str
    issue_number: int
    issue_title: str
    source: str = "github"
    external_issue_key: str | None = None
    external_issue_url: str | None = None
    status: RunStatus
    model: str
    total_steps: int
    duration_ms: int | None = None
    pr_number: int | None = None
    pr_url: str | None = None
    created_at: datetime
    completed_at: datetime | None = None


class RunDetail(RunSummary):
    issue_body: str
    baseline_tests: dict[str, Any] | None = None
    final_tests: dict[str, Any] | None = None
    error_message: str | None = None
    steps: list[StepOut] = Field(default_factory=list)


class RepositoryOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    owner: str
    name: str
    installation_id: int | None = None
    index_status: IndexStatus
    last_indexed_sha: str | None = None
    files_indexed: int
    config: dict[str, Any]
    created_at: datetime
    updated_at: datetime


class RepoConfigUpdate(BaseModel):
    trigger_label: str | None = None
    auto_assign: bool | None = None
    base_branch: str | None = None


class GitHubIssueLabel(BaseModel):
    name: str
    color: str | None = None


class GitHubIssueOut(BaseModel):
    number: int
    title: str
    body: str
    state: str
    author: str | None = None
    labels: list[GitHubIssueLabel] = Field(default_factory=list)
    html_url: str
    created_at: datetime
    updated_at: datetime


class PaginatedGitHubIssues(BaseModel):
    items: list[GitHubIssueOut]
    page: int
    page_size: int
    has_more: bool


class ManualRunRequest(BaseModel):
    repo_id: str
    issue_number: int


class StatsOut(BaseModel):
    total_runs: int
    solved: int
    failed: int
    in_progress: int
    success_rate: float
    avg_steps: float
    avg_duration_ms: float
    recent: list[RunSummary]


class HealthOut(BaseModel):
    status: str
    services: dict[str, bool]


class PaginatedRuns(BaseModel):
    items: list[RunSummary]
    total: int
    page: int
    page_size: int
