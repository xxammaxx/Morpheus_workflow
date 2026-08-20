#!/usr/bin/env python3
"""DeepSeek Model Adapter (HAMH Layer B, ADR H6) — official API semantics.

Implements REAL provider semantics verified against api-docs.deepseek.com on
2026-08-20. NO live network calls happen in this module; it builds valid
requests, validates protocol rules offline, and maps provider behavior.
A live smoke script (evidence/scripts/deepseek_live_smoke.py) can OPT-IN use
`to_http()` when credentials exist. No credentials -> no calls.

Verified live facts encoded here:
  - model IDs: ONLY "deepseek-v4-flash" (DeepSeek-V4-Flash-0731) and
    "deepseek-v4-pro" (DeepSeek-V4-Pro-0813). deepseek-chat/deepseek-reasoner
    RETIRED after 2026-07-24. Reasoning is a MODE, not a model.
  - thinking: {"type": "enabled"|"disabled"} (default enabled)
  - reasoning_effort: low|high|max (default high; medium/xhigh -> high)
  - temperature/top_p are silent no-ops in thinking mode
  - TOOL TURNS: reasoning_content MUST be passed back in all subsequent
    requests when `tools` is present, otherwise HTTP 400
  - tools: type function only, max 128; tool_choice none|auto|required|named
  - strict mode is BETA (requires base_url https://api.deepseek.com/beta)
  - context 1M, max output 384K
  - automatic prefix caching; usage.prompt_cache_hit_tokens /
    usage.prompt_cache_miss_tokens
  - errors by HTTP status only: 400/401/402/422/429/500/503
  - concurrency (account level): flash 2500, pro 500; optional user_id
  - concurrency is an ACCOUNT-RUNTIME configuration (mutable external fact),
    NOT an intrinsic model property — see provider_limits below
  - thinking-mode-dead parameters (temperature/top_p/presence_penalty/
    frequency_penalty) are NON_OPTIMIZABLE for the HAMH evolver: they have no
    causal effect on the model (documented no-ops)
  - HAMH evolution may ONLY optimize reasoning_effort over (high, max):
    low/medium/xhigh are compatibility values, not evolution dimensions
"""

import copy
import json
import re

MODEL_IDS = {
    "deepseek-v4-flash": {
        "full_version": "DeepSeek-V4-Flash-0731",
        "context_window": 1_000_000,
        "max_output": 384_000,
        "provider_limits": {
            "concurrency": {
                "documented_value": 2500,
                "scope": "account",
                "mutable_external_fact": True,
            }
        },
    },
    "deepseek-v4-pro": {
        "full_version": "DeepSeek-V4-Pro-0813",
        "context_window": 1_000_000,
        "max_output": 384_000,
        "provider_limits": {
            "concurrency": {
                "documented_value": 500,
                "scope": "account",
                "mutable_external_fact": True,
            }
        },
    },
}

RETIRED_MODEL_IDS = ("deepseek-chat", "deepseek-reasoner")

THINKING_TYPES = ("enabled", "disabled")
REASONING_EFFORTS = ("low", "high", "max")
REASONING_EFFORT_MAP = {"medium": "high", "xhigh": "high"}

# Kanonische Optimierungswerte fuer die HAMH-Evolution (order section 26):
# low/medium/xhigh sind Kompatibilitaets-Mappings und KEINE eigenstaendigen
# Evolutionsdimensionen. Nur high und max sind kausal unterscheidbar.
EVOLUTION_REASONING_EFFORTS = ("high", "max")

# Thinking-Mode-tote Parameter (offiziell dokumentiert als wirkungslos):
# temperature, top_p, presence_penalty, frequency_penalty. Sie duerfen aus
# Kompatibilitaetsgruenden gesendet werden, beeinflussen das Modell aber
# nicht. Der HAMH-Evolver darf daraus KEINE kausalen Schlussfolgerungen
# ziehen -> als NON_OPTIMIZABLE markiert und als Evolutionsdimension blockiert.
NON_OPTIMIZABLE_IN_THINKING_MODE = (
    "temperature",
    "top_p",
    "presence_penalty",
    "frequency_penalty",
)

BASE_URLS = {
    "openai": "https://api.deepseek.com",
    "anthropic": "https://api.deepseek.com/anthropic",
    "beta": "https://api.deepseek.com/beta",
}

# HTTP-status-only error mapping (no string error codes in current docs).
ERROR_TABLE = {
    400: {"name": "INVALID_FORMAT", "retryable": False, "action": "FIX_REQUEST"},
    401: {"name": "AUTHENTICATION_FAILS", "retryable": False, "action": "HALT"},
    402: {
        "name": "INSUFFICIENT_BALANCE",
        "retryable": False,
        "action": "HALT_ESCALATE",
    },
    422: {"name": "INVALID_PARAMETERS", "retryable": False, "action": "FIX_REQUEST"},
    429: {"name": "RATE_LIMIT_REACHED", "retryable": True, "action": "BACKOFF_RETRY"},
    500: {"name": "SERVER_ERROR", "retryable": True, "action": "BACKOFF_RETRY"},
    503: {"name": "SERVER_OVERLOADED", "retryable": True, "action": "BACKOFF_RETRY"},
}

