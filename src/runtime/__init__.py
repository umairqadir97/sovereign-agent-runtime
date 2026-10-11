"""Sovereign Agent Runtime.

Enterprise-grade, sovereign multi-agent execution runtime engineered for strict
data residency, deterministic boundary governance, and resilient state persistence.
"""

from runtime.config import SovereignConfig, get_settings
from runtime.graph import compile_sovereign_graph
from runtime.policies import (
    DataResidencyViolation,
    PolicyCheckResult,
    enforce_sovereign_boundary,
)
from runtime.state import AgentState, create_initial_state
from runtime.tools import MCPToolRegistry

__version__ = "0.1.0"

__all__ = [
    "AgentState",
    "create_initial_state",
    "SovereignConfig",
    "get_settings",
    "enforce_sovereign_boundary",
    "PolicyCheckResult",
    "DataResidencyViolation",
    "MCPToolRegistry",
    "compile_sovereign_graph",
]
