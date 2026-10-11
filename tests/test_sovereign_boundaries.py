"""Tier 1: Sovereign Boundary & Policy Gate Tests (Deterministic).

Verifies strict geographic data residency enforcement and deterministic DLP
(Data Loss Prevention) boundary gates before any LLM inference or tool execution.
"""

from typing import Any

import pytest
from langchain_core.messages import HumanMessage

from runtime.policies import enforce_sovereign_boundary


@pytest.mark.asyncio
async def test_policy_gate_blocks_unauthorized_region() -> None:
    """Ensure payloads destined for unaccredited jurisdictions are rejected immediately."""
    state: dict[str, Any] = {
        "session_id": "test-session-1",
        "messages": [HumanMessage(content="Process financial transfer")],
        "data_residency_region": "US-EAST",  # Unauthorized sovereign region
        "policy_compliance_passed": False,
        "execution_audit_trail": [],
        "retry_count": 0,
    }
    passed, reason = await enforce_sovereign_boundary(state)  # type: ignore[arg-type]
    assert not passed
    assert "unauthorized for sovereign compute" in reason.lower()
    assert state["policy_compliance_passed"] is False
    assert len(state["active_violations"]) >= 1


@pytest.mark.asyncio
async def test_policy_gate_intercepts_pii_egress() -> None:
    """Ensure deterministic DLP intercepts unmasked payment card tokens."""
    state: dict[str, Any] = {
        "session_id": "test-session-2",
        "messages": [HumanMessage(content="User credit card is 4532015099881234")],
        "data_residency_region": "me-central1",
        "policy_compliance_passed": False,
        "execution_audit_trail": [],
        "retry_count": 0,
    }
    passed, reason = await enforce_sovereign_boundary(state)  # type: ignore[arg-type]
    assert not passed
    assert "Deterministic DLP intercepted" in reason
    assert state["policy_compliance_passed"] is False


@pytest.mark.asyncio
async def test_policy_gate_allows_valid_payload() -> None:
    """Ensure clean payloads within accredited sovereign regions pass without hindrance."""
    state: dict[str, Any] = {
        "session_id": "test-session-3",
        "messages": [HumanMessage(content="Generate a quarterly summary report")],
        "data_residency_region": "me-central1",
        "policy_compliance_passed": False,
        "execution_audit_trail": [],
        "retry_count": 0,
    }
    passed, reason = await enforce_sovereign_boundary(state)  # type: ignore[arg-type]
    assert passed
    assert state["policy_compliance_passed"] is True
    assert len(state["active_violations"]) == 0


@pytest.mark.asyncio
async def test_policy_gate_blocks_national_id_leakage() -> None:
    """Ensure national identity numbers (e.g. Qatar QID) trigger sovereign DLP gate."""
    state: dict[str, Any] = {
        "session_id": "test-session-4",
        "messages": [HumanMessage(content="Verification for Qatar citizen with QID 29801234567")],
        "data_residency_region": "me-central1",
        "policy_compliance_passed": False,
        "execution_audit_trail": [],
        "retry_count": 0,
    }
    passed, reason = await enforce_sovereign_boundary(state)  # type: ignore[arg-type]
    assert not passed
    assert "Deterministic DLP intercepted" in reason
    assert any("QATAR_NATIONAL_ID" in v for v in state["active_violations"])


@pytest.mark.asyncio
async def test_policy_gate_audit_trail_integrity() -> None:
    """Verify that every policy evaluation records an immutable cryptographic audit record."""
    state: dict[str, Any] = {
        "session_id": "test-session-audit-trail",
        "messages": [HumanMessage(content="Execute enclave query")],
        "data_residency_region": "me-central1",
        "policy_compliance_passed": False,
        "execution_audit_trail": [],
        "retry_count": 0,
    }
    passed, _ = await enforce_sovereign_boundary(state)  # type: ignore[arg-type]
    assert passed
    assert len(state["execution_audit_trail"]) == 1
    audit_event = state["execution_audit_trail"][0]
    assert audit_event["stage"] == "policy_gate"
    assert "event_checksum" in audit_event
    assert audit_event["region"] == "me-central1"
