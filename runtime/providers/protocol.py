#!/usr/bin/env python3
"""Provider protocol values and fail-closed eligibility rules."""

import datetime as dt
import json
import os
import re
import uuid
from dataclasses import dataclass, field

FREE_CLASSES = {
    "LOCAL_ZERO_COST",
    "FREE_HARD_STOP",
    "FREE_QUOTA",
    "FREE_PROTOTYPING",
    "FREE_CREDIT",
    "FREE_TRIAL",
}
PAID_CLASSES = {"PAID", "PAID_ONLY", "FREE_WITH_BILLING_RISK"}
FREE_EVIDENCE_STAGES = (
    "CATALOG_FREE",
    "ACCOUNT_FREE_ELIGIBLE",
    "DIRECT_LIVE_PROVEN",
    "ADAPTER_LIVE_PROVEN",
    "SELECTION_TO_EXECUTION_PROVEN",
)
TASK_CAPABILITIES = {
    "research": "RESEARCH_CAPABLE",
    "baseline": "RESEARCH_CAPABLE",
    "plan": "PLAN_CAPABLE",
    "build": "BUILD_CAPABLE",
    "fix": "BUILD_CAPABLE",
    "review": "REVIEW_CAPABLE",
    "verify": "REVIEW_CAPABLE",
}
ROUTING_FAILURE_CLASSES = {"TRANSPORT", "SEMANTIC", "HARNESS"}

# Provider identifiers and physical model identifiers are different domains.
# Model IDs come from a trusted provider/OpenCode catalog, but still need a
# bounded lexical check before they cross process and shell boundaries.
MODEL_IDENTIFIER_RE = re.compile(r"[A-Za-z0-9._/@:-]{1,128}\Z")


def now_utc():
    return dt.datetime.now(dt.timezone.utc).replace(microsecond=0).isoformat()


def new_id(prefix):
    return "%s-%s" % (prefix, uuid.uuid4().hex)


def credential_present(env_name):
    return bool(os.environ.get(env_name, "").strip())


def credential_inventory(env_names):
    return {name: credential_present(name) for name in env_names}


def parse_rate_limit_headers(headers):
    lower = {str(k).lower(): str(v) for k, v in (headers or {}).items()}
    return {
        "remaining_requests": lower.get("x-ratelimit-remaining-requests"),
        "remaining_tokens": lower.get("x-ratelimit-remaining-tokens"),
        "reset_requests": lower.get("x-ratelimit-reset-requests"),
        "reset_tokens": lower.get("x-ratelimit-reset-tokens"),
        "retry_after": lower.get("retry-after"),
    }


@dataclass
class ProviderRequest:
    provider: str
    model: str
    messages: list
    endpoint: str = ""
    task_class: str = "research"
    requested_capabilities: list = field(default_factory=list)
    privacy_class: str = "ALLOWED"
    routing_event_id: str = ""
    outbound_request_id: str = ""


@dataclass
class ProviderResponse:
    text: str
    provider: str
    requested_model: str
    resolved_model: str = ""
    actual_provider: str = ""
    actual_model: str = ""
    provider_request_id: str = ""
    usage: dict = field(default_factory=dict)
    actual_cost: float = None
    response_headers: dict = field(default_factory=dict)


@dataclass
class RouteRequest:
    provider: str = ""
    model: str = ""
    task_class: str = "research"
    requested_capabilities: list = field(default_factory=list)
    privacy_class: str = "ALLOWED"
    free_first: bool = True
    run_id: str = ""
    task_id: str = ""
    task_profile: dict = field(default_factory=dict)
    excluded_models: list = field(default_factory=list)


@dataclass
class ProviderExecution:
    decision: dict
    response: ProviderResponse
    failover_chain: list
    attempt_id: str
    execution_proof: dict


class ProviderFailure(RuntimeError):
    """Provider failure with explicit failover safety classification."""

    def __init__(self, message, status=None, retryable=False, uncertain=False, headers=None):
        super().__init__(message)
        self.status = status
        self.retryable = retryable
        self.uncertain = uncertain
        self.headers = headers or {}


