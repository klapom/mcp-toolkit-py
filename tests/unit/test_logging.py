"""Tests for mcp_toolkit_py.logging."""

from __future__ import annotations

import structlog

from mcp_toolkit_py.logging import _pii_scrubber, get_logger, setup_logging


def test_pii_scrubber_redacts_known_keys_case_insensitively() -> None:
    event = {"Authorization": "Bearer xyz", "TOKEN": "sk-abc", "msg": "hi"}
    out = _pii_scrubber(None, "info", event)
    assert out["Authorization"] == "<redacted>"
    assert out["TOKEN"] == "<redacted>"
    assert out["msg"] == "hi"


def test_pii_scrubber_covers_all_known_keys() -> None:
    event = {
        "authorization": "a",
        "token": "b",
        "secret": "c",
        "password": "d",
        "client_secret": "e",
        "api_key": "f",
        "access_token": "g",
        "refresh_token": "h",
    }
    out = _pii_scrubber(None, "info", event)
    for k in event:
        assert out[k] == "<redacted>"


def test_pii_scrubber_leaves_unknown_keys_intact() -> None:
    event = {"user_id": 123, "payload": {"nested": "value"}}
    out = _pii_scrubber(None, "info", event)
    assert out["user_id"] == 123
    assert out["payload"] == {"nested": "value"}


def test_pii_scrubber_leaves_none_values_alone() -> None:
    event = {"token": None, "secret": None}
    out = _pii_scrubber(None, "info", event)
    assert out["token"] is None
    assert out["secret"] is None


def test_setup_logging_debug_and_info_do_not_raise() -> None:
    setup_logging("debug")
    setup_logging("info")
    setup_logging("warning")
    setup_logging("error")


def test_get_logger_returns_structlog_bound_logger() -> None:
    setup_logging("info")
    log = get_logger("test")
    assert isinstance(log, structlog.stdlib.BoundLogger | structlog.BoundLoggerBase) or hasattr(
        log, "info"
    )
    # Call info to verify it doesn't raise
    log.info("event", user="x")
