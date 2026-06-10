"""Integration test for follow-up hints against a real FastMCP server (Sprint 15.7).

API under test:
    ``mcp_toolkit_py.hints.integration.install_followup_hints(mcp, rules_path, known_tools)
        -> FollowupHintsMiddleware``

Wraps ``mcp.call_tool`` to:
1. Run the original tool.
2. Build the matcher context: ``request_arguments`` are the call kwargs;
   ``result`` is the structured output dict (FastMCP's second tuple item)
   if it is a dict, else ``{}``.
3. Call ``middleware.select_hints``.
4. If hints are returned, modify the first ``TextContent`` of the content
   blocks in place via ``append_hints_to_text``, and attach the structured
   ``meta`` payload to that same block under ``"x-pommer/next_actions"``.
5. Return the modified ``(content_blocks, structured_output)`` tuple.

If the original return is not a tuple (older FastMCP shape, just blocks),
the wrapper still works and returns a list of blocks.

Tests use a synthetic in-process FastMCP server with two tools so the
heavy ot-knowledge RAG stack is NOT touched.
"""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml
from mcp.server.fastmcp import FastMCP


@pytest.fixture
def mini_mcp_and_yaml(tmp_path: Path):
    """Spin up a fresh FastMCP with two synthetic tools and a tiny rules.yaml."""

    rules_path = tmp_path / "rules.yaml"
    rules_path.write_text(
        yaml.safe_dump(
            {
                "version": 1,
                "tools": {
                    "echo_tool": {
                        "hints": [
                            {
                                "tool": "other_tool",
                                "rationale": "Folge-Beispiel",
                            }
                        ]
                    },
                },
            }
        )
    )

    mcp = FastMCP("hints-integration-test")

    @mcp.tool(name="echo_tool")
    async def echo_tool(message: str) -> str:
        return f"echo: {message}"

    @mcp.tool(name="other_tool")
    async def other_tool(x: int) -> str:
        return f"other={x}"

    return mcp, rules_path


def _import_integration():
    from mcp_toolkit_py.hints import integration

    return integration


# ──────────────────────────────────────────────────────────────────────────────
# Flag OFF → response byte-identical to the un-wrapped version
# ──────────────────────────────────────────────────────────────────────────────


async def test_flag_off_response_unchanged(mini_mcp_and_yaml, monkeypatch):
    """Regression-guard: with the flag off, install_followup_hints must NOT
    alter the response observed by callers."""
    mcp, rules_path = mini_mcp_and_yaml
    monkeypatch.delenv("MCP_FOLLOWUP_HINTS_ENABLED", raising=False)

    # Snapshot the un-wrapped response first
    baseline = await mcp.call_tool("echo_tool", {"message": "hi"})

    integration = _import_integration()
    integration.install_followup_hints(
        mcp, rules_path=rules_path, known_tools={"echo_tool", "other_tool"}
    )

    wrapped = await mcp.call_tool("echo_tool", {"message": "hi"})

    # Equal shape and equal text content; structured output too
    assert type(wrapped) is type(baseline)
    if isinstance(baseline, tuple):
        b_blocks, b_struct = baseline
        w_blocks, w_struct = wrapped
        assert [tc.text for tc in w_blocks] == [tc.text for tc in b_blocks]
        assert w_struct == b_struct
    else:
        assert [tc.text for tc in wrapped] == [tc.text for tc in baseline]


# ──────────────────────────────────────────────────────────────────────────────
# Flag ON → hints appended to the first TextContent
# ──────────────────────────────────────────────────────────────────────────────


async def test_flag_on_appends_hint_block(mini_mcp_and_yaml, monkeypatch):
    mcp, rules_path = mini_mcp_and_yaml
    monkeypatch.setenv("MCP_FOLLOWUP_HINTS_ENABLED", "true")

    integration = _import_integration()
    integration.install_followup_hints(
        mcp, rules_path=rules_path, known_tools={"echo_tool", "other_tool"}
    )

    result = await mcp.call_tool("echo_tool", {"message": "hi"})
    blocks = result[0] if isinstance(result, tuple) else result
    text = blocks[0].text

    # Original payload preserved
    assert text.startswith("echo: hi")
    # Hint block present
    assert "Mögliche nächste Schritte:" in text
    assert "1. other_tool" in text
    assert "Folge-Beispiel" in text


