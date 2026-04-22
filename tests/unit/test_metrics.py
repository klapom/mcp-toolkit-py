"""Tests for mcp_toolkit_py.metrics."""

from __future__ import annotations

import contextlib

import pytest

from mcp_toolkit_py import metrics as metrics_mod
from mcp_toolkit_py.metrics import init_metrics, render_metrics


@pytest.fixture(autouse=True)
def _reset_service_info(monkeypatch: pytest.MonkeyPatch) -> None:
    """Reset global so each test starts clean. Unregister any Info named mcp_service."""
    registry = metrics_mod.REGISTRY
    # Collect all collectors registered under the mcp_service Info's names
    to_remove = []
    for name in ("mcp_service", "mcp_service_info"):
        collector = registry._names_to_collectors.get(name)  # type: ignore[attr-defined]
        if collector is not None and collector not in to_remove:
            to_remove.append(collector)
    for collector in to_remove:
        with contextlib.suppress(KeyError):
            registry.unregister(collector)
    monkeypatch.setattr(metrics_mod, "_service_info", None)


def test_init_metrics_registers_and_render_contains_info() -> None:
    init_metrics("svc", "0.1.0")
    output = render_metrics()
    assert b"mcp_service_info" in output
    assert b'name="svc"' in output
    assert b'version="0.1.0"' in output


def test_init_metrics_is_idempotent() -> None:
    init_metrics("svc", "0.1.0")
    first = metrics_mod._service_info
    init_metrics("other", "9.9.9")  # second call should be no-op
    assert metrics_mod._service_info is first
    output = render_metrics()
    # First values persist
    assert b'name="svc"' in output
    assert b'name="other"' not in output


def test_render_metrics_returns_bytes() -> None:
    init_metrics("svc", "0.1.0")
    out = render_metrics()
    assert isinstance(out, bytes)
