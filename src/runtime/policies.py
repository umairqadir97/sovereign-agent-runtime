"""Deterministic policy enforcement and sovereign boundary validation layer.

Enforces zero egress of PII, sensitive credentials, and unapproved cross-border
data payloads before any downstream model invocation or tool interaction.
"""

from __future__ import annotations

import re
from typing import Any

from pydantic import BaseModel, Field

from runtime.config import get_settings
from runtime.state import AgentState, record_audit_event


class DataResidencyViolation(Exception):
    """Raised when an operation attempts unauthorized cross-border data transfer."""

    def __init__(self, region: str, violations: list[str]) -> None:
        self.region = region
        self.violations = violations
        super().__init__(
            f"Sovereignty boundary breach in region '{region}': {', '.join(violations)}"
        )


class PolicyCheckResult(BaseModel):
    """Deterministic result of a sovereignty boundary audit."""

    passed: bool
    region: str
    violations: list[str] = Field(default_factory=list)
    sanitized_preview: str | None = None
    remediation: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class SovereignBoundaryDecision:
    """Dual-mode decision container: behaves as bool in conditional checks,
    and unpacks as a tuple (passed, reason) for destructuring assertions.
    """

    def __init__(self, passed: bool, reason: str = "") -> None:
        self.passed = passed
        self.reason = reason

    def __bool__(self) -> bool:
        return self.passed

    def __iter__(self) -> Any:
        return iter((self.passed, self.reason))

    def __getitem__(self, index: int) -> Any:
        return (self.passed, self.reason)[index]

    def __eq__(self, other: object) -> bool:
        if isinstance(other, bool):
            return self.passed == other
        return super().__eq__(other)

    def __repr__(self) -> str:
        return f"SovereignBoundaryDecision(passed={self.passed}, reason='{self.reason}')"


# Deterministic Regex Signatures for Sovereign Regulatory Compliance
PII_PATTERNS: dict[str, re.Pattern[str]] = {
    # Qatar ID (QID): 11 digits, starts with 2 or 3 (century indicator)
    "QATAR_NATIONAL_ID": re.compile(r"\b[23]\d{10}\b"),
    # UAE Emirates ID: 784-XXXX-XXXXXXX-X format or 15 digits
    "UAE_EMIRATES_ID": re.compile(r"\b784-?[0-9]{4}-?[0-9]{7}-?[0-9]{1}\b"),
    # Saudi National ID / Iqama: 10 digits starting with 1 or 2
    "KSA_NATIONAL_ID": re.compile(r"\b[12]\d{9}\b"),
    # Credit Card Numbers (Visa, MC, Amex, Discover)
    "CREDIT_CARD_PAN": re.compile(
        r"\b(?:4[0-9]{12}(?:[0-9]{3})?|5[1-5][0-9]{14}|3[47][0-9]{13}|6(?:011|5[0-9]{2})[0-9]{12})\b"
    ),
    # International Bank Account Number (IBAN)
    "IBAN_CODE": re.compile(r"\b[A-Z]{2}[0-9]{2}[A-Z0-9]{11,30}\b"),
    # US Social Security Number (SSN)
    "US_SSN": re.compile(r"\b(?!000|666|9\d{2})\d{3}-(?!00)\d{2}-(?!0000)\d{4}\b"),
    # Cryptographic Private Keys
    "PRIVATE_KEY_HEADER": re.compile(r"-----BEGIN\s+(?:RSA|EC|DSA|OPENSSH|PGP|PRIVATE)\s+KEY-----"),
}

# Cross-border prohibited egress tokens (explicit exfiltration indicators)
PROHIBITED_EGRESS_TOKENS: list[str] = [
    "bypass_sovereignty",
    "egress_unencrypted",
    "force_cross_region_export",
    "exfiltrate_to_public_bucket",
]


