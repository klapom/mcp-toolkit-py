# mcp-toolkit-py

Shared runtime for klapom Python MCP services. Extracts the per-service
boilerplate for logging, Prometheus metrics, dual-surface HTTP (REST +
MCP Streamable-HTTP), stdio MCP transport, and follow-up-hint emission
(v0.2.0+).

## Install

```bash
uv add "mcp-toolkit-py @ git+https://github.com/klapom/mcp-toolkit-py@v0.2.0"
```

## Follow-up Hints (v0.2.0)

Opt-in feature: after each FastMCP tool call, append a "Mögliche nächste
Schritte" block + structured `_meta["x-pommer/next_actions"]` to the
first text response. See `src/mcp_toolkit_py/hints/__init__.py` for the
public API; rule files are MCP-specific and live next to each consuming
package's code.

```python
from mcp_toolkit_py.hints import install_followup_hints

# After all @mcp.tool decorators have run:
install_followup_hints(
    mcp,
    rules_path=Path(__file__).parent / "hints" / "rules.yaml",
    known_tools={t for t in mcp._tool_manager._tools
                 if not t.startswith("internal_")},
)
```

Env-flag: `MCP_FOLLOWUP_HINTS_ENABLED=true` enables, `forced_off` is the
kill-switch, anything else (default) keeps responses untouched.

## Usage

```python
from mcp.server.fastmcp import FastMCP
from mcp_toolkit_py.config import BaseServiceSettings
from mcp_toolkit_py.http import run_dual_surface
from mcp_toolkit_py.logging import setup_logging, get_logger
from mcp_toolkit_py.metrics import init_metrics
from mcp_toolkit_py.stdio import run_stdio


class Settings(BaseServiceSettings):
    upstream_url: str = "https://example.com"


mcp = FastMCP("my-service")


@mcp.tool()
def hello(name: str) -> str:
    return f"Hello {name}"


# HTTP entry
def main_http() -> None:
    import asyncio

    settings = Settings()
    setup_logging(settings.log_level)
    init_metrics("my-service", "0.1.0")
    asyncio.run(
        run_dual_surface(
            mcp,
            service_name="my-service",
            version="0.1.0",
            listen_port=settings.listen_port,
            mcp_port=settings.mcp_port,
        )
    )


# Stdio entry
def main_stdio() -> None:
    settings = Settings()
    run_stdio(mcp, service_name="my-service", version="0.1.0", log_level=settings.log_level)
```

## Modules

- `config.BaseServiceSettings` — pydantic-settings base, process-env beats `.env`.
- `logging` — structlog JSON with PII-scrubber for known credential keys.
- `metrics` — Prometheus `mcp_service_info` + default collectors.
- `http.create_dual_app` / `http.run_dual_surface` — REST + MCP-HTTP.
- `stdio.run_stdio` — stdio MCP transport.