TOOL_NAME_RE = re.compile(r"^[A-Za-z0-9_-]{1,64}$")
MAX_TOOLS = 128
MAX_USER_ID_LEN = 512

FINISH_REASONS = (
    "stop",
    "length",
    "tool_calls",
    "insufficient_system_resource",
    "content_filter",
)


class DeepSeekProtocolError(ValueError):
    """Offline protocol-rule violation (would be a provider 400/422 live)."""


def validate_model(model):
    if model in MODEL_IDS:
        return MODEL_IDS[model]
    if model in RETIRED_MODEL_IDS:
        raise DeepSeekProtocolError(
            "model %r RETIRED after 2026-07-24; use deepseek-v4-flash or "
            "deepseek-v4-pro (reasoning is a MODE now, not a model)" % model
        )
    raise DeepSeekProtocolError(
        "unknown model %r (known: %s)" % (model, ", ".join(sorted(MODEL_IDS)))
    )


def normalize_reasoning_effort(effort):
    if effort is None:
        return "high"
    effort = str(effort).lower()
    return REASONING_EFFORT_MAP.get(effort, effort)


def validate_evolution_reasoning_effort(effort):
    """Guard: HAMH evolution may ONLY optimize over (high, max).

    low/medium/xhigh are compatibility values (accepted for plain API
    requests via normalize_reasoning_effort) but must NEVER be treated as
    standalone HAMH evolution dimensions (order section 4/26). This guard
    accepts EXACTLY "high" or "max" (case-insensitive) and raises
    DeepSeekProtocolError for anything else. NOTE: medium/xhigh are NOT
    collapsed to high here — an evolver requesting them is treating a
    compatibility value as an evolution dimension, which is a governance
    violation. evolution.propose() enforces the same rule.
    """
    if effort is None:
        raise DeepSeekProtocolError(
            "reasoning_effort is required for HAMH evolution dimensions; "
            "canonical optimization values are %s"
            % ", ".join(EVOLUTION_REASONING_EFFORTS)
        )
    effort = str(effort).lower()
    if effort not in EVOLUTION_REASONING_EFFORTS:
        raise DeepSeekProtocolError(
            "reasoning_effort %r is not a HAMH evolution dimension; canonical "
            "optimization values are %s (low/medium/xhigh are compatibility "
            "values only)" % (effort, ", ".join(EVOLUTION_REASONING_EFFORTS))
        )
    return effort


def is_non_optimizable_in_thinking_mode(param):
    """True for parameters that are documented no-ops in thinking mode.

    The evolver must never treat these as causal harness variables
    (order section 5: THINKING.temperature etc. = NON_OPTIMIZABLE).
    """
    return param in NON_OPTIMIZABLE_IN_THINKING_MODE


def validate_thinking(thinking):
    if thinking not in THINKING_TYPES:
        raise DeepSeekProtocolError(
            "thinking must be one of %s, got %r" % (THINKING_TYPES, thinking)
        )


def validate_tools(tools, strict=False):
    """Validate the tools array against documented constraints."""
    if tools is None:
        return
    if not isinstance(tools, list):
        raise DeepSeekProtocolError("tools must be a list")
    if len(tools) > MAX_TOOLS:
        raise DeepSeekProtocolError(
            "max %d functions supported, got %d" % (MAX_TOOLS, len(tools))
        )
    for t in tools:
        if not isinstance(t, dict) or t.get("type") != "function":
            raise DeepSeekProtocolError("only type 'function' tools are supported")
        fn = t.get("function") or {}
        name = fn.get("name") or ""
        if not TOOL_NAME_RE.match(name):
            raise DeepSeekProtocolError(
                "invalid function name %r (a-z A-Z 0-9 _ -, max 64)" % name
            )
        if strict and not t.get("strict"):
            raise DeepSeekProtocolError(
                "strict mode requires strict:true on EVERY function"
            )


