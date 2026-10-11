"""Durable state definitions and reducer schemas for LangGraph execution.

Implements strict TypedDict typing with LangChain message accumulation and
immutable audit trail recording for regulatory and forensic compliance.
"""

from __future__ import annotations

import hashlib
import json
import time
from typing import Annotated, Any, TypedDict

from langchain_core.messages import BaseMessage, HumanMessage
from langgraph.graph.message import add_messages


def _audit_trail_reducer(
    current: list[dict[str, Any]], update: list[dict[str, Any]] | dict[str, Any]
) -> list[dict[str, Any]]:
    """Reducer that appends audit trail entries monotonically, preserving immutability."""
    existing = list(current) if current else []
    if isinstance(update, list):
        return existing + update
    return existing + [update]


class AgentState(TypedDict):
    """Durable state schema for sovereign agent graph execution.

    Designed for deterministic hydration across distributed workers and
    resilient checkpoint persistence in Redis.
    """

    # Primary workflow identifiers
    session_id: str
    tenant_id: str

    # Message sequence governed by add_messages reducer
    messages: Annotated[list[BaseMessage], add_messages]

    # Sovereign Cloud Governance
    data_residency_region: str
    policy_compliance_passed: bool
    active_violations: list[str]
    escalation_reason: str | None

    # Immutable forensic audit trail (monotonic appending)
    execution_audit_trail: Annotated[list[dict[str, Any]], _audit_trail_reducer]

    # Resilience & Flow Control
    retry_count: int
    current_step: str
    state_digest: str


def compute_state_digest(session_id: str, messages: list[BaseMessage], region: str) -> str:
    """Generate deterministic SHA-256 hash of core state attributes for tamper detection."""
    serialized_messages = [{"type": m.type, "content": str(m.content)} for m in messages]
    payload = json.dumps(
        {
            "session_id": session_id,
            "region": region,
            "messages": serialized_messages,
        },
        sort_keys=True,
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def record_audit_event(
    state: AgentState,
    stage: str,
    action: str,
    details: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Construct a structured, timestamped audit log event adhering to sovereignty standards."""
    now_epoch = time.time()
    event_data = {
        "timestamp_epoch": now_epoch,
        "timestamp_iso": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(now_epoch)),
        "session_id": state.get("session_id", "unknown"),
        "tenant_id": state.get("tenant_id", "unknown"),
        "stage": stage,
        "action": action,
        "region": state.get("data_residency_region", "unknown"),
        "details": details or {},
    }
    # Append tamper-proof event checksum
    event_checksum = hashlib.sha256(
        json.dumps(event_data, sort_keys=True).encode("utf-8")
    ).hexdigest()
    event_data["event_checksum"] = event_checksum
    return event_data


def create_initial_state(
    session_id: str,
    prompt: str,
    data_residency_region: str,
    tenant_id: str = "sovereign-root",
) -> AgentState:
    """Instantiate a validated, production-ready AgentState dictionary."""
    initial_messages: list[BaseMessage] = [HumanMessage(content=prompt)]
    digest = compute_state_digest(session_id, initial_messages, data_residency_region)

    init_audit_event = {
        "timestamp_epoch": time.time(),
        "timestamp_iso": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "session_id": session_id,
        "tenant_id": tenant_id,
        "stage": "initialization",
        "action": "session_created",
        "region": data_residency_region,
        "details": {"prompt_preview": prompt[:120]},
        "event_checksum": digest,
    }

    return {
        "session_id": session_id,
        "tenant_id": tenant_id,
        "messages": initial_messages,
        "data_residency_region": data_residency_region,
        "policy_compliance_passed": True,
        "active_violations": [],
        "escalation_reason": None,
        "execution_audit_trail": [init_audit_event],
        "retry_count": 0,
        "current_step": "init",
        "state_digest": digest,
    }
