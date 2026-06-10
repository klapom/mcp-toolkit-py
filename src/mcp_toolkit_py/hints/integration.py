"""install_followup_hints — wraps FastMCP tool calls to emit follow-up hints (Sprint 15.7).

API
---
``install_followup_hints(mcp, rules_path, known_tools) -> FollowupHintsMiddleware``

How the wrap is applied
-----------------------
FastMCP registers its ``call_tool`` BOUND METHOD as the lowlevel
``request_handlers[CallToolRequest]`` at construction time. That means
just replacing ``mcp.call_tool`` on the instance affects only direct
callers — the HTTP/stdio transports go through the request-handler
closure and never see the new attribute.

We therefore re-register the lowlevel handler with a wrapped function
that calls the saved original and merges hints. We also replace
``mcp.call_tool`` for the few direct callers (and to keep the
unit-tests representative of behaviour).

Idempotency
-----------
The first install saves the *original* FastMCP ``call_tool`` bound
method on ``mcp._followup_hints_original_call_tool``. Subsequent
installs always chain to that original (never to a previously-installed
wrapper), so hints are appended exactly once regardless of how many
times ``install_followup_hints`` is called.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from mcp.server.fastmcp import FastMCP

from mcp_toolkit_py.hints.middleware import FollowupHintsMiddleware
from mcp_toolkit_py.hints.render import append_hints_to_text, format_hints_meta


def install_followup_hints(
    mcp: FastMCP,
    rules_path: Path | str,
    known_tools: set[str],
) -> FollowupHintsMiddleware:
    """Wrap tool-call response to append follow-up hints.

    Returns the FollowupHintsMiddleware instance for inspection.
    """
    middleware = FollowupHintsMiddleware(
        rules_path=rules_path,
        known_tools=known_tools,
    )

    # Idempotency: always chain to the first-seen original call_tool method.
    if getattr(mcp, "_followup_hints_original_call_tool", None) is None:
        mcp._followup_hints_original_call_tool = mcp.call_tool  # type: ignore[attr-defined]

    original_call_tool = mcp._followup_hints_original_call_tool  # type: ignore[attr-defined]

    async def _hinted_call_tool(name: str, arguments: dict[str, Any]) -> Any:
        result = await original_call_tool(name, arguments)

        # FastMCP's call_tool returns either a (content_blocks, structured) tuple
        # or just content_blocks (older shape).
        if isinstance(result, tuple) and len(result) == 2:
            content_blocks, structured_output = result[0], result[1]
            is_tuple = True
        else:
            content_blocks = result
            structured_output = {}
            is_tuple = False

        request_arguments = arguments if isinstance(arguments, dict) else {}
        result_ctx = structured_output if isinstance(structured_output, dict) else {}

        hints = middleware.select_hints(name, request_arguments, result_ctx)
        if not hints:
            return result

        blocks = list(content_blocks)
        if not blocks:
            return result

        first = blocks[0]
        # Defensive: only modify TextContent-like blocks (have .text attr).
        if not hasattr(first, "text"):
            return result

        new_text = append_hints_to_text(first.text, hints)
        meta_payload = format_hints_meta(hints)

        existing_meta: dict[str, Any] = dict(first.meta) if first.meta else {}
        existing_meta["x-pommer/next_actions"] = meta_payload

        new_first = first.model_copy(update={"text": new_text, "meta": existing_meta})
        new_blocks = [new_first, *blocks[1:]]

        if is_tuple:
            return (new_blocks, structured_output)
        return new_blocks

    # 1. Replace mcp.call_tool on the instance for direct callers.
    mcp.call_tool = _hinted_call_tool  # type: ignore[method-assign]

    # 2. Re-register the lowlevel request handler so HTTP/stdio transports
    #    pick up the wrap. FastMCP's _setup_handlers does the same dance
    #    once at construction time; we run it again to overwrite.
    mcp._mcp_server.call_tool(validate_input=False)(_hinted_call_tool)

    return middleware
