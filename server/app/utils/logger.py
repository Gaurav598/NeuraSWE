"""Structured logging setup using structlog over the stdlib logging module."""

from __future__ import annotations

import logging
import re
import sys

import structlog

from app.config import settings

_configured = False
_SENSITIVE_FRAGMENTS = ("token", "secret", "password", "api_key", "authorization", "credential")
_VALUE_PATTERNS = (
    re.compile(r"(?i)\bBearer\s+[A-Za-z0-9._~+/-]+=*"),
    re.compile(r"(?i)(?P<scheme>[a-z][a-z0-9+.-]*://)[^\s/@:]+:[^\s/@]+@"),
    re.compile(r"\b(?:gh[pousr]_|gsk_|sk-)[A-Za-z0-9_-]{12,}"),
)


def _scrub_value(value):  # type: ignore[no-untyped-def]
    if isinstance(value, str):
        for pattern in _VALUE_PATTERNS:
            value = pattern.sub(
                lambda match: (
                    f"{match.groupdict().get('scheme')}[REDACTED]@"
                    if match.groupdict().get("scheme") else "[REDACTED]"
                ),
                value,
            )
        return value
    if isinstance(value, dict):
        return {key: _scrub_value(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return type(value)(_scrub_value(item) for item in value)
    return value


def _redact_sensitive(_logger, _method_name: str, event_dict: dict):  # type: ignore[no-untyped-def]
    for key in list(event_dict):
        if any(fragment in key.lower() for fragment in _SENSITIVE_FRAGMENTS):
            event_dict[key] = "[REDACTED]"
        else:
            event_dict[key] = _scrub_value(event_dict[key])
    return event_dict


def configure_logging() -> None:
    global _configured
    if _configured:
        return

    level = getattr(logging, settings.log_level.upper(), logging.INFO)

    logging.basicConfig(
        format="%(message)s",
        stream=sys.stdout,
        level=level,
    )

    processors = [
        structlog.contextvars.merge_contextvars,
        structlog.processors.add_log_level,
        _redact_sensitive,
        structlog.processors.StackInfoRenderer(),
        structlog.processors.TimeStamper(fmt="iso"),
    ]

    if settings.is_production:
        processors.append(structlog.processors.JSONRenderer())
    else:
        processors.append(structlog.dev.ConsoleRenderer())

    structlog.configure(
        processors=processors,
        wrapper_class=structlog.make_filtering_bound_logger(level),
        logger_factory=structlog.PrintLoggerFactory(),
        cache_logger_on_first_use=True,
    )
    _configured = True


def get_logger(name: str | None = None) -> structlog.BoundLogger:
    configure_logging()
    return structlog.get_logger(name)
