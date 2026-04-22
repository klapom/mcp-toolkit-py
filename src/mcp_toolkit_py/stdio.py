"""Stdio MCP transport entry.

Intended for Claude Desktop or local agents that speak stdio.
"""

from __future__ import annotations

from mcp.server.fastmcp import FastMCP

from .logging import setup_logging
from .metrics import init_metrics


def run_stdio(
    mcp: FastMCP,
    *,
    service_name: str,
    version: str,
    log_level: str = "info",
) -> None:
    """Set up logging + metrics + run the stdio MCP transport.

    Blocks until stdio closes.
    """
    setup_logging(log_level)
    init_metrics(service_name, version)
    mcp.run()