async def test_flag_on_attaches_meta(mini_mcp_and_yaml, monkeypatch):
    """The structured _meta payload must land on the first content block under
    the key ``x-pommer/next_actions``."""
    mcp, rules_path = mini_mcp_and_yaml
    monkeypatch.setenv("MCP_FOLLOWUP_HINTS_ENABLED", "true")

    integration = _import_integration()
    integration.install_followup_hints(
        mcp, rules_path=rules_path, known_tools={"echo_tool", "other_tool"}
    )

    result = await mcp.call_tool("echo_tool", {"message": "hi"})
    blocks = result[0] if isinstance(result, tuple) else result
    first_block = blocks[0]

    # TextContent has `meta` field (None when unused)
    assert first_block.meta is not None
    assert "x-pommer/next_actions" in first_block.meta
    actions = first_block.meta["x-pommer/next_actions"]
    assert isinstance(actions, list)
    assert len(actions) == 1
    assert actions[0]["tool"] == "other_tool"
    assert actions[0]["rationale"] == "Folge-Beispiel"


# ──────────────────────────────────────────────────────────────────────────────
# Kill-switch overrides truthy values
# ──────────────────────────────────────────────────────────────────────────────


async def test_forced_off_suppresses_hints(mini_mcp_and_yaml, monkeypatch):
    mcp, rules_path = mini_mcp_and_yaml
    monkeypatch.setenv("MCP_FOLLOWUP_HINTS_ENABLED", "forced_off")

    integration = _import_integration()
    integration.install_followup_hints(
        mcp, rules_path=rules_path, known_tools={"echo_tool", "other_tool"}
    )

    result = await mcp.call_tool("echo_tool", {"message": "hi"})
    blocks = result[0] if isinstance(result, tuple) else result
    text = blocks[0].text
    assert "Mögliche nächste Schritte" not in text
    assert blocks[0].meta is None or "x-pommer/next_actions" not in (blocks[0].meta or {})


# ──────────────────────────────────────────────────────────────────────────────
# Tools without rules are passed through unchanged
# ──────────────────────────────────────────────────────────────────────────────


async def test_tool_without_rule_passes_through(mini_mcp_and_yaml, monkeypatch):
    """other_tool has no rule entry — its response must not be altered even
    when the flag is on."""
    mcp, rules_path = mini_mcp_and_yaml
    monkeypatch.setenv("MCP_FOLLOWUP_HINTS_ENABLED", "true")

    integration = _import_integration()
    integration.install_followup_hints(
        mcp, rules_path=rules_path, known_tools={"echo_tool", "other_tool"}
    )

    result = await mcp.call_tool("other_tool", {"x": 7})
    blocks = result[0] if isinstance(result, tuple) else result
    text = blocks[0].text
    assert text == "other=7"
    assert blocks[0].meta is None or "x-pommer/next_actions" not in (blocks[0].meta or {})


# ──────────────────────────────────────────────────────────────────────────────
# Idempotency: installing twice should not double-wrap
# ──────────────────────────────────────────────────────────────────────────────


async def test_install_is_idempotent(mini_mcp_and_yaml, monkeypatch):
    mcp, rules_path = mini_mcp_and_yaml
    monkeypatch.setenv("MCP_FOLLOWUP_HINTS_ENABLED", "true")

    integration = _import_integration()
    integration.install_followup_hints(
        mcp, rules_path=rules_path, known_tools={"echo_tool", "other_tool"}
    )
    # Second install should be a no-op (or replace, but NOT double-wrap)
    integration.install_followup_hints(
        mcp, rules_path=rules_path, known_tools={"echo_tool", "other_tool"}
    )

    result = await mcp.call_tool("echo_tool", {"message": "hi"})
    blocks = result[0] if isinstance(result, tuple) else result
    text = blocks[0].text
    # The hint block must appear EXACTLY ONCE — not twice.
    assert text.count("Mögliche nächste Schritte:") == 1


