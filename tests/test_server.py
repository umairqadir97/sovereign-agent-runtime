"""API tests for FastAPI endpoints, SSE streaming, and health checks."""

import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
async def test_health_live_endpoint(async_client: AsyncClient) -> None:
    resp = await async_client.get("/health/live")
    assert resp.status_code == 200
    assert resp.json()["status"] == "alive"


@pytest.mark.asyncio
async def test_health_ready_endpoint(async_client: AsyncClient) -> None:
    resp = await async_client.get("/health/ready")
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "ready"
    assert data["registered_mcp_tools_count"] >= 2


@pytest.mark.asyncio
async def test_list_tools_endpoint(async_client: AsyncClient) -> None:
    resp = await async_client.get("/v1/tools")
    assert resp.status_code == 200
    tools = resp.json()
    assert len(tools) >= 2
    tool_names = [t["name"] for t in tools]
    assert "sovereign_identity_tokenizer" in tool_names


@pytest.mark.asyncio
async def test_agent_execute_compliant(async_client: AsyncClient) -> None:
    payload = {
        "prompt": "Evaluate sovereign data protection regulation guidelines.",
        "data_residency_region": "me-central1",
        "stream": False,
    }
    resp = await async_client.post("/v1/agents/execute", json=payload)
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "success"
    assert data["policy_compliance_passed"] is True
    assert len(data["active_violations"]) == 0
    assert "X-Sovereign-Region" in resp.headers


@pytest.mark.asyncio
async def test_agent_execute_unauthorized_region(async_client: AsyncClient) -> None:
    payload = {
        "prompt": "Hello unapproved region.",
        "data_residency_region": "us-east-1",  # Unauthorized
        "stream": False,
    }
    resp = await async_client.post("/v1/agents/execute", json=payload)
    assert resp.status_code == 400
    detail = resp.json()["detail"]
    assert detail["error"] == "UNAUTHORIZED_SOVEREIGN_REGION"


@pytest.mark.asyncio
async def test_agent_execute_policy_violation(async_client: AsyncClient) -> None:
    payload = {
        "prompt": "Citizen profile QID: 29801234567 needs export.",
        "data_residency_region": "me-central1",
        "stream": False,
    }
    resp = await async_client.post("/v1/agents/execute", json=payload)
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "escalated"
    assert data["policy_compliance_passed"] is False
    assert len(data["active_violations"]) > 0
    assert "SOVEREIGN GOVERNANCE HALT" in data["output_message"]


@pytest.mark.asyncio
async def test_agent_execute_sse_streaming(async_client: AsyncClient) -> None:
    payload = {
        "prompt": "Demonstrate sovereign SSE stream.",
        "data_residency_region": "me-central1",
        "stream": True,
    }
    resp = await async_client.post("/v1/agents/execute", json=payload)
    assert resp.status_code == 200
    assert "text/event-stream" in resp.headers["content-type"]
    text = resp.text
    assert "event: session_start" in text
    assert "event: complete" in text
