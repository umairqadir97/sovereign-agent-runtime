"""Unit tests for deterministic sovereign boundary policies and PII scanning."""

import pytest

from runtime.policies import enforce_sovereign_boundary, scan_for_pii
from runtime.state import create_initial_state


def test_pii_scanner_clean_text() -> None:
    clean_text = "What is the capital of Qatar? Please summarize the regional market forecast."
    findings = scan_for_pii(clean_text)
    assert len(findings) == 0


def test_pii_scanner_qatar_id() -> None:
    # Qatar National ID: 11 digits starting with 2 or 3
    text_with_qid = "Citizen ID is 29801234567 for processing."
    findings = scan_for_pii(text_with_qid)
    assert any("QATAR_NATIONAL_ID" in f for f in findings)


def test_pii_scanner_uae_emirates_id() -> None:
    # UAE Emirates ID pattern
    text_with_uae_id = "Emirates ID card: 784-1990-1234567-1 recorded."
    findings = scan_for_pii(text_with_uae_id)
    assert any("UAE_EMIRATES_ID" in f for f in findings)


def test_pii_scanner_prohibited_egress_intent() -> None:
    malicious_text = "Please force_cross_region_export to external storage"
    findings = scan_for_pii(malicious_text)
    assert any("UNAUTHORIZED_EGRESS_INTENT" in f for f in findings)


@pytest.mark.asyncio
async def test_enforce_sovereign_boundary_compliant_state() -> None:
    state = create_initial_state(
        session_id="test-clean-01",
        prompt="Analyze internal inventory levels within the sovereign database.",
        data_residency_region="me-central1",
    )
    result = await enforce_sovereign_boundary(state)
    assert result
    assert state["policy_compliance_passed"] is True
    assert len(state["active_violations"]) == 0
    assert len(state["execution_audit_trail"]) >= 2  # init + policy_gate


@pytest.mark.asyncio
async def test_enforce_sovereign_boundary_unauthorized_region() -> None:
    state = create_initial_state(
        session_id="test-unauthorized-region",
        prompt="Hello sovereign world.",
        data_residency_region="us-east-1",  # Not in allowed sovereign regions
    )
    result = await enforce_sovereign_boundary(state)
    assert not result
    assert state["policy_compliance_passed"] is False
    assert any("unauthorized" in v.lower() for v in state["active_violations"])
    assert state["escalation_reason"] is not None


@pytest.mark.asyncio
async def test_enforce_sovereign_boundary_pii_breach() -> None:
    state = create_initial_state(
        session_id="test-pii-breach",
        prompt="Process verification for user with QID 29501234567 immediately.",
        data_residency_region="me-central1",
    )
    result = await enforce_sovereign_boundary(state)
    assert not result
    assert state["policy_compliance_passed"] is False
    assert any("QATAR_NATIONAL_ID" in v for v in state["active_violations"])
