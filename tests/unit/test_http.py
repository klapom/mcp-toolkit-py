"""Tests for mcp_toolkit_py.http."""

from __future__ import annotations

from typing import Any
from unittest.mock import MagicMock

import pytest
from fastapi.testclient import TestClient
from mcp.server.fastmcp import FastMCP

from mcp_toolkit_py import http as http_mod
from mcp_toolkit_py import metrics as metrics_mod
from mcp_toolkit_py.http import _serialize, create_dual_app, run_dual_surface


@pytest.fixture
def mcp_server() -> FastMCP:
    mcp = FastMCP("test-svc")

    @mcp.tool()
    def echo(text: str) -> str:
        """Echo back the given text."""
        return f"echoed: {text}"

    @mcp.tool()
    def boom() -> str:
        """Always raises."""
        raise RuntimeError("kaboom")

    return mcp


@pytest.fixture
def client(mcp_server: FastMCP) -> TestClient:
    # Ensure metrics is initialised so /metrics has content
    if metrics_mod._service_info is None:
        metrics_mod.init_metrics("test-svc", "0.1.0")
    app = create_dual_app(
        mcp_server,
        service_name="test-svc",
        version="0.1.0",
        listen_port=32999,
        mcp_port=33999,
    )
    return TestClient(app)


def test_health_shape(client: TestClient) -> None:
    r = client.get("/health")
    assert r.status_code == 200
    body = r.json()
    assert body["service"] == "test-svc"
    assert body["version"] == "0.1.0"
    assert body["status"] == "ok"
    assert set(body["tools"]) == {"echo", "boom"}
    assert body["mcpEndpoint"] == "http://0.0.0.0:33999/mcp"


def test_tools_shape(client: TestClient) -> None:
    r = client.get("/tools")
    assert r.status_code == 200
    body = r.json()
    assert body["count"] == 2
    names = {t["name"] for t in body["tools"]}
    assert names == {"echo", "boom"}
    for t in body["tools"]:
        assert "description" in t
        assert "input_schema" in t


def test_metrics_content_type(client: TestClient) -> None:
    r = client.get("/metrics")
    assert r.status_code == 200
    assert r.headers["content-type"] == "text/plain; version=0.0.4; charset=utf-8"


def test_call_tool_success(client: TestClient) -> None:
    r = client.post("/tools/echo", json={"text": "hi"})
    assert r.status_code == 200
    body = r.json()
    assert body["ok"] is True
    assert any("echoed: hi" in c["text"] for c in body["content"])


def test_call_tool_unknown_404(client: TestClient) -> None:
    r = client.post("/tools/does_not_exist", json={})
    assert r.status_code == 404


def test_call_tool_bad_json_400(client: TestClient) -> None:
    r = client.post(
        "/tools/echo",
        content=b"not json at all",
        headers={"content-type": "application/json"},
    )
    assert r.status_code == 400


def test_call_tool_non_object_body_400(client: TestClient) -> None:
    r = client.post("/tools/echo", json=[1, 2, 3])
    assert r.status_code == 400


def test_call_tool_exception_500(client: TestClient) -> None:
    r = client.post("/tools/boom", json={})
    assert r.status_code == 500


def test_call_tool_empty_body_ok(mcp_server: FastMCP) -> None:
    # Tool with no required args; empty body should work
    mcp = FastMCP("t")

    @mcp.tool()
    def ping() -> str:
        """Ping."""
        return "pong"

    app = create_dual_app(
        mcp,
        service_name="t",
        version="0.1.0",
        listen_port=1,
        mcp_port=2,
    )
    c = TestClient(app)
    r = c.post("/tools/ping", content=b"")
    assert r.status_code == 200


def test_serialize_tuple_result() -> None:
    class Block:
        def __init__(self, text: str) -> None:
            self.text = text

    out = _serialize(([Block("a"), Block("b")], {"k": 1}))
    assert out["ok"] is True
    assert out["content"] == [{"type": "text", "text": "a"}, {"type": "text", "text": "b"}]
    assert out["structured"] == {"k": 1}


def test_serialize_non_iterable() -> None:
    out = _serialize(42)
    assert out["ok"] is True
    assert out["content"] == []
    assert out["structured"] is None


def test_create_dual_app_with_injected_logger(mcp_server: FastMCP) -> None:
    logger = MagicMock()
    app = create_dual_app(
        mcp_server,
        service_name="x",
        version="0.0.1",
        listen_port=1,
        mcp_port=2,
        logger=logger,
    )
    c = TestClient(app)
    # Trigger an exception path to verify logger is used
    r = c.post("/tools/boom", json={})
    assert r.status_code == 500
    logger.exception.assert_called_once()


async def test_run_dual_surface_invokes_gather(
    mcp_server: FastMCP, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Smoke-test: patch uvicorn.Server.serve + asyncio.gather to avoid actual binding."""

    served: list[Any] = []

    class FakeServer:
        def __init__(self, config: Any) -> None:
            self.config = config

        async def serve(self) -> None:
            served.append(self.config)

    monkeypatch.setattr(http_mod.uvicorn, "Server", FakeServer)

    await run_dual_surface(
        mcp_server,
        service_name="t",
        version="0.1.0",
        listen_port=12345,
        mcp_port=12346,
    )

    assert len(served) == 2
    ports = {s.port for s in served}
    assert ports == {12345, 12346}
