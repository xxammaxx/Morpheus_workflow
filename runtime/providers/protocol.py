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
    actual_cost: float = 0.0
    response_headers: dict = field(default_factory=dict)


@dataclass
class RouteRequest:
    provider: str = ""
    model: str = ""
    task_class: str = "research"
    requested_capabilities: list = field(default_factory=list)
    privacy_class: str = "ALLOWED"
    free_first: bool = True


@dataclass
class ProviderExecution:
    decision: dict
    response: ProviderResponse
    failover_chain: list
    attempt_id: str
    execution_proof: dict


class ProviderFailure(RuntimeError):
    """Provider failure with explicit failover safety classification."""

    def __init__(self, message, status=None, retryable=False, uncertain=False):
        super().__init__(message)
        self.status = status
        self.retryable = retryable
        self.uncertain = uncertain


class NoEligibleProvider(RuntimeError):
    code = "NO_ELIGIBLE_FREE_PROVIDER"


def normalize_usage(payload):
    usage = payload.get("usage") if isinstance(payload, dict) else {}
    usage = usage if isinstance(usage, dict) else {}
    return {
        "input_tokens": usage.get("prompt_tokens", usage.get("input_tokens", 0)) or 0,
        "output_tokens": usage.get("completion_tokens", usage.get("output_tokens", 0))
        or 0,
    }


def normalized_entry(provider, model, endpoint, **values):
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
        "last_verified_at": values.pop("last_verified_at", now_utc()),
    }
    entry.update(values)
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


def free_eligibility(entry, privacy_class="ALLOWED"):
    stages = set(entry.get("free_evidence") or [])
    zero_priced = entry.get("input_price") == 0 and entry.get("output_price") == 0
    eligible = (
        entry.get("cost_class") in FREE_CLASSES
        and zero_priced
        and entry.get("account_class") not in ("unknown", "")
        and entry.get("usage_terms_permit") is True
        and entry.get("automatic_paid_fallback") is False
        and entry.get("availability") is True
        and entry.get("health") in ("HEALTHY", "DEGRADED")
        and entry.get("quota_state", {}).get("exhausted") is not True
        and _privacy_ok(entry, privacy_class)
        and set(FREE_EVIDENCE_STAGES).issubset(stages)
        and not entry.get("quarantined", False)
    )
    entry["free_eligible"] = bool(eligible)
    return bool(eligible)


def safe_id(value):
    return bool(re.match(r"^[A-Za-z0-9._/-]{1,128}$", str(value or "")))


def is_deepseek_identifier(provider, model):
    return "deepseek" in ("%s/%s" % (provider or "", model or "")).lower()


def json_bytes(payload):
    return json.dumps(payload, separators=(",", ":")).encode("utf-8")
