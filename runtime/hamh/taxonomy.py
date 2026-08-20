#!/usr/bin/env python3
"""HAMH failure taxonomy — EXTENDS the adapter failure classes, never replaces.

The AutoDev Harness v2 adapter classifies failures as:
    TEST_FAILURE, BUILD_FAILURE, LINT_FAILURE, CONTRACT_FAILURE,
    CONTEXT_FAILURE, PROVIDER_FAILURE, INFRA_FAILURE, TIMEOUT,
    SECURITY_BLOCK, UNKNOWN

HAMH adds a second, orthogonal meta-dimension (ADR H10):

    HARNESS_FAILURE     - model likely capable, but context/tooling/prompt/
                          state/workflow prevented success
    EXECUTION_FAILURE   - tool/environment/network/test-infra failed
    STRATEGY_FAILURE    - capabilities+information were sufficient, but the
                          chosen approach was unsuitable
    CAPABILITY_FAILURE  - evidence that the backbone cannot reliably solve
                          the task within reasonable budget

CAPABILITY_FAILURE must never be masked by endless harness evolution; it
feeds the existing routing/escalation ladder (RETRY_DENIED_* -> SPLIT).
"""

HAMH_CLASSES = (
    "HARNESS_FAILURE",
    "EXECUTION_FAILURE",
    "STRATEGY_FAILURE",
    "CAPABILITY_FAILURE",
)

# Adapter class -> default HAMH meta-class (base mapping).
BASE_MAP = {
    "TEST_FAILURE": "STRATEGY_FAILURE",
    "BUILD_FAILURE": "STRATEGY_FAILURE",
    "LINT_FAILURE": "STRATEGY_FAILURE",
    "CONTRACT_FAILURE": "HARNESS_FAILURE",
    "CONTEXT_FAILURE": "HARNESS_FAILURE",
    "PROVIDER_FAILURE": "EXECUTION_FAILURE",
    "INFRA_FAILURE": "EXECUTION_FAILURE",
    "TIMEOUT": "EXECUTION_FAILURE",
    "SECURITY_BLOCK": "EXECUTION_FAILURE",
    "UNKNOWN": "EXECUTION_FAILURE",
}

# Default: single runs are NOT sufficient evidence for permanent harness
# changes. Aggregated evidence or explicitly flagged experimental exceptions
# only (order section 16).
MIN_EVIDENCE_RUNS = 2


def classify(adapter_class, evidence=None):
    """Classify an adapter failure into the HAMH meta-dimension.

    evidence: dict with optional keys:
        failure_signature  (str)  canonical signature from the verifier
        attempt_count      (int)  number of attempts for this job
        same_fundamental_failure (bool)  same signature across deltas
        new_evidence       (list)  verifier-produced new information
        strategy_delta     (bool)  a justified strategy change was applied
        malformed_model_output (bool)  provider returned protocol-invalid data
        harness_blame      (bool)  explicit harness misconfiguration marker

    Returns (hamh_class, reason, escalate): escalate=True means the existing
    routing/escalation ladder must take over (CAPABILITY_FAILURE).
    """
    evidence = evidence or {}
    base = BASE_MAP.get(adapter_class, "EXECUTION_FAILURE")

    # Explicit harness misconfiguration -> HARNESS_FAILURE
    if evidence.get("harness_blame") or (
        adapter_class == "CONTRACT_FAILURE" and evidence.get("malformed_model_output")
    ):
        return ("HARNESS_FAILURE", "HARNESS_MISCONFIGURATION", False)

    # Malformed provider output is a harness/protocol problem, not a
    # capability problem (provider protocol error never condemns the model).
    if evidence.get("malformed_model_output"):
        return ("HARNESS_FAILURE", "MALFORMED_MODEL_OUTPUT", False)

    # Capability candidate: repeated fundamental failure despite justified
    # deltas, or explicit evidence flag.
    attempts = evidence.get("attempt_count", 1)
    same_failure = evidence.get("same_fundamental_failure")
    if same_failure and attempts >= MIN_EVIDENCE_RUNS:
        return (
            "CAPABILITY_FAILURE",
            "REPEATED_FUNDAMENTAL_FAILURE",
            True,
        )
    if evidence.get("capability_evidence"):
        return ("CAPABILITY_FAILURE", "CAPABILITY_EVIDENCE", True)

    # Strategy failure: tests failed but new information exists or a strategy
    # delta was applied -> the existing FIX/SPLIT ladder applies.
    if base == "STRATEGY_FAILURE":
        if evidence.get("new_evidence") or evidence.get("strategy_delta"):
            return ("STRATEGY_FAILURE", "FIXABLE_WITH_DELTA", False)
        # First failure without information gain -> still strategy territory
        # for the verifier; the retry policy decides.
        return ("STRATEGY_FAILURE", "FIRST_FAILURE", False)

    return (base, "BASE_MAP", False)


def capability_bound(hamh_class):
    """True if the failure hits the backbone capability bound."""
    return hamh_class == "CAPABILITY_FAILURE"