def build_chat_request(
    model,
    messages,
    thinking="enabled",
    reasoning_effort=None,
    tools=None,
    tool_choice=None,
    max_tokens=None,
    temperature=None,
    top_p=None,
    stream=False,
    beta=False,
    strict=False,
    user_id=None,
):
    """Build a chat-completions request dict per current official semantics.

    Raises DeepSeekProtocolError for documented rule violations instead of
    sending a request that the provider would reject (or silently ignore).
    """
    validate_model(model)
    validate_thinking(thinking)
    effort = normalize_reasoning_effort(reasoning_effort)
    if effort not in REASONING_EFFORTS:
        raise DeepSeekProtocolError(
            "reasoning_effort must be one of %s, got %r" % (REASONING_EFFORTS, effort)
        )
    if strict and not beta:
        raise DeepSeekProtocolError(
            "strict mode is Beta and requires base_url https://api.deepseek.com/beta"
        )
    validate_tools(tools, strict=strict)
    # LIVE-VERIFIED invariant (2026-08-20): thinking mode does NOT support
    # tool_choice="required" (provider: "Thinking mode does not support this
    # tool_choice", HTTP 400). Guard offline so the harness never sends a
    # request the provider would reject.
    if thinking == "enabled" and tool_choice == "required":
        raise DeepSeekProtocolError(
            "thinking mode does not support tool_choice='required' "
            "(live-verified provider invariant 2026-08-20); use 'auto'"
        )
    if max_tokens is not None:
        if max_tokens < 1:
            raise DeepSeekProtocolError("max_tokens must be >= 1")
        if max_tokens > MODEL_IDS[model]["max_output"]:
            raise DeepSeekProtocolError(
                "max_tokens %d exceeds documented max output %d"
                % (max_tokens, MODEL_IDS[model]["max_output"])
            )
    if user_id is not None and (
        len(str(user_id)) > MAX_USER_ID_LEN
        or not re.match(r"^[a-zA-Z0-9\-_]+$", str(user_id))
    ):
        raise DeepSeekProtocolError(
            "user_id must match [a-zA-Z0-9\\-_]+, max %d" % MAX_USER_ID_LEN
        )

    req = {
        "model": model,
        "messages": copy.deepcopy(messages),
        "thinking": {"type": thinking},
        "reasoning_effort": effort,
        "stream": bool(stream),
    }
    if tools is not None:
        req["tools"] = copy.deepcopy(tools)
    if tool_choice is not None:
        req["tool_choice"] = copy.deepcopy(tool_choice)
    if max_tokens is not None:
        req["max_tokens"] = max_tokens
    if temperature is not None:
        req["temperature"] = temperature  # no-op in thinking mode (documented)
    if top_p is not None:
        req["top_p"] = top_p  # no-op in thinking mode (documented)
    if user_id is not None:
        req["user_id"] = str(user_id)
    return req


def to_http(request, api_key, base="openai"):
    """Render a built request to (method, url, headers, body). The caller
    decides whether and how to execute it (opt-in live smoke only)."""
    if base not in BASE_URLS:
        raise DeepSeekProtocolError("unknown base %r" % base)
    url = BASE_URLS[base] + "/chat/completions"
    headers = {
        "Authorization": "Bearer %s" % api_key,
        "Content-Type": "application/json",
    }
    return "POST", url, headers, json.dumps(request)


def map_http_error(status_code):
    return dict(
        ERROR_TABLE.get(
            int(status_code),
            {
                "name": "UNKNOWN_HTTP_%s" % status_code,
                "retryable": False,
                "action": "HALT",
            },
        )
    )


def parse_usage(usage):
    """Extract cache/reasoning telemetry from a usage object."""
    usage = usage or {}
    return {
        "prompt_tokens": usage.get("prompt_tokens"),
        "completion_tokens": usage.get("completion_tokens"),
        "total_tokens": usage.get("total_tokens"),
        "prompt_cache_hit_tokens": usage.get("prompt_cache_hit_tokens", 0),
        "prompt_cache_miss_tokens": usage.get("prompt_cache_miss_tokens", 0),
        "reasoning_tokens": (
            (usage.get("completion_tokens_details") or {}).get("reasoning_tokens")
        ),
    }


def build_tool_message(tool_call_id, content):
    return {"role": "tool", "tool_call_id": tool_call_id, "content": content}


def build_assistant_prefix_message(content, reasoning_content=None):
    """Chat Prefix Completion (Beta): last message must be role:assistant with
    prefix:true; reasoning_content is used as the CoT input (Beta endpoint)."""
    msg = {"role": "assistant", "content": content, "prefix": True}
    if reasoning_content is not None:
        msg["reasoning_content"] = reasoning_content
    return msg


def extract_tool_calls(response):
    choice = ((response or {}).get("choices") or [{}])[0]
    msg = choice.get("message") or {}
    return msg.get("tool_calls") or []


def extract_reasoning_content(response):
    choice = ((response or {}).get("choices") or [{}])[0]
    msg = choice.get("message") or {}
    return msg.get("reasoning_content")


def validate_tool_turn_chain(messages):
    """Offline contract check for the documented 400 rule:

    "For requests carrying the tools parameter, the reasoning_content must
    be fully passed back to the API in all subsequent requests."

    Violation report: list of {index, reason}. Empty list = compliant.
    """
    violations = []
    msgs = list(messages or [])
    for i, msg in enumerate(msgs):
        if not isinstance(msg, dict):
            continue
        if msg.get("role") != "assistant":
            continue
        if not msg.get("tool_calls"):
            continue
        rc = msg.get("reasoning_content") or ""
        if not rc:
            # assistant called tools but produced no reasoning_content —
            # not itself a violation, but nothing to echo either
            continue
        # find the next assistant message AFTER the tool-result messages
        echoed = False
        for later in msgs[i + 1 :]:
            if later.get("role") == "tool":
                continue
            if later.get("role") == "assistant":
                if (later.get("reasoning_content") or "") == rc:
                    echoed = True
                break
        if not echoed:
            violations.append(
                {
                    "index": i,
                    "reason": (
                        "assistant tool-call turn %d: reasoning_content not "
                        "passed back in the next assistant turn -> provider "
                        "would return HTTP 400" % i
                    ),
                }
            )
    return violations
