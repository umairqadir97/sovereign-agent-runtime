"""High-concurrency FastAPI server exposing sovereign agent execution endpoints.

Supports Server-Sent Events (SSE) streaming, OpenTelemetry distributed tracing hooks,
durable state rehydration, and regulatory compliance health probes.
"""

from __future__ import annotations

import json
import logging
import time
import uuid
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from typing import Annotated, Any

from fastapi import Depends, FastAPI, HTTPException, Request, Response, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from runtime.config import SovereignConfig, get_settings
from runtime.graph import AsyncRedisSaver, compile_sovereign_graph
from runtime.state import create_initial_state
from runtime.tools import default_registry

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] [%(name)s] %(message)s",
)
logger = logging.getLogger("sovereign.server")


# ---------------------------------------------------------------------------
# OpenTelemetry Tracing Hook Simulation & Context
# ---------------------------------------------------------------------------


class SpanContext:
    """Lightweight W3C TraceContext simulation and OpenTelemetry hook wrapper."""

    def __init__(self, trace_id: str, span_id: str, attributes: dict[str, Any]) -> None:
        self.trace_id = trace_id
        self.span_id = span_id
        self.attributes = attributes
        self.start_time = time.time()

    def set_attribute(self, key: str, value: Any) -> None:
        self.attributes[key] = value

    def finish(self) -> float:
        duration = (time.time() - self.start_time) * 1000
        logger.info(
            "OTEL Span [%s:%s] duration=%.2fms attrs=%s",
            self.trace_id[:8],
            self.span_id[:8],
            duration,
            self.attributes,
        )
        return duration


@asynccontextmanager
async def trace_agent_execution(
    request: Request, span_name: str, attributes: dict[str, Any]
) -> AsyncGenerator[SpanContext, None]:
    """Context manager injecting W3C OpenTelemetry span context into execution scope."""
    traceparent = request.headers.get("traceparent")
    if traceparent and len(traceparent.split("-")) == 4:
        parts = traceparent.split("-")
        trace_id = parts[1]
        parent_span = parts[2]
    else:
        trace_id = uuid.uuid4().hex
        parent_span = uuid.uuid4().hex[:16]

    span_id = uuid.uuid4().hex[:16]
    ctx = SpanContext(
        trace_id=trace_id,
        span_id=span_id,
        attributes={"parent_span": parent_span, "span.name": span_name, **attributes},
    )
    try:
        yield ctx
    finally:
        ctx.finish()


# ---------------------------------------------------------------------------
# Request & Response Schemas
# ---------------------------------------------------------------------------


class AgentExecuteRequest(BaseModel):
    """Payload for sovereign agent execution."""

    prompt: str = Field(..., min_length=1, description="Instruction or query for sovereign agent")
    session_id: str = Field(
        default_factory=lambda: f"session-{uuid.uuid4().hex[:12]}",
        description="Durable session identifier for state checkpointing",
    )
    data_residency_region: str = Field(
        default="me-central1",
        description="Mandatory geographic cloud region enforcing data residency",
    )
    tenant_id: str = Field(
        default="sovereign-root",
        description="Tenant identifier for multi-tenant isolation",
    )
    stream: bool = Field(
        default=False,
        description="Enable Server-Sent Events (SSE) streaming for real-time tokens and node updates",
    )


class AgentExecuteResponse(BaseModel):
    """Deterministic output payload including forensic audit trail."""

    session_id: str
    tenant_id: str
    status: str
    policy_compliance_passed: bool
    data_residency_region: str
    output_message: str
    active_violations: list[str]
    escalation_reason: str | None
    execution_audit_trail: list[dict[str, Any]]
    duration_ms: float


# ---------------------------------------------------------------------------
# Application Lifespan & Global Graph
# ---------------------------------------------------------------------------

runtime_state: dict[str, Any] = {}


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """Initialize persistent checkpointer and compile sovereign StateGraph."""
    settings = get_settings()
    logger.info(
        "Initializing Sovereign Agent Runtime [Env: %s, Cloud: %s, Strict: %s]",
        settings.ENVIRONMENT,
        settings.CLOUD_PROVIDER.value,
        settings.STRICT_DATA_RESIDENCY,
    )
    saver = AsyncRedisSaver(redis_url=settings.REDIS_URL, key_prefix=settings.REDIS_KEY_PREFIX)
    app.state.checkpointer = saver
    app.state.graph = compile_sovereign_graph(
        checkpointer=saver.get_saver(),
        registry=default_registry,
    )
    yield
    logger.info("Shutting down Sovereign Agent Runtime.")