class NoEligibleProvider(RuntimeError):
    code = "NO_ELIGIBLE_FREE_PROVIDER"


class DeepSeekPolicyViolation(RuntimeError):
    """Raised before any provider or worker invocation can be attempted."""

    code = "DEEPSEEK_RETIRED"


def normalize_usage(payload):
    usage = payload.get("usage") if isinstance(payload, dict) else {}
    usage = usage if isinstance(usage, dict) else {}
    return {
        "input_tokens": usage.get("prompt_tokens", usage.get("input_tokens", 0)) or 0,
        "output_tokens": usage.get("completion_tokens", usage.get("output_tokens", 0))
        or 0,
    }


def normalized_entry(provider, model, endpoint, **values):
    supplied_zero_cost = "zero_cost_verified" in values
    entry = {
        "provider": provider,
        "model": model,
        "endpoint": endpoint,
        "account_class": values.pop("account_class", "unknown"),
        "availability": values.pop("availability", False),
        "cost_class": values.pop("cost_class", "UNKNOWN"),
        "input_price": values.pop("input_price", None),
        "output_price": values.pop("output_price", None),
        "usage_terms_permit": values.pop("usage_terms_permit", False),
        "automatic_paid_fallback": values.pop("automatic_paid_fallback", True),
        "privacy_class": values.pop("privacy_class", "UNKNOWN"),
        "privacy_policy": values.pop("privacy_policy", {}),
        "health": values.pop("health", "UNAVAILABLE"),
        "quota_state": values.pop("quota_state", {}),
        "rate_limits": values.pop("rate_limits", {}),
        "free_evidence": values.pop("free_evidence", []),
        "free_eligible": False,
        "quarantined": values.pop("quarantined", False),
        "capabilities": values.pop("capabilities", {}),
        "context_length": values.pop("context_length", 0),
        "supports_tools": values.pop("supports_tools", False),
        "zero_cost_verified": values.pop("zero_cost_verified", False),
        "authenticated": values.pop("authenticated", True),
        "supports_vision": values.pop("supports_vision", False),
        "structured_output_score": values.pop("structured_output_score", 0.0),
        "tool_probe": values.pop("tool_probe", "UNKNOWN"),
        "vision_probe": values.pop("vision_probe", "UNKNOWN"),
        "score": values.pop("score", 0.0),
        "last_verified_at": values.pop("last_verified_at", now_utc()),
    }
    entry.update(values)
    if not supplied_zero_cost:
        entry["zero_cost_verified"] = bool(
            entry.get("input_price") == 0
            and entry.get("output_price") == 0
            and (
                entry.get("route_cost_proven") is True
                or "CATALOG_FREE" in set(entry.get("free_evidence") or [])
            )
        )
    free_eligibility(entry)
    return entry


def _privacy_ok(entry, requested):
    if entry.get("privacy_class") != "ALLOWED":
        return False
    if requested in ("PRIVATE_CODE", "PRIVATE_REPOSITORY"):
        policy = entry.get("privacy_policy") or {}
        return (
            policy.get("version") == "v1"
            and policy.get("approved") is True
            and bool(policy.get("provider_policy_ref"))
            and bool(policy.get("request_data_class"))
            and bool(policy.get("retention_class"))
        )
    return True


