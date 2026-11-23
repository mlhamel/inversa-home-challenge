"""The FastAPI app exposes the FastMCP surface over streamable HTTP at /mcp."""

from __future__ import annotations

import json
from collections.abc import Iterator
from typing import Any

import pytest
from inversa.api.app import create_app
from inversa.api.config import Settings
from starlette.testclient import TestClient
from test_mcp_tools import MATCH_STALE, TS

ACCEPT: dict[str, str] = {"Accept": "application/json, text/event-stream"}
INIT_PARAMS: dict[str, Any] = {
    "protocolVersion": "2025-06-18",
    "capabilities": {},
    "clientInfo": {"name": "pytest", "version": "0"},
}
TOOL_IDS = [
    "analyze_downwind_impact",
    "get_station_timeseries",
    "find_worst_air_quality_events",
    "list_active_fires",
]
CALL_KEYS = ["content", "isError", "structuredContent"]


@pytest.fixture
def http_app(api_settings: Settings) -> Iterator[TestClient]:
    """Run the real app lifespan so the engine and the MCP session factory boot."""
    app = create_app(api_settings)
    with TestClient(app) as client:
        yield client


def test_initialize_negotiates_a_session(http_app: TestClient) -> None:
    """initialize on the mount returns an MCP session id and a result frame."""
    response = http_app.post(
        "/mcp/",
        json={"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": INIT_PARAMS},
        headers=ACCEPT,
    )
    assert response.status_code == 200
    assert "result" in _rpc_body(response)
    session_id = response.headers.get("mcp-session-id")
    assert isinstance(session_id, str) and len(session_id) > 0


def test_tools_list_exposes_the_four_tools(http_app: TestClient) -> None:
    """tools/list over the mounted HTTP transport names all four spec-04 tools."""
    headers = {**ACCEPT, "mcp-session-id": _session_id(http_app)}
    response = http_app.post(
        "/mcp/",
        json={"jsonrpc": "2.0", "id": 2, "method": "tools/list"},
        headers=headers,
    )
    assert response.status_code == 200
    body = _rpc_body(response)
    assert [tool["name"] for tool in body["result"]["tools"]] == TOOL_IDS


def test_tools_call_roundtrip_returns_structured_envelope(http_app: TestClient) -> None:
    """tools/call over HTTP streams back the same envelope the in-process client sees."""
    headers = {**ACCEPT, "mcp-session-id": _session_id(http_app)}
    response = http_app.post(
        "/mcp/",
        json={
            "jsonrpc": "2.0",
            "id": 3,
            "method": "tools/call",
            "params": {"name": "analyze_downwind_impact", "arguments": {"timestamp_iso": TS}},
        },
        headers=headers,
    )
    assert response.status_code == 200
    result = _rpc_body(response)["result"]
    assert list(result) == CALL_KEYS
    assert result["isError"] is False
    assert result["content"][0]["type"] == "text"
    payload = json.loads(result["content"][0]["text"])
    assert payload["matches"][0] == MATCH_STALE
    assert payload["evidence_refs"]["bbox_focus"] == [-122.0, 37.0, -122.0, 37.5]


def test_health_reports_liveness(api_settings: Settings) -> None:
    """GET /health answers ok without entering the analytical lifespan."""
    client = TestClient(create_app(api_settings))
    response = client.get("/health")
    client.close()
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def _session_id(client: TestClient) -> str:
    """initialize on the mount, send the initialized notification, return the session."""
    response = client.post(
        "/mcp/",
        json={"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": INIT_PARAMS},
        headers=ACCEPT,
    )
    session = response.headers.get("mcp-session-id")
    if not isinstance(session, str) or not session:
        raise AssertionError("initialize did not return an mcp-session-id header")
    client.post(
        "/mcp/",
        headers={**ACCEPT, "mcp-session-id": session},
        json={"jsonrpc": "2.0", "method": "notifications/initialized"},
    )
    return session


def _rpc_body(response: Any) -> dict[str, Any]:
    """Parse an SSE frame or a plain JSON body, whatever the transport picked."""
    body: dict[str, Any]
    if response.text.startswith("event:"):
        data_line = [line for line in response.text.splitlines() if line.startswith("data:")][-1]
        body = json.loads(data_line[5:])
    else:
        body = response.json()
    return body
