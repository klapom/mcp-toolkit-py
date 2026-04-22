"""Shared runtime for klapom Python MCP services.

Usage (per-service wiring):

    from mcp.server.fastmcp import FastMCP
    from mcp_toolkit_py.config import BaseServiceSettings
    from mcp_toolkit_py.http import create_dual_app, run_dual_surface
    from mcp_toolkit_py.logging import setup_logging, get_logger
    from mcp_toolkit_py.metrics import init_metrics
    from mcp_toolkit_py.stdio import run_stdio

    class Settings(BaseServiceSettings):
        ...  # service-specific fields

    mcp = FastMCP("my-service")
    # register tools ...
"""

__version__ = "0.1.0"
__all__ = ["__version__"]
