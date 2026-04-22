"""Tests for mcp_toolkit_py.stdio."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from mcp_toolkit_py import stdio as stdio_mod
from mcp_toolkit_py.stdio import run_stdio


def test_run_stdio_calls_setup_metrics_and_run(monkeypatch: pytest.MonkeyPatch) -> None:
    setup_mock = MagicMock()
    metrics_mock = MagicMock()
    monkeypatch.setattr(stdio_mod, "setup_logging", setup_mock)
    monkeypatch.setattr(stdio_mod, "init_metrics", metrics_mock)

    mcp = MagicMock()

    run_stdio(mcp, service_name="svc", version="1.2.3", log_level="debug")

    setup_mock.assert_called_once_with("debug")
    metrics_mock.assert_called_once_with("svc", "1.2.3")
    mcp.run.assert_called_once_with()


def test_run_stdio_default_log_level(monkeypatch: pytest.MonkeyPatch) -> None:
    setup_mock = MagicMock()
    monkeypatch.setattr(stdio_mod, "setup_logging", setup_mock)
    monkeypatch.setattr(stdio_mod, "init_metrics", MagicMock())

    mcp = MagicMock()
    run_stdio(mcp, service_name="x", version="y")
    setup_mock.assert_called_once_with("info")
