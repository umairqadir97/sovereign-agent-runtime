"""Integration tests for LangGraph StateGraph conditional routing and state persistence."""

import pytest
from langgraph.checkpoint.memory import MemorySaver

from runtime.graph import compile_sovereign_graph
from runtime.state import create_initial_state
from runtime.tools import default_registry


@pytest.mark.asyncio
async def test_graph_compliant_flow() -> None:
    saver = MemorySaver()
    graph = compile_sovereign_graph(checkpointer=saver, registry=default_registry)

    state = create_initial_state(
        session_id="session-compliant-graph-01",
        prompt="Explain sovereign cloud data governance benefits.",
        data_residency_region="me-central1",
    )
    config = {"configurable": {"thread_id": "session-compliant-graph-01"}}

    final_state = await graph.ainvoke(state, config=config)

    assert final_state["policy_compliance_passed"] is True
    assert final_state["current_step"] in ["reasoning_engine", "init"]
    assert len(final_state["messages"]) >= 2
    assert "Execution verified within sovereign boundary" in str(
        final_state["messages"][-1].content
    )


@pytest.mark.asyncio
async def test_graph_policy_breach_routes_to_human_escalation() -> None:
    saver = MemorySaver()
    graph = compile_sovereign_graph(checkpointer=saver, registry=default_registry)

    # Prompt with PII breach (Qatar ID)
    state = create_initial_state(
        session_id="session-breach-graph-02",
        prompt="Verify identity for Qatar ID: 29801234567.",
        data_residency_region="me-central1",
    )
    config = {"configurable": {"thread_id": "session-breach-graph-02"}}

    final_state = await graph.ainvoke(state, config=config)

    assert final_state["policy_compliance_passed"] is False
    assert final_state["current_step"] == "human_escalation"
    assert "SOVEREIGN GOVERNANCE HALT" in str(final_state["messages"][-1].content)
    assert any("QATAR_NATIONAL_ID" in v for v in final_state["active_violations"])


@pytest.mark.asyncio
async def test_graph_tool_execution_flow() -> None:
    saver = MemorySaver()
    graph = compile_sovereign_graph(checkpointer=saver, registry=default_registry)

    state = create_initial_state(
        session_id="session-tool-graph-03",
        prompt="Please tokenize the customer identity within sovereign perimeter.",
        data_residency_region="me-central1",
    )
    config = {"configurable": {"thread_id": "session-tool-graph-03"}}

    final_state = await graph.ainvoke(state, config=config)

    assert final_state["policy_compliance_passed"] is True
    # Verify that tool execution audit event exists in trail
    audit_trail = final_state["execution_audit_trail"]
    actions = [evt.get("action") for evt in audit_trail]
    assert any("mcp_tool_executed" in str(a) for a in actions)
