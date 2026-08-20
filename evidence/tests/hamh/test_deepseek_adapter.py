#!/usr/bin/env python3
"""DeepSeek Model Adapter contract tests (T3, ADR H6).

Offline contract tests of the verified official API semantics
(api-docs.deepseek.com, 2026-08-20). NO live network calls.

Run: python3 evidence/tests/hamh/test_deepseek_adapter.py
"""

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "..", "runtime"))

from hamh import deepseek_adapter as ds  # noqa: E402

PASS = 0
FAIL = 0


def check(name, cond, detail=""):
    global PASS, FAIL
    if cond:
        PASS += 1
        print("PASS %s" % name)
    else:
        FAIL += 1
        print("FAIL %s %s" % (name, detail))


def expect_protocol_error(name, fn):
    try:
        fn()
        check(name, False, "expected DeepSeekProtocolError")
    except ds.DeepSeekProtocolError:
        check(name, True)


def main():
    # --- model IDs: only deepseek-v4-flash and deepseek-v4-pro exist
    check(
        "DS_MODEL_FLASH",
        ds.validate_model("deepseek-v4-flash")["full_version"]
        == "DeepSeek-V4-Flash-0731",
    )
    check(
        "DS_MODEL_PRO",
        ds.validate_model("deepseek-v4-pro")["full_version"] == "DeepSeek-V4-Pro-0813",
    )
    expect_protocol_error(
        "DS_RETIRED_CHAT_REJECTED", lambda: ds.validate_model("deepseek-chat")
    )
    expect_protocol_error(
        "DS_RETIRED_REASONER_REJECTED",
        lambda: ds.validate_model("deepseek-reasoner"),
    )
    expect_protocol_error(
        "DS_UNKNOWN_MODEL_REJECTED", lambda: ds.validate_model("gpt-4")
    )

    # --- thinking mode is a MODE, not a model; effort mapping
    req = ds.build_chat_request(
        "deepseek-v4-flash",
        [{"role": "user", "content": "hi"}],
        thinking="enabled",
        reasoning_effort="medium",  # mapped to high
    )
    check("DS_THINKING_ENABLED", req["thinking"] == {"type": "enabled"})
    check("DS_EFFORT_MEDIUM_MAPPED_HIGH", req["reasoning_effort"] == "high")
    req = ds.build_chat_request(
        "deepseek-v4-flash", [], thinking="disabled", reasoning_effort="low"
    )
    check("DS_THINKING_DISABLED", req["thinking"] == {"type": "disabled"})
    check("DS_EFFORT_LOW", req["reasoning_effort"] == "low")
    expect_protocol_error(
        "DS_BAD_THINKING",
        lambda: ds.build_chat_request("deepseek-v4-flash", [], thinking="maybe"),
    )

    # --- context window and max output documented limits
    check(
        "DS_CONTEXT_1M",
        ds.MODEL_IDS["deepseek-v4-flash"]["context_window"] == 1_000_000,
    )
    check(
        "DS_MAX_OUTPUT_384K", ds.MODEL_IDS["deepseek-v4-flash"]["max_output"] == 384_000
    )
    expect_protocol_error(
        "DS_MAX_TOKENS_CAP",
        lambda: ds.build_chat_request("deepseek-v4-flash", [], max_tokens=999_999),
    )

    # --- tools: function-only, max 128, name pattern, tool_choice
    tools = [
        {
            "type": "function",
            "function": {"name": "read_file", "parameters": {"type": "object"}},
        }
    ]
    req = ds.build_chat_request(
        "deepseek-v4-flash", [], tools=tools, tool_choice="required"
    )
    check("DS_TOOLS_PASSED", req["tools"] == tools and req["tool_choice"] == "required")
    expect_protocol_error(
        "DS_TOOL_BAD_TYPE",
        lambda: ds.build_chat_request(
            "deepseek-v4-flash", [], tools=[{"type": "code_interpreter"}]
        ),
    )
    expect_protocol_error(
        "DS_TOOL_BAD_NAME",
        lambda: ds.build_chat_request(
            "deepseek-v4-flash",
            [],
            tools=[{"type": "function", "function": {"name": "bad name!"}}],
        ),
    )
    expect_protocol_error(
        "DS_TOOL_TOO_MANY",
        lambda: ds.build_chat_request(
            "deepseek-v4-flash",
            [],
            tools=[
                {"type": "function", "function": {"name": "f%d" % i}}
                for i in range(129)
            ],
        ),
    )

    # --- strict mode requires the Beta base URL
    expect_protocol_error(
        "DS_STRICT_REQUIRES_BETA",
        lambda: ds.build_chat_request(
            "deepseek-v4-flash", [], tools=tools, strict=True, beta=False
        ),
    )
    req = ds.build_chat_request(
        "deepseek-v4-flash",
        [],
        tools=[{**tools[0], "strict": True}],
        strict=True,
        beta=True,
    )
    check("DS_STRICT_BETA_OK", req["tools"][0]["strict"] is True)
    expect_protocol_error(
        "DS_STRICT_MISSING_PER_FN",
        lambda: ds.build_chat_request(
            "deepseek-v4-flash", [], tools=tools, strict=True, beta=True
        ),
    )

    # --- THE 400 RULE: reasoning_content must be echoed across tool turns
    assistant_tool_turn = {
        "role": "assistant",
        "content": None,
        "reasoning_content": "REASONING_BLOCK_42",
        "tool_calls": [
            {
                "id": "call-1",
                "type": "function",
                "function": {"name": "read_file", "arguments": "{}"},
            }
        ],
    }
    tool_result = {"role": "tool", "tool_call_id": "call-1", "content": "file content"}
    # compliant chain: next assistant turn carries the reasoning_content
    compliant = [
        {"role": "user", "content": "task"},
        assistant_tool_turn,
        tool_result,
        {
            **assistant_tool_turn,
            "content": "done",
            "tool_calls": None,
            "reasoning_content": "REASONING_BLOCK_42",
        },
    ]
    check("DS_400_RULE_COMPLIANT", ds.validate_tool_turn_chain(compliant) == [])
    # violating chain: reasoning_content missing in the follow-up turn
    violating = [
        {"role": "user", "content": "task"},
        assistant_tool_turn,
        tool_result,
        {"role": "assistant", "content": "done", "reasoning_content": None},
    ]
    v = ds.validate_tool_turn_chain(violating)
    check("DS_400_RULE_VIOLATION_DETECTED", len(v) == 1 and v[0]["index"] == 1)

    # --- errors keyed by HTTP status only
    e = ds.map_http_error(429)
    check("DS_ERR_429", e["name"] == "RATE_LIMIT_REACHED" and e["retryable"])
    e = ds.map_http_error(402)
    check(
        "DS_ERR_402",
        e["name"] == "INSUFFICIENT_BALANCE" and e["action"] == "HALT_ESCALATE",
    )
    e = ds.map_http_error(422)
    check("DS_ERR_422", e["name"] == "INVALID_PARAMETERS" and not e["retryable"])
    e = ds.map_http_error(503)
    check("DS_ERR_503", e["name"] == "SERVER_OVERLOADED" and e["retryable"])

    # --- cache telemetry parsing (prompt_cache_hit/miss_tokens)
    u = ds.parse_usage(
        {
            "prompt_tokens": 100,
            "completion_tokens": 50,
            "total_tokens": 150,
            "prompt_cache_hit_tokens": 80,
            "prompt_cache_miss_tokens": 20,
            "completion_tokens_details": {"reasoning_tokens": 30},
        }
    )
    check("DS_CACHE_HIT", u["prompt_cache_hit_tokens"] == 80)
    check("DS_CACHE_MISS", u["prompt_cache_miss_tokens"] == 20)
    check("DS_REASONING_TOKENS", u["reasoning_tokens"] == 30)

    # --- concurrency limits documented (account level)
    check(
        "DS_CONCURRENCY_FLASH",
        ds.MODEL_IDS["deepseek-v4-flash"]["concurrency_limit"] == 2500,
    )
    check(
        "DS_CONCURRENCY_PRO",
        ds.MODEL_IDS["deepseek-v4-pro"]["concurrency_limit"] == 500,
    )

    # --- chat prefix completion (Beta) message shape
    msg = ds.build_assistant_prefix_message(
        "continue here", reasoning_content="CoT so far"
    )
    check(
        "DS_PREFIX_MSG",
        msg
        == {
            "role": "assistant",
            "content": "continue here",
            "prefix": True,
            "reasoning_content": "CoT so far",
        },
    )

    # --- to_http renders a valid request (never executed here)
    method, url, headers, body = ds.to_http(req, "dummy-key", base="openai")
    check(
        "DS_TO_HTTP",
        method == "POST"
        and url == "https://api.deepseek.com/chat/completions"
        and headers["Authorization"] == "Bearer dummy-key"
        and "deepseek-v4-flash" in body,
    )

    print("\nRESULT %d passed, %d failed" % (PASS, FAIL))
    return 0 if FAIL == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
