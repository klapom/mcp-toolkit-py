"""Dual-surface HTTP: REST (32xxx) + MCP Streamable-HTTP (33xxx).

Both surfaces share the same ``FastMCP`` instance, so a tool registered
via ``@mcp.tool()`` is automatically reachable on all three surfaces
(this module's REST + MCP, and stdio).
"""

from __future__ import annotations

import asyncio
from typing import Any

import uvicorn
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import Response
from mcp.server.fastmcp import FastMCP

from .logging import get_logger
from .metrics import render_metrics


def _serialize(result: Any) -> dict[str, Any]:
    """Normalize FastMCP call_tool result into plain JSON. Handles (content, structured) tuple."""
    structured: Any = None
    content: Any = result
    if isinstance(result, tuple) and len(result) == 2:
        content, structured = result

    texts: list[str] = []
    try:
        for block in content or []:
            text = getattr(block, "text", None)
            if text is not None:
                texts.append(text)
    except TypeError:
        pass

    return {
        "ok": True,
        "content": [{"type": "text", "text": t} for t in texts],
        "structured": structured,
    }


def create_dual_app(
    mcp: FastMCP,
    *,
    service_name: str,
    version: str,
    listen_port: int,
    mcp_port: int,
    logger: Any | None = None,
) -> FastAPI:
    """Build the FastAPI REST app with /health, /metrics, /tools, /tools/{name}.

    Bound to ``mcp`` instance for tool listing + dispatch.
    """
    log = logger if logger is not None else get_logger(__name__)
    app = FastAPI(title=f"{service_name} REST", version=version)

    # ``listen_port`` is not used in routes but reserved for future extensions
    # (e.g. base-URL construction). Keep in signature for contract stability.
    _ = listen_port

    @app.get("/health")
    async def health() -> dict[str, Any]:
        tools = await mcp.list_tools()
        return {
            "service": service_name,
            "version": version,
            "status": "ok",
            "tools": [t.name for t in tools],
            "mcpEndpoint": f"http://0.0.0.0:{mcp_port}/mcp",
        }

    @app.get("/metrics")
    async def metrics() -> Response:
        return Response(
            content=render_metrics(),
            media_type="text/plain; version=0.0.4; charset=utf-8",
        )

    @app.get("/tools")
    async def list_tools() -> dict[str, Any]:
        tools = await mcp.list_tools()
        return {
            "count": len(tools),
            "tools": [
                {
                    "name": t.name,
                    "description": (t.description or "").strip().split("\n", 1)[0],
                    "input_schema": t.inputSchema,
                }
                for t in tools
            ],
        }

    @app.post("/tools/{tool_name}")
    async def call_tool(tool_name: str, request: Request) -> dict[str, Any]:
        try:
            body = await request.json() if await request.body() else {}
        except ValueError as e:
            raise HTTPException(status_code=400, detail=f"Invalid JSON: {e}") from e
        if not isinstance(body, dict):
            raise HTTPException(status_code=400, detail="Body must be a JSON object.")

        tools = await mcp.list_tools()
        if tool_name not in {t.name for t in tools}:
            raise HTTPException(status_code=404, detail=f"Unknown tool: {tool_name}")

        try:
            result = await mcp.call_tool(tool_name, body)
        except Exception as e:
            log.exception("tool_error", tool=tool_name)
            raise HTTPException(status_code=500, detail=str(e)) from e
        return _serialize(result)

    return app


async def run_dual_surface(
    mcp: FastMCP,
    *,
    service_name: str,
    version: str,
    listen_port: int,
    mcp_port: int,
    logger: Any | None = None,
) -> None:
    """Run REST + MCP Streamable-HTTP concurrently via asyncio.gather.

    REST on ``listen_port``, MCP on ``mcp_port`` at /mcp.
    Logs ``dual_surface_start`` event on startup.
    """
    log = logger if logger is not None else get_logger(__name__)
    rest_app = create_dual_app(
        mcp,
        service_name=service_name,
        version=version,
        listen_port=listen_port,
        mcp_port=mcp_port,
        logger=log,
    )
    mcp_app = mcp.streamable_http_app()

    rest_config = uvicorn.Config(
        rest_app,
        host="0.0.0.0",
        port=listen_port,
        log_config=None,
        access_log=False,
    )
    mcp_config = uvicorn.Config(
        mcp_app,
        host="0.0.0.0",
        port=mcp_port,
        log_config=None,
        access_log=False,
    )

    rest_server = uvicorn.Server(rest_config)
    mcp_server = uvicorn.Server(mcp_config)

    log.info(
        "dual_surface_start",
        service=service_name,
        version=version,
        rest_port=listen_port,
        mcp_port=mcp_port,
    )

    await asyncio.gather(rest_server.serve(), mcp_server.serve())