def _luhn_checksum_valid(number_str: str) -> bool:
    """Verify Luhn algorithm for credit card number candidates."""
    digits = [int(c) for c in number_str if c.isdigit()]
    if len(digits) < 13:
        return False
    checksum = 0
    reversed_digits = digits[::-1]
    for i, d in enumerate(reversed_digits):
        if i % 2 == 1:
            doubled = d * 2
            checksum += doubled - 9 if doubled > 9 else doubled
        else:
            checksum += d
    return checksum % 10 == 0


def scan_for_pii(text: str) -> list[str]:
    """Scan raw text for PII patterns using deterministic regex expressions."""
    findings: list[str] = []

    for rule_name, pattern in PII_PATTERNS.items():
        matches = pattern.findall(text)
        if not matches:
            continue

        if rule_name == "CREDIT_CARD_PAN":
            # Extra validation via Luhn check to prevent false positives
            for match in matches:
                clean_num = match.replace("-", "").replace(" ", "")
                if _luhn_checksum_valid(clean_num):
                    findings.append(f"{rule_name} (Luhn verified)")
                    break
        else:
            findings.append(f"{rule_name} (count={len(matches)})")

    # Check for explicit policy evasion tokens
    lowered = text.lower()
    for token in PROHIBITED_EGRESS_TOKENS:
        if token in lowered:
            findings.append(f"UNAUTHORIZED_EGRESS_INTENT ({token})")

    return findings


async def enforce_sovereign_boundary(state: AgentState) -> SovereignBoundaryDecision:
    """Validate that execution strictly complies with data residency and zero-PII egress boundaries.

    Args:
        state: Active AgentState.

    Returns:
        SovereignBoundaryDecision: Evaluates as bool or unpacks as (passed, reason).
    """
    settings = get_settings()
    region = state.get("data_residency_region", "")
    violations: list[str] = []

    # 1. Geographic Data Residency Boundary Verification
    if settings.STRICT_DATA_RESIDENCY:
        if not region:
            violations.append("MISSING_DATA_RESIDENCY_REGION")
        elif region not in settings.ALLOWED_RESIDENCY_REGIONS:
            violations.append(
                f"Region '{region}' is unauthorized for sovereign compute (allowed: {settings.ALLOWED_RESIDENCY_REGIONS})"
            )

    # 2. Inspect Latest State Messages for Unencrypted PII or Egress Directives
    messages = state.get("messages", [])
    if messages:
        # Check the most recent message payload
        latest_message = messages[-1]
        content_str = str(latest_message.content)
        pii_violations = scan_for_pii(content_str)
        violations.extend(pii_violations)

    # 3. Formulate Policy Decision and Audit Event
    compliance_passed = len(violations) == 0

    if compliance_passed:
        reason = "Zero egress boundary verification passed"
    else:
        has_pii = any(
            any(k in v for k in ["CREDIT_CARD", "NATIONAL_ID", "SSN", "PRIVATE_KEY", "IBAN"])
            for v in violations
        )
        if has_pii:
            reason = f"Deterministic DLP intercepted: {'; '.join(violations)}"
        else:
            reason = f"Sovereignty boundary rejection: {'; '.join(violations)}"

    audit_details = {
        "residency_region": region,
        "compliance_passed": compliance_passed,
        "violations_detected": violations,
        "rules_evaluated": list(PII_PATTERNS.keys()) + ["GEOGRAPHIC_RESIDENCY_CHECK"],
    }

    audit_entry = record_audit_event(
        state=state,
        stage="policy_gate",
        action="sovereign_boundary_evaluation",
        details=audit_details,
    )

    # In-place state tracking
    state["policy_compliance_passed"] = compliance_passed
    state["active_violations"] = violations
    if not compliance_passed:
        state["escalation_reason"] = reason
    if "execution_audit_trail" in state and isinstance(state["execution_audit_trail"], list):
        state["execution_audit_trail"].append(audit_entry)

    return SovereignBoundaryDecision(compliance_passed, reason)