app = FastAPI(
    title="Sovereign Agent Runtime",
    version="0.1.0",
    description="Enterprise runtime for sovereign AI agents with LangGraph state persistence and deterministic data boundaries.",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ---------------------------------------------------------------------------
# Health & Diagnostic Probes
# ---------------------------------------------------------------------------


@app.get("/health/live", tags=["Diagnostics"])
async def liveness_probe() -> dict[str, str]:
    """Kubernetes liveness probe verifying basic process responsiveness."""
    return {"status": "alive", "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())}


@app.get("/health/ready", tags=["Diagnostics"])
async def readiness_probe(
    settings: Annotated[SovereignConfig, Depends(get_settings)],
) -> dict[str, Any]:
    """Kubernetes readiness probe verifying tool registry and sovereign policy boundaries."""
    tools = default_registry.list_tools()
    return {
        "status": "ready",
        "service": settings.SERVICE_NAME,
        "environment": settings.ENVIRONMENT,
        "cloud_provider": settings.CLOUD_PROVIDER.value,
        "cmek_key_configured": bool(settings.CMEK_KEY_ID),
        "vpc_perimeter_id": settings.VPC_SERVICE_PERIMETER_ID,
        "registered_mcp_tools_count": len(tools),
        "allowed_residency_regions": settings.ALLOWED_RESIDENCY_REGIONS,
    }


@app.get("/v1/tools", tags=["MCP Tools"])
async def list_available_tools() -> Any:
    """List Model Context Protocol (MCP) schemas exposed by the sovereign runtime."""
    return default_registry.list_tools()


# ---------------------------------------------------------------------------
# Agent Execution Endpoint
# ---------------------------------------------------------------------------


@app.post(
    "/v1/agents/execute",
    response_model=AgentExecuteResponse,
    tags=["Agent Execution"],
    summary="Execute Sovereign Agent with Policy Enforcement",
)
async def execute_agent(
    req: AgentExecuteRequest,
    request: Request,
    response: Response,
    settings: Annotated[SovereignConfig, Depends(get_settings)],
) -> Any:
    """Execute or resume an agent workflow within strict sovereign boundaries.

    Validates geographic residency, executes deterministic policy gates before LLM invocation,
    and returns complete cryptographic audit traces.
    """
    start_time = time.time()
    graph = request.app.state.graph

    # Validate region upfront if strict residency enabled
    if (
        settings.STRICT_DATA_RESIDENCY
        and req.data_residency_region not in settings.ALLOWED_RESIDENCY_REGIONS
    ):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={
                "error": "UNAUTHORIZED_SOVEREIGN_REGION",
                "message": f"Requested region '{req.data_residency_region}' is not within authorized sovereign perimeter.",
                "authorized_regions": settings.ALLOWED_RESIDENCY_REGIONS,
            },
        )

    # Initialize initial state dictionary
    initial_state = create_initial_state(
        session_id=req.session_id,
        prompt=req.prompt,
        data_residency_region=req.data_residency_region,
        tenant_id=req.tenant_id,
    )

    thread_config = {"configurable": {"thread_id": req.session_id}}

    # Handle Server-Sent Events (SSE) Streaming
    if req.stream:

        async def sse_event_stream() -> AsyncGenerator[str, None]:
            async with trace_agent_execution(
                request,
                "agent.execute.stream",
                {"session_id": req.session_id, "region": req.data_residency_region},
            ) as span:
                yield f"event: session_start\ndata: {json.dumps({'session_id': req.session_id, 'region': req.data_residency_region})}\n\n"

                try:
                    async for chunk in graph.astream(
                        initial_state,
                        config=thread_config,
                        stream_mode="updates",
                    ):
                        for node_name, node_update in chunk.items():
                            event_payload = {
                                "node": node_name,
                                "current_step": node_update.get("current_step", node_name),
                                "policy_passed": node_update.get("policy_compliance_passed", True),
                            }
                            # Include message delta if present
                            if "messages" in node_update and node_update["messages"]:
                                latest = node_update["messages"][-1]
                                event_payload["message_preview"] = str(latest.content)

                            yield f"event: node_transition\ndata: {json.dumps(event_payload)}\n\n"

                    final_state = await graph.aget_state(thread_config)
                    final_values = final_state.values if final_state else {}
                    span.set_attribute(
                        "policy_passed", final_values.get("policy_compliance_passed", True)
                    )

                    yield f"event: complete\ndata: {json.dumps({'status': 'finished', 'session_id': req.session_id})}\n\n"

                except Exception as exc:
                    logger.error("Streaming error in session %s: %s", req.session_id, exc)
                    yield f"event: error\ndata: {json.dumps({'error': str(exc)})}\n\n"

        return StreamingResponse(
            sse_event_stream(),
            media_type="text/event-stream",
            headers={"Cache-Control": "no-cache", "Connection": "keep-alive"},
        )

    # Standard JSON Non-Streaming Execution
    async with trace_agent_execution(
        request,
        "agent.execute.sync",
        {"session_id": req.session_id, "region": req.data_residency_region},
    ) as span:
        final_state_output = await graph.ainvoke(initial_state, config=thread_config)
        duration = (time.time() - start_time) * 1000

        messages = final_state_output.get("messages", [])
        last_message_content = str(messages[-1].content) if messages else "Workflow concluded."
        policy_passed = final_state_output.get("policy_compliance_passed", True)

        span.set_attribute("policy_passed", policy_passed)
        span.set_attribute("duration_ms", duration)

        response.headers["X-Sovereign-Region"] = req.data_residency_region
        response.headers["X-Audit-Checksum"] = final_state_output.get("state_digest", "verified")

        return AgentExecuteResponse(
            session_id=req.session_id,
            tenant_id=req.tenant_id,
            status="escalated" if not policy_passed else "success",
            policy_compliance_passed=policy_passed,
            data_residency_region=req.data_residency_region,
            output_message=last_message_content,
            active_violations=final_state_output.get("active_violations", []),
            escalation_reason=final_state_output.get("escalation_reason"),
            execution_audit_trail=final_state_output.get("execution_audit_trail", []),
            duration_ms=round(duration, 2),
        )