def free_eligibility(entry, privacy_class="ALLOWED", require_execution=True):
    # A retired provider/model is never eligible, even when an old catalog
    # snapshot, credential, alias, or local endpoint claims it is free.
    if is_deepseek_identifier(entry.get("provider"), entry.get("model")):
        entry.update({
            "free_eligible": False,
            "catalog_eligible": False,
            "router_eligible": False,
            "explicit_request_allowed": False,
            "fallback_allowed": False,
            "opencode_default": False,
        })
        return False
    stages = set(entry.get("free_evidence") or [])
    zero_priced = entry.get("input_price") == 0 and entry.get("output_price") == 0
    required_stages = set(FREE_EVIDENCE_STAGES) if require_execution else {
        "CATALOG_FREE", "ACCOUNT_FREE_ELIGIBLE"
    }
    groq_account_proven = not (
        entry.get("provider") == "groq"
        and not (
            str(entry.get("account_class", "unknown")).lower() == "free"
            and entry.get("account_class_evidence") == "PASS"
        )
    )
    eligible = (
        entry.get("cost_class") in FREE_CLASSES
        and zero_priced
        and entry.get("zero_cost_verified") is True
        and (
            entry.get("account_class") not in ("unknown", "")
            or entry.get("route_cost_proven") is True
        )
        and entry.get("usage_terms_permit") is True
        and entry.get("automatic_paid_fallback") is False
        and entry.get("availability") is True
        and entry.get("health") in ("HEALTHY", "DEGRADED")
        and entry.get("quota_state", {}).get("exhausted") is not True
        and _privacy_ok(entry, privacy_class)
        and groq_account_proven
        and required_stages.issubset(stages)
        and not entry.get("quarantined", False)
    )
    entry["free_eligible"] = bool(eligible)
    return bool(eligible)


def _safe_pre_execution(entry):
    return (
        entry.get("credential_valid", True) is True
        and entry.get("route_exists", True) is True
        and entry.get("availability") is True
        and entry.get("health") in ("HEALTHY", "DEGRADED")
        and entry.get("usage_terms_permit") is True
        and entry.get("automatic_paid_fallback") is False
        and entry.get("privacy_class") == "ALLOWED"
        and entry.get("quota_state", {}).get("exhausted") is not True
        and not entry.get("quarantined", False)
    )


def _hard_zero_route(entry):
    return (
        entry.get("cost_class") == "FREE_HARD_STOP"
        and entry.get("input_price") == 0
        and entry.get("output_price") == 0
        and entry.get("automatic_paid_fallback") is False
    )


def probe_eligibility(entry):
    """Pre-execution eligibility; execution proof is intentionally absent."""
    return bool(
        _safe_pre_execution(entry)
        and entry.get("cost_class") in FREE_CLASSES
        and entry.get("input_price") == 0
        and entry.get("output_price") == 0
        and entry.get("zero_cost_verified") is True
        and (
            entry.get("account_class") not in ("unknown", "")
            or entry.get("route_cost_proven") is True
        )
        and (_hard_zero_route(entry) or entry.get("route_cost_proven") is True)
        and entry.get("probe_attempted") is not True
    )


def promotion_eligibility(entry, decision=None):
    decision = decision or entry
    promoted = (
        entry.get("promoted_free_eligible") is True
        if decision is entry
        else decision.get("execution_proof") == "PASS"
        and decision.get("selection_to_execution_proven") is True
    )
    return bool(
        _safe_pre_execution(entry)
        and promoted
        and decision.get("probe_attempted") is True
        and decision.get("actual_cost_proof") in {
            "EXPLICIT_ZERO", "USAGE_ZERO", "CATALOG_HARD_ZERO"
        }
        and decision.get("actual_cost") in (None, 0, 0.0)
    )


def required_capabilities(request):
    """Return the hard capability gates for a route request."""
    required = list(request.requested_capabilities or [])
    capability = TASK_CAPABILITIES.get(request.task_class)
    if capability and capability not in required:
        required.append(capability)
    profile = request.task_profile or {}
    if profile.get("requires_code") and "BUILD_CAPABLE" not in required:
        required.append("BUILD_CAPABLE")
    if profile.get("requires_vision") and "VISION_CAPABLE" not in required:
        required.append("VISION_CAPABLE")
    if profile.get("requires_repository_tools") and "TOOL_CAPABLE" not in required:
        required.append("TOOL_CAPABLE")
    if profile.get("requires_structured_output") and "STRUCTURED_OUTPUT_CAPABLE" not in required:
        required.append("STRUCTURED_OUTPUT_CAPABLE")
    return required


