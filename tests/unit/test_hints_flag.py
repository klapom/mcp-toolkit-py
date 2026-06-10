"""Tests for the follow-up-hints env-flag resolver (Sprint 15.2).

API under test: ``mcp_toolkit_py.hints.flag.hints_enabled() -> bool``.

The resolver reads the env var ``MCP_FOLLOWUP_HINTS_ENABLED`` and returns:
- True when the value is in a defined truthy set (case-insensitive)
- False on any other value (including unset)
- False when the value is ``"forced_off"`` — this is a kill-switch that
  overrides any other interpretation, even if some future caller tries to
  pre-set the env to a truthy value, ``forced_off`` always wins.

Default is **False** (opt-in). This prevents accidental token-bloat on
deploys that haven't been audited for the new behavior.
"""

from __future__ import annotations

import pytest


def _import_flag():
    """Import lazily so the test file can be collected even before impl exists."""
    from mcp_toolkit_py.hints import flag

    return flag


# ── default state ────────────────────────────────────────────────────────────


def test_default_unset_returns_false(monkeypatch):
    monkeypatch.delenv("MCP_FOLLOWUP_HINTS_ENABLED", raising=False)
    assert _import_flag().hints_enabled() is False


def test_default_empty_string_returns_false(monkeypatch):
    monkeypatch.setenv("MCP_FOLLOWUP_HINTS_ENABLED", "")
    assert _import_flag().hints_enabled() is False


# ── truthy values ────────────────────────────────────────────────────────────


@pytest.mark.parametrize("value", ["1", "true", "True", "TRUE", "yes", "YES", "on", "ON"])
def test_truthy_values_enable(monkeypatch, value):
    monkeypatch.setenv("MCP_FOLLOWUP_HINTS_ENABLED", value)
    assert _import_flag().hints_enabled() is True


def test_truthy_with_surrounding_whitespace(monkeypatch):
    monkeypatch.setenv("MCP_FOLLOWUP_HINTS_ENABLED", "  true  ")
    assert _import_flag().hints_enabled() is True


# ── explicit falsy values ────────────────────────────────────────────────────


@pytest.mark.parametrize("value", ["0", "false", "False", "FALSE", "no", "NO", "off", "OFF"])
def test_falsy_values_disable(monkeypatch, value):
    monkeypatch.setenv("MCP_FOLLOWUP_HINTS_ENABLED", value)
    assert _import_flag().hints_enabled() is False


# ── garbage / unknown values default to False ────────────────────────────────


@pytest.mark.parametrize("value", ["maybe", "enabled?", "42", "null", "None"])
def test_unknown_values_return_false(monkeypatch, value):
    """Anything outside the defined truthy set is treated as False — safe default."""
    monkeypatch.setenv("MCP_FOLLOWUP_HINTS_ENABLED", value)
    assert _import_flag().hints_enabled() is False


# ── kill-switch ──────────────────────────────────────────────────────────────


def test_forced_off_returns_false(monkeypatch):
    monkeypatch.setenv("MCP_FOLLOWUP_HINTS_ENABLED", "forced_off")
    assert _import_flag().hints_enabled() is False


def test_forced_off_case_insensitive(monkeypatch):
    monkeypatch.setenv("MCP_FOLLOWUP_HINTS_ENABLED", "FORCED_OFF")
    assert _import_flag().hints_enabled() is False


def test_forced_off_with_whitespace(monkeypatch):
    monkeypatch.setenv("MCP_FOLLOWUP_HINTS_ENABLED", "  forced_off  ")
    assert _import_flag().hints_enabled() is False


# ── repeatability / no side effects ──────────────────────────────────────────


def test_multiple_calls_consistent(monkeypatch):
    """Resolver must read env on every call — no module-level caching of the value.

    Reason: ops needs to flip the flag at runtime (signal-driven config reload
    in some deploy strategies); caching would defeat that.
    """
    flag_mod = _import_flag()
    monkeypatch.setenv("MCP_FOLLOWUP_HINTS_ENABLED", "true")
    assert flag_mod.hints_enabled() is True
    monkeypatch.setenv("MCP_FOLLOWUP_HINTS_ENABLED", "false")
    assert flag_mod.hints_enabled() is False
    monkeypatch.setenv("MCP_FOLLOWUP_HINTS_ENABLED", "forced_off")
    assert flag_mod.hints_enabled() is False
