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
