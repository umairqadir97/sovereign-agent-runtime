"""Tier 2: State Graph Traversal & Loop Invariant Tests (Mocked/Enclave).

Verifies state machine reliability, deterministic transition invariants,
checkpoint serialization across threads, and human escalation fallback routing.
"""

from typing import Any

import pytest
from langchain_core.messages import HumanMessage
from langgraph.checkpoint.memory import MemorySaver

from runtime.graph import build_sovereign_graph, compile_sovereign_graph
from runtime.state import create_initial_state
from runtime.tools import default_registry


@pytest.mark.asyncio
async def test_graph_routes_to_human_escalation_on_violation() -> None:
    """Ensure state violating residency or DLP transitions strictly to human escalation, never tool worker."""
    graph = build_sovereign_graph()

    # State violating data residency with PII payload
    initial_state: dict[str, Any] = {
        "session_id": "violating-session-inv-01",
        "tenant_id": "sovereign-root",
        "messages": [HumanMessage(content="Run query with sensitive key 4532015099881234")],
        "data_residency_region": "me-central1",
        "policy_compliance_passed": True,
        "active_violations": [],
        "escalation_reason": None,
        "execution_audit_trail": [],
        "retry_count": 0,
        "current_step": "init",
        "state_digest": "seed_digest",
    }

    config = {"configurable": {"thread_id": "violating-session-inv-01"}}
    final_state = await graph.ainvoke(initial_state, config=config)

    # Invariants
    assert not final_state["policy_compliance_passed"]
    assert len(final_state["execution_audit_trail"]) >= 1
    assert "CRITICAL: Workflow paused" in final_state["messages"][-1].content
    assert final_state["current_step"] == "human_escalation"


@pytest.mark.asyncio
async def test_graph_prevents_infinite_cycles_and_terminates() -> None:
    """Verify that multi-step reasoning cycles terminate deterministically within iteration bounds."""
    saver = MemorySaver()
    graph = compile_sovereign_graph(checkpointer=saver, registry=default_registry)

    # Trigger tool execution which loops back to policy_gate
    initial_state = create_initial_state(
        session_id="session-cycle-bound-02",
        prompt="Please tokenize customer identity within enclave perimeter.",
        data_residency_region="me-central1",
    )
    config = {
        "configurable": {"thread_id": "session-cycle-bound-02"},
        "recursion_limit": 10,
    }

    final_state = await graph.ainvoke(initial_state, config=config)

    # Must complete cleanly without RecursionError or infinite loop
    assert final_state["policy_compliance_passed"] is True
    # The message history should have HumanMessage -> AIMessage (tool_call) -> ToolMessage -> final AIMessage
    assert len(final_state["messages"]) >= 3
    last_msg = final_state["messages"][-1]
    assert "concluded successfully" in str(last_msg.content) or "verified" in str(last_msg.content)


@pytest.mark.asyncio
async def test_graph_state_persistence_and_rehydration() -> None:
    """Verify that checkpoints serialize and deserialize without loss across consecutive invocations."""
    saver = MemorySaver()
    graph = compile_sovereign_graph(checkpointer=saver, registry=default_registry)
    thread_id = "durable-thread-persistence-test"
    config = {"configurable": {"thread_id": thread_id}}

    # Turn 1: Initial query
    state_turn_1 = create_initial_state(
        session_id=thread_id,
        prompt="Initial sovereign security query.",
        data_residency_region="me-central1",
    )
    await graph.ainvoke(state_turn_1, config=config)

    # Retrieve checkpoint directly from saver
    checkpoint_state = await graph.aget_state(config)
    assert checkpoint_state is not None
    assert checkpoint_state.values["session_id"] == thread_id
    assert checkpoint_state.values["policy_compliance_passed"] is True
    assert len(checkpoint_state.values["messages"]) >= 2

    # Turn 2: Subsequent message under identical thread_id
    follow_up_input = {
        "messages": [HumanMessage(content="Follow-up question on data encryption.")],
        "data_residency_region": "me-central1",
    }
    await graph.ainvoke(follow_up_input, config=config)

    # Validate state accumulated messages monotonically
    updated_checkpoint = await graph.aget_state(config)
    assert updated_checkpoint is not None
    assert len(updated_checkpoint.values["messages"]) >= 4
    assert len(updated_checkpoint.values["execution_audit_trail"]) >= 3