def evaluate_route_admission(request, entry, state=None, catalog_member=True):
    """Evaluate the exact pre-execution route admission predicate.

    This is intentionally provider-free.  The returned reasons are stable
    diagnostic codes; dispatch may continue to expose its stable public error.
    """
    state = state or {
        "run_model_exclusions": set(),
        "task_model_exclusions": {},
        "provider_exclusions": set(),
    }
    reasons = []
    identity = "%s/%s" % (entry.get("provider"), entry.get("model"))
    task_id = request.task_id
    task_exclusions = set((state.get("task_model_exclusions") or {}).get(task_id, set()))
    caps = entry.get("capabilities") or {}
    profile = request.task_profile or {}
    required = required_capabilities(request)

    gates = {
        "CATALOG_MEMBER": catalog_member,
        "REQUESTED_PROVIDER_MATCH": not request.provider or request.provider == entry.get("provider"),
        "REQUESTED_MODEL_MATCH": not request.model or request.model == entry.get("model"),
        "NOT_DEEPSEEK": not is_deepseek_identifier(entry.get("provider"), entry.get("model")),
        "NOT_RUN_MODEL_EXCLUDED": identity not in set(state.get("run_model_exclusions") or set()),
        "NOT_TASK_MODEL_EXCLUDED": identity not in task_exclusions,
        "NOT_PROVIDER_EXCLUDED": entry.get("provider") not in set(state.get("provider_exclusions") or set()),
        "AUTHENTICATED": entry.get("authenticated", True) is not False,
        "AVAILABLE": entry.get("availability") is True,
        "HEALTH_ALLOWED": entry.get("health") in ("HEALTHY", "DEGRADED"),
        "PROBE_ELIGIBLE": probe_eligibility(entry),
        "PROMOTION_ELIGIBLE": promotion_eligibility(entry),
        "COST_CLASS_ALLOWED": entry.get("cost_class") in FREE_CLASSES,
        "PRIVACY_ALLOWED": _privacy_ok(entry, request.privacy_class),
        "QUOTA_AVAILABLE": entry.get("quota_state", {}).get("exhausted") is not True,
        "NOT_QUARANTINED": not entry.get("quarantined", False),
    }
    for capability in required:
        gates[capability] = caps.get(capability) is True
    if profile.get("requires_vision"):
        gates["VISION_GATE"] = caps.get("VISION_CAPABLE") is True and entry.get("vision_probe") != "FAIL"
    else:
        gates["VISION_GATE"] = True
    if profile.get("requires_repository_tools"):
        gates["TOOL_GATE"] = caps.get("TOOL_CAPABLE") is True and entry.get("tool_probe") == "PASS"
    else:
        gates["TOOL_GATE"] = True
    if profile.get("requires_long_context"):
        gates["CONTEXT_GATE"] = int(entry.get("context_length") or 0) >= int(profile.get("minimum_context_tokens") or 0)
    else:
        gates["CONTEXT_GATE"] = True
    if profile.get("requires_structured_output"):
        score = float(entry.get("structured_output_score") or 0)
        gates["STRUCTURED_OUTPUT_SCORE_OK"] = score >= 0.8
    else:
        gates["STRUCTURED_OUTPUT_SCORE_OK"] = True
    gates["PREEXECUTION_ELIGIBLE"] = gates["PROBE_ELIGIBLE"] or gates["PROMOTION_ELIGIBLE"]
    gates["FREE_EVIDENCE_ALLOWED"] = gates["PREEXECUTION_ELIGIBLE"]
    gate_reasons = []
    for name, passed in gates.items():
        if not passed:
            gate_reasons.append({
                "gate": name,
                "code": {
                    "AVAILABLE": "ROUTE_UNAVAILABLE",
                    "HEALTH_ALLOWED": "HEALTH_NOT_ALLOWED",
                    "AUTHENTICATED": "PROVIDER_NOT_AUTHENTICATED",
                    "NOT_DEEPSEEK": "DEEPSEEK_RETIRED",
                    "NOT_RUN_MODEL_EXCLUDED": "RUN_MODEL_EXCLUDED",
                    "NOT_TASK_MODEL_EXCLUDED": "TASK_MODEL_EXCLUDED",
                    "NOT_PROVIDER_EXCLUDED": "PROVIDER_EXCLUDED",
                    "PROBE_ELIGIBLE": "PROBE_NOT_ELIGIBLE",
                    "PROMOTION_ELIGIBLE": "PROMOTION_NOT_ELIGIBLE",
                    "STRUCTURED_OUTPUT_CAPABLE": "STRUCTURED_OUTPUT_CAPABILITY_MISSING",
                    "STRUCTURED_OUTPUT_SCORE_OK": "STRUCTURED_OUTPUT_SCORE_TOO_LOW",
                    "PLAN_CAPABLE": "PLAN_CAPABILITY_MISSING",
                    "COST_CLASS_ALLOWED": "COST_CLASS_NOT_FREE",
                    "PRIVACY_ALLOWED": "PRIVACY_NOT_ALLOWED",
                    "QUOTA_AVAILABLE": "QUOTA_EXHAUSTED",
                    "NOT_QUARANTINED": "MODEL_QUARANTINED",
                    "CATALOG_MEMBER": "MODEL_NOT_IN_CATALOG",
                    "REQUESTED_PROVIDER_MATCH": "PROVIDER_IDENTITY_MISMATCH",
                    "REQUESTED_MODEL_MATCH": "MODEL_IDENTITY_MISMATCH",
                    "VISION_GATE": "VISION_CAPABILITY_MISSING",
                    "TOOL_GATE": "TOOL_CAPABILITY_MISSING",
                    "CONTEXT_GATE": "CONTEXT_TOO_SHORT",
                }.get(name, name),
            })
    # Probe and promotion are alternative lifecycle proofs.  A missing
    # promotion proof is not a rejection when the pre-execution probe gate is
    # valid, and vice versa.
    reasons = [reason for reason in gate_reasons if not (
        (reason["gate"] == "PROMOTION_ELIGIBLE" and gates["PROBE_ELIGIBLE"])
        or (reason["gate"] == "PROBE_ELIGIBLE" and gates["PROMOTION_ELIGIBLE"])
        or reason["gate"] == "PREEXECUTION_ELIGIBLE"
        or reason["gate"] == "FREE_EVIDENCE_ALLOWED"
    )]
    # Derived gates are useful in diagnostics but should not duplicate a
    # second admission policy: final eligibility is their conjunction.
    alternative_gates = {"PROBE_ELIGIBLE", "PROMOTION_ELIGIBLE", "PREEXECUTION_ELIGIBLE", "FREE_EVIDENCE_ALLOWED"}
    eligible = bool(gates["PREEXECUTION_ELIGIBLE"] and all(
        passed for name, passed in gates.items() if name not in alternative_gates
    ))
    return {
        "eligible": bool(eligible),
        "reasons": reasons,
        "gate_reasons": gate_reasons,
        "decision_inputs": {
            "identity": identity,
            "required_capabilities": required,
            "gates": gates,
            "free_eligible": bool(entry.get("free_eligible")),
            "probe_eligibility": gates["PROBE_ELIGIBLE"],
            "promotion_eligibility": gates["PROMOTION_ELIGIBLE"],
        },
    }


def safe_id(value):
    return bool(re.match(r"^[A-Za-z0-9._/-]{1,128}$", str(value or "")))


def is_valid_model_identifier(value):
    """Validate the lexical shape of a catalog model ID.

    Catalog membership remains the authorization check.  This function only
    permits the identifier forms used by current provider catalogs and
    rejects controls, whitespace, and shell metacharacters before dispatch.
    """
    if not isinstance(value, str) or not value or len(value) > 128:
        return False
    if any(ord(char) < 32 or ord(char) == 127 for char in value):
        return False
    return MODEL_IDENTIFIER_RE.fullmatch(value) is not None


def is_deepseek_identifier(provider, model):
    return "deepseek" in ("%s/%s" % (provider or "", model or "")).lower()


def assert_runtime_model_allowed(provider, model):
    if is_deepseek_identifier(provider, model):
        raise DeepSeekPolicyViolation("DeepSeek is retired for Morpheus runtime agents")


def json_bytes(payload):
    return json.dumps(payload, separators=(",", ":")).encode("utf-8")