# ──────────────────────────────────────────────────────────────────────────────
# Returns the middleware instance
# ──────────────────────────────────────────────────────────────────────────────


def test_install_returns_middleware(mini_mcp_and_yaml):
    """The returned object must be a FollowupHintsMiddleware so callers can
    inspect/configure it (e.g. unit-test wiring)."""
    mcp, rules_path = mini_mcp_and_yaml
    integration = _import_integration()
    from mcp_toolkit_py.hints.middleware import FollowupHintsMiddleware

    mw = integration.install_followup_hints(
        mcp, rules_path=rules_path, known_tools={"echo_tool", "other_tool"}
    )
    assert isinstance(mw, FollowupHintsMiddleware)


# ──────────────────────────────────────────────────────────────────────────────
# Critical regression: HTTP transport goes through request_handlers, NOT
# through mcp.call_tool. The wrap must hook both paths.
# ──────────────────────────────────────────────────────────────────────────────


async def test_lowlevel_request_handler_emits_hints(mini_mcp_and_yaml, monkeypatch):
    """The HTTP/stdio transports invoke
    ``mcp._mcp_server.request_handlers[CallToolRequest]`` directly. That
    handler captured FastMCP's original call_tool bound method at server
    construction — patching ``mcp.call_tool`` alone does NOT affect it.
    This test simulates the transport path so we catch any future regression
    where install_followup_hints stops hooking the lowlevel handler."""
    from mcp import types as mcp_types

    mcp, rules_path = mini_mcp_and_yaml
    monkeypatch.setenv("MCP_FOLLOWUP_HINTS_ENABLED", "true")

    integration = _import_integration()
    integration.install_followup_hints(
        mcp, rules_path=rules_path, known_tools={"echo_tool", "other_tool"}
    )

    # Build a CallToolRequest the way the transport would and route it through
    # the registered handler — same path the streamable-HTTP server takes.
    handler = mcp._mcp_server.request_handlers[mcp_types.CallToolRequest]
    req = mcp_types.CallToolRequest(
        method="tools/call",
        params=mcp_types.CallToolRequestParams(name="echo_tool", arguments={"message": "hi"}),
    )
    server_result = await handler(req)

    call_tool_result = server_result.root  # ServerResult wraps CallToolResult
    content = list(call_tool_result.content)
    assert content, "expected at least one content block from the handler"
    text = content[0].text
    assert "echo: hi" in text
    assert "Mögliche nächste Schritte:" in text
    assert "1. other_tool" in text

    # And the structured _meta payload must be on the same block
    assert content[0].meta is not None
    assert "x-pommer/next_actions" in content[0].meta


async def test_lowlevel_handler_unchanged_when_flag_off(mini_mcp_and_yaml, monkeypatch):
    """Flag off → handler must NOT emit hints (regression-guard for the HTTP path)."""
    from mcp import types as mcp_types

    mcp, rules_path = mini_mcp_and_yaml
    monkeypatch.delenv("MCP_FOLLOWUP_HINTS_ENABLED", raising=False)

    integration = _import_integration()
    integration.install_followup_hints(
        mcp, rules_path=rules_path, known_tools={"echo_tool", "other_tool"}
    )

    handler = mcp._mcp_server.request_handlers[mcp_types.CallToolRequest]
    req = mcp_types.CallToolRequest(
        method="tools/call",
        params=mcp_types.CallToolRequestParams(name="echo_tool", arguments={"message": "hi"}),
    )
    server_result = await handler(req)
    content = list(server_result.root.content)
    text = content[0].text
    assert "Mögliche nächste Schritte" not in text
    assert content[0].meta is None or "x-pommer/next_actions" not in (content[0].meta or {})
