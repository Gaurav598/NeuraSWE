"""GitHub webhook signature verification and event parsing."""

from __future__ import annotations

import hashlib
import hmac
from dataclasses import dataclass

from app.config import settings
from app.utils.logger import get_logger

log = get_logger("github.webhook")

TRIGGER_ACTIONS = {"opened", "assigned", "labeled", "reopened"}
DEFAULT_TRIGGER_LABEL = "neuraswe"


@dataclass
class IssueEvent:
    owner: str
    repo: str
    installation_id: int | None
    issue_number: int
    title: str
    body: str
    labels: list[str]
    action: str


def verify_signature(payload: bytes, signature_header: str | None) -> bool:
    """Verify X-Hub-Signature-256. If no secret is configured, accept only in dev."""
    if not settings.github_webhook_secret:
        return not settings.is_production
    if not signature_header or not signature_header.startswith("sha256="):
        return False
    expected = (
        "sha256="
        + hmac.new(
            settings.github_webhook_secret.encode(), payload, hashlib.sha256
        ).hexdigest()
    )
    return hmac.compare_digest(expected, signature_header)


def parse_issue_event(body: dict) -> IssueEvent | None:
    if "issue" not in body:
        return None
    issue = body["issue"]
    repo = body.get("repository", {})
    owner = repo.get("owner", {}).get("login", "")
    labels = [label.get("name", "") for label in issue.get("labels", [])]
    return IssueEvent(
        owner=owner,
        repo=repo.get("name", ""),
        installation_id=(body.get("installation") or {}).get("id"),
        issue_number=issue.get("number", 0),
        title=issue.get("title", ""),
        body=issue.get("body") or "",
        labels=labels,
        action=body.get("action", ""),
    )


def should_trigger(event: IssueEvent, trigger_label: str = DEFAULT_TRIGGER_LABEL) -> bool:
    if event.action not in TRIGGER_ACTIONS:
        return False
    return trigger_label in event.labels
