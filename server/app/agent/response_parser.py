"""Parse THOUGHT + ACTION out of the LLM's raw text response.

Local models are not perfectly format-compliant, so the parser is defensive:
- THOUGHT may be missing or span multiple lines.
- ACTION JSON may be wrapped in ```json fences, have trailing prose, or use
  single quotes. We try several strategies before giving up.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass

from app.agent.types import Action

_THOUGHT_RE = re.compile(r"THOUGHT:\s*(.*?)(?:\nACTION:|\Z)", re.IGNORECASE | re.DOTALL)
_ACTION_RE = re.compile(r"ACTION:\s*(.*)", re.IGNORECASE | re.DOTALL)
_FENCE_RE = re.compile(r"```(?:json)?\s*(.*?)```", re.DOTALL)


@dataclass
class ParsedResponse:
    thought: str
    action: Action | None
    parse_error: str | None = None


def parse_response(text: str) -> ParsedResponse:
    json_mode = _try_json(text)
    if json_mode is not None:
        parsed = _parsed_json_mode_response(json_mode)
        if parsed is not None:
            return parsed

    thought = _extract_thought(text)
    action_blob = _extract_action_blob(text)

    if action_blob is None:
        return ParsedResponse(thought=thought, action=None, parse_error="No ACTION found.")

    obj = _try_json(action_blob)
    if obj is None:
        return ParsedResponse(
            thought=thought,
            action=None,
            parse_error="ACTION was not valid JSON.",
        )

    return _parsed_action_object(thought, obj)


def _parsed_json_mode_response(obj: dict) -> ParsedResponse | None:
    if isinstance(obj.get("action"), dict):
        thought = str(obj.get("thought") or "").strip()
        return _parsed_action_object(thought, obj["action"])
    if obj.get("tool") or obj.get("name"):
        thought = str(obj.get("thought") or "").strip()
        return _parsed_action_object(thought, obj)
    return None


def _parsed_action_object(thought: str, obj: dict) -> ParsedResponse:
    tool = obj.get("tool") or obj.get("name")
    if not tool:
        return ParsedResponse(
            thought=thought, action=None, parse_error="ACTION JSON missing 'tool'."
        )
    args = obj.get("args") or obj.get("arguments") or {}
    if not isinstance(args, dict):
        args = {}
    return ParsedResponse(thought=thought, action=Action(tool=str(tool), args=args))


def _extract_thought(text: str) -> str:
    m = _THOUGHT_RE.search(text)
    if m:
        return m.group(1).strip()
    # Fall back to everything before ACTION.
    idx = text.upper().find("ACTION:")
    if idx > 0:
        return text[:idx].strip()
    return text.strip()[:1000]


def _extract_action_blob(text: str) -> str | None:
    m = _ACTION_RE.search(text)
    candidate = m.group(1).strip() if m else text

    fence = _FENCE_RE.search(candidate)
    if fence:
        return fence.group(1).strip()

    brace = _first_balanced_object(candidate)
    return brace


def _first_balanced_object(text: str) -> str | None:
    start = text.find("{")
    if start == -1:
        return None
    depth = 0
    in_str = False
    escape = False
    for i in range(start, len(text)):
        ch = text[i]
        if in_str:
            if escape:
                escape = False
            elif ch == "\\":
                escape = True
            elif ch == '"':
                in_str = False
            continue
        if ch == '"':
            in_str = True
        elif ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                return text[start : i + 1]
    return None


def _try_json(blob: str) -> dict | None:
    candidates = [blob]
    collapsed = _collapse_template_braces(blob)
    if collapsed != blob:
        candidates.append(collapsed)

    for candidate in [*candidates, *(c.replace("'", '"') for c in candidates)]:
        try:
            obj = json.loads(candidate)
            if isinstance(obj, dict):
                return obj
        except (json.JSONDecodeError, TypeError):
            continue
    return None


def _collapse_template_braces(blob: str) -> str:
    if "{{" not in blob and "}}" not in blob:
        return blob
    return blob.replace("{{", "{").replace("}}", "}")
