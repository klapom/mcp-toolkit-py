"""Tests for mcp_toolkit_py.config."""

from __future__ import annotations

import pytest

from mcp_toolkit_py.config import BaseServiceSettings


def test_defaults_load(monkeypatch: pytest.MonkeyPatch, tmp_path) -> None:  # type: ignore[no-untyped-def]
    # Ensure no stray .env in cwd affects the test
    monkeypatch.chdir(tmp_path)
    s = BaseServiceSettings()
    assert s.listen_port == 32000
    assert s.mcp_port == 33000
    assert s.log_level == "info"


def test_subclass_with_custom_field_env_override(monkeypatch: pytest.MonkeyPatch, tmp_path) -> None:  # type: ignore[no-untyped-def]
    monkeypatch.chdir(tmp_path)

    class MySettings(BaseServiceSettings):
        upstream_url: str = "https://default.example"

    monkeypatch.setenv("UPSTREAM_URL", "https://override.example")
    monkeypatch.setenv("LISTEN_PORT", "32700")
    s = MySettings()
    assert s.upstream_url == "https://override.example"
    assert s.listen_port == 32700


def test_extra_ignored(monkeypatch: pytest.MonkeyPatch, tmp_path) -> None:  # type: ignore[no-untyped-def]
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("COMPLETELY_UNKNOWN_FIELD", "whatever")
    # Should not raise
    s = BaseServiceSettings()
    assert s.listen_port == 32000
