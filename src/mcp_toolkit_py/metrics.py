"""Prometheus metrics (ADR-012).

Uses the global ``REGISTRY`` which auto-collects process + platform defaults
(CPU, RSS, fds, ``python_info``). Service identity is exposed via the
``mcp_service_info`` Info metric — parity with TS-toolkit's ``service`` label
is achieved at scrape-time via relabel_configs in Prometheus.
"""

from __future__ import annotations

from prometheus_client import REGISTRY, Info, generate_latest

_service_info: Info | None = None


def init_metrics(service_name: str, version: str) -> None:
    """Register ``mcp_service_info`` once per process."""
    global _service_info
    if _service_info is not None:
        return
    _service_info = Info("mcp_service", "Service identification", registry=REGISTRY)
    _service_info.info({"name": service_name, "version": version})


def render_metrics() -> bytes:
    """Render the default registry in Prometheus text format."""
    return generate_latest(REGISTRY)
