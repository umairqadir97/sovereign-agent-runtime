"""Unit tests for Model Context Protocol (MCP) tool registry and circuit breaker."""

import pytest
from pydantic import BaseModel, Field

from runtime.tools import CircuitBreaker, CircuitState, MCPToolRegistry


class SampleInput(BaseModel):
    value: int = Field(..., gt=0)
    label: str


@pytest.mark.asyncio
async def test_mcp_registry_registration_and_execution() -> None:
    registry = MCPToolRegistry()

    @registry.register(
        name="test_doubler",
        description="Doubles the input value",
        args_schema=SampleInput,
    )
    async def test_doubler(payload: SampleInput, context: dict) -> dict:
        return {"doubled": payload.value * 2, "label": payload.label}

    # Verify MCP schema export
    specs = registry.list_tools()
    assert len(specs) == 1
    assert specs[0]["name"] == "test_doubler"
    assert "properties" in specs[0]["inputSchema"]

    # Valid execution
    resp = await registry.execute_tool("test_doubler", {"value": 21, "label": "test"})
    assert resp["status"] == "success"
    assert resp["result"]["doubled"] == 42


@pytest.mark.asyncio
async def test_mcp_tool_validation_error() -> None:
    registry = MCPToolRegistry()

    @registry.register(
        name="test_validator",
        description="Validates positive integers",
        args_schema=SampleInput,
    )
    async def test_validator(payload: SampleInput, context: dict) -> dict:
        return {"status": "ok"}

    # Invalid payload (value <= 0)
    resp = await registry.execute_tool("test_validator", {"value": -5, "label": "invalid"})
    assert resp["status"] == "validation_error"
    assert "details" in resp


@pytest.mark.asyncio
async def test_circuit_breaker_tripping() -> None:
    cb = CircuitBreaker(failure_threshold=3, recovery_timeout_seconds=2.0)
    assert cb.state == CircuitState.CLOSED

    cb.record_failure()
    cb.record_failure()
    assert cb.state == CircuitState.CLOSED

    cb.record_failure()  # 3rd failure reaches threshold
    assert cb.state == CircuitState.OPEN

    allowed, cooldown = cb.can_execute()
    assert allowed is False
    assert cooldown > 0.0
