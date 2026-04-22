"""Structured JSON logging with PII-scrubber (ADR-012).

Usage:
    from mcp_toolkit_py.logging import setup_logging, get_logger
    setup_logging(level="info")
    log = get_logger(__name__)
    log.info("event", user_id=123, token="sk-xxx")  # token redacted
"""

from __future__ import annotations

import logging
import sys
from collections.abc import MutableMapping
from typing import Any

import structlog

_REDACT_KEYS = frozenset(
    {
        "authorization",
        "token",
        "secret",
        "password",
        "client_secret",
        "api_key",
        "access_token",
        "refresh_token",
    }
)
_REDACT_PLACEHOLDER = "<redacted>"


def _pii_scrubber(
    _logger: Any, _method_name: str, event_dict: MutableMapping[str, Any]
) -> MutableMapping[str, Any]:
    """Redact keys that commonly hold credentials. Shallow scan by design."""
    for key in list(event_dict.keys()):
        if key.lower() in _REDACT_KEYS and event_dict[key] is not None:
            event_dict[key] = _REDACT_PLACEHOLDER
    return event_dict


def setup_logging(level: str = "info") -> None:
    """Configure stdlib + structlog for JSON output to stdout."""
    logging.basicConfig(
        format="%(message)s",
        stream=sys.stdout,
        level=getattr(logging, level.upper()),
    )

    structlog.configure(
        processors=[
            structlog.contextvars.merge_contextvars,
            structlog.processors.add_log_level,
            structlog.processors.TimeStamper(fmt="iso", utc=True),
            _pii_scrubber,
            structlog.processors.format_exc_info,
            structlog.processors.JSONRenderer(),
        ],
        wrapper_class=structlog.make_filtering_bound_logger(getattr(logging, level.upper())),
        context_class=dict,
        logger_factory=structlog.PrintLoggerFactory(file=sys.stdout),
        cache_logger_on_first_use=True,
    )


def get_logger(name: str | None = None) -> Any:
    """Return a bound logger. Typed as Any to dodge structlog generic-typing friction."""
    return structlog.get_logger(name)
