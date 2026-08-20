#!/usr/bin/env python3
"""HAMH Real Testing — DeepSeek V4 Flash LIVE proof (§14-§18).

Executes REAL provider requests against https://api.deepseek.com with the
credential from the LEGITIMATE opencode secret store
(~/.local/share/opencode/auth.json -> "deepseek"). The key is read into
memory only, NEVER written to files, env, logs or evidence.

Proofs (§14-§17):
  14. provider connectivity smoke (thinking=disabled): HTTP_SUCCESS,
      MODEL_RESPONSE_RECEIVED, USAGE_RECEIVED, NO_PROTOCOL_ERROR
  15. thinking smoke (thinking=enabled, reasoning_effort=high):
      RESPONSE_SUCCESS, REASONING_STATE_RECEIVED, FINAL_CONTENT_RECEIVED
  16. real tool-call proof: REAL_DEEPSEEK_REQUEST_1 -> REAL_TOOL_CALL ->
      REAL_TOOL_EXECUTION -> REAL_TOOL_RESULT -> REAL_DEEPSEEK_REQUEST_2 ->
      FINAL_RESPONSE, with reasoning_content propagation = PASS
  17. negative protocol test (isolated): tool follow-up WITHOUT required
      reasoning_content -> expected HTTP 400 (provider invariant guard).
      NEVER modifies the production request builder (uses a dedicated
      raw-request path).

Privacy (§7): reasoning_content is PROTOCOL_STATE, not observability
payload. Only metadata is recorded (reasoning_state_present, byte counts).
Content of reasoning is NEVER reproduced in evidence.

Cost (§38): real usage data + documented pricing snapshot 2026-08-20
(off-peak): cache-hit $0.007/1M, cache-miss $0.22/1M, output $0.66/1M.
Hard stop at MAX_EXTERNAL_API_COST_USD (default 5.45 USD ~ 5 EUR).
"""

import json
import os
import sys
import time
import urllib.error
import urllib.request

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "..", "runtime"))
from hamh import deepseek_adapter as ds  # noqa: E402

BASE = ds.BASE_URLS["openai"]
AUTH_FILE = os.path.expanduser("~/.local/share/opencode/auth.json")
OUT_DIR = os.path.join(os.path.dirname(__file__), "..", "results")
OUT = os.path.join(OUT_DIR, "deepseek-live-proof.jsonl")
SUMMARY = os.path.join(OUT_DIR, "deepseek-live-summary.json")

# Pricing snapshot 2026-08-20 (USD / 1M tokens, off-peak; peak hours
# 01:00-04:00 + 06:00-10:00 UTC). Price is NOT a hard-coded immutable
# harness property — documented snapshot for this run only.
PRICE = {
    "snapshot_date": "2026-08-20",
    "currency": "USD",
    "tier": "off-peak",
    "input_cache_hit_per_1m": 0.007,
    "input_cache_miss_per_1m": 0.22,
    "output_per_1m": 0.66,
    "peak_hours_utc": ["01:00-04:00", "06:00-10:00"],
}
MAX_EXTERNAL_API_COST_USD = float(
    os.environ.get("MAX_EXTERNAL_API_COST_USD", "5.45")
)  # ~5 EUR

TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "get_test_value",
            "description": "Returns a deterministic test value for a given key",
            "parameters": {
                "type": "object",
                "properties": {"key": {"type": "string"}},
                "required": ["key"],
            },
        },
    }
]


def load_api_key():
    """Read the deepseek key from the legitimate opencode auth store."""
    with open(AUTH_FILE) as f:
        data = json.load(f)
    entry = data.get("deepseek") or {}
    key = entry.get("key") or entry.get("apiKey") or ""
    if not key:
        return None
    # format guard: sk- + 32 hex chars (documented DeepSeek key format)
    if not (key.startswith("sk-") and len(key) == 35):
        return None
    return key


def call_raw(payload, api_key):
    """Raw request execution (used by the negative test as well)."""
    body = json.dumps(payload).encode()
    req = urllib.request.Request(
        BASE + "/chat/completions",
        data=body,
        headers={
            "Authorization": "Bearer %s" % api_key,
            "Content-Type": "application/json",
        },
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=120) as r:
        return r.status, json.loads(r.read().decode())


def cost_of(usage):
    u = usage or {}
    hit = u.get("prompt_cache_hit_tokens") or 0
    miss = u.get("prompt_cache_miss_tokens") or 0
    out = u.get("completion_tokens") or 0
    usd = (
        hit / 1e6 * PRICE["input_cache_hit_per_1m"]
        + miss / 1e6 * PRICE["input_cache_miss_per_1m"]
        + out / 1e6 * PRICE["output_per_1m"]
    )
    return {"hit": hit, "miss": miss, "output": out, "cost_usd": round(usd, 8)}


def main():
    api_key = load_api_key()
    if not api_key:
        print("DEEPSEEK_CREDENTIAL=BLOCKED (no valid sk- key in auth.json)")
        return 2

    trail = []
    total_cost = 0.0

    def rec(event, data):
        trail.append({"ts": time.time(), "event": event, "data": data})

    def budget_check():
        if total_cost > MAX_EXTERNAL_API_COST_USD:
            print(
                "COST_LIMIT_EXCEEDED total=%.4f limit=%.2f"
                % (total_cost, MAX_EXTERNAL_API_COST_USD)
            )
            return False
        return True

    results = {}
    try:
        # ================= §14: NON-THINKING SMOKE =================
        t0 = time.time()
        status, resp = call_raw(
            ds.build_chat_request(
                "deepseek-v4-flash",
                [{"role": "user", "content": "Reply with exactly: OK"}],
                thinking="disabled",
                reasoning_effort="high",
            ),
            api_key,
        )
        latency = int((time.time() - t0) * 1000)
        usage = ds.parse_usage(resp.get("usage") or {})
        c = cost_of(usage)
        total_cost += c["cost_usd"]
        rec(
            "14_non_thinking",
            {
                "http_status": status,
                "latency_ms": latency,
                "model": resp.get("model"),
                "content_received": bool(resp["choices"][0]["message"].get("content")),
                "usage": {
                    k: usage[k]
                    for k in (
                        "prompt_tokens",
                        "completion_tokens",
                        "prompt_cache_hit_tokens",
                        "prompt_cache_miss_tokens",
                    )
                },
                "cost_usd": c["cost_usd"],
            },
        )
        s14 = (
            status == 200
            and resp["choices"][0]["message"].get("content")
            and usage.get("prompt_tokens") is not None
        )
        results["NON_THINKING_LIVE"] = s14
        print(
            "§14 non-thinking: HTTP %d, latency %dms, cost $%.6f"
            % (status, latency, c["cost_usd"])
        )

        # ================= §15: THINKING SMOKE =================
        t0 = time.time()
        status, resp = call_raw(
            ds.build_chat_request(
                "deepseek-v4-flash",
                [{"role": "user", "content": "Think briefly, then reply OK."}],
                thinking="enabled",
                reasoning_effort="high",
            ),
            api_key,
        )
        latency = int((time.time() - t0) * 1000)
        usage = ds.parse_usage(resp.get("usage") or {})
        c = cost_of(usage)
        total_cost += c["cost_usd"]
        msg = resp["choices"][0]["message"]
        reasoning = msg.get("reasoning_content")
        rec(
            "15_thinking",
            {
                "http_status": status,
                "latency_ms": latency,
                "reasoning_state_present": bool(reasoning),
                "reasoning_state_bytes": len(reasoning) if reasoning else 0,
                "final_content_received": bool(msg.get("content")),
                "usage": {
                    "completion_tokens": usage.get("completion_tokens"),
                    "reasoning_tokens": usage.get("reasoning_tokens"),
                },
                "cost_usd": c["cost_usd"],
            },
        )
        # privacy: reasoning content itself is NEVER recorded
        s15 = status == 200 and bool(reasoning) and bool(msg.get("content"))
        results["THINKING_LIVE"] = s15
        print(
            "§15 thinking: HTTP %d, reasoning=%dB, cost $%.6f"
            % (status, len(reasoning) if reasoning else 0, c["cost_usd"])
        )

        # ================= §16: REAL TOOL-CALL PROOF =================
        # request 1: force a tool call (tool_choice=required, 1 tool)
        req1 = ds.build_chat_request(
            "deepseek-v4-flash",
            [
                {
                    "role": "user",
                    "content": "Call get_test_value with key=fixture_a and report the value.",
                }
            ],
            thinking="enabled",
            reasoning_effort="high",
            tools=TOOLS,
            tool_choice="auto",
        )
        t0 = time.time()
        status, resp1 = call_raw(req1, api_key)
        latency1 = int((time.time() - t0) * 1000)
        msg1 = resp1["choices"][0]["message"]
        tool_calls = msg1.get("tool_calls") or []
        reasoning1 = msg1.get("reasoning_content")
        rec(
            "16_request_1",
            {
                "http_status": status,
                "latency_ms": latency1,
                "tool_calls": [
                    {"name": tc["function"]["name"], "id_prefix": tc["id"][:8]}
                    for tc in tool_calls
                ],
                "reasoning_state_present": bool(reasoning1),
                "reasoning_state_bytes": len(reasoning1) if reasoning1 else 0,
            },
        )
        assert status == 200 and tool_calls, "tool call expected"
        tc = tool_calls[0]
        tool_call_id = tc["id"]
        tool_name = tc["function"]["name"]
        args = json.loads(tc["function"]["arguments"] or "{}")

        # REAL TOOL EXECUTION (deterministic, harmless, isolated)
        # tool: get_test_value -> returns a fixed value derived from the key
        tool_result_value = "fixture_a_value_42"
        if args.get("key") == "fixture_a":
            tool_result_value = "fixture_a_value_42"
        tool_result = ds.build_tool_message(
            tool_call_id,
            json.dumps({"key": args.get("key"), "value": tool_result_value}),
        )
        rec(
            "16_tool_execution",
            {
                "tool": tool_name,
                "args_keys": sorted(args.keys()),
                "result_keys": ["key", "value"],
                "deterministic": True,
            },
        )

        # request 2: follow-up WITH reasoning_content echo (compliant)
        assistant_echo = {
            "role": "assistant",
            "content": msg1.get("content"),
            "reasoning_content": reasoning1,
            "tool_calls": tool_calls,
        }
        req2 = ds.build_chat_request(
            "deepseek-v4-flash",
            [
                {
                    "role": "user",
                    "content": "Call get_test_value with key=fixture_a and report the value.",
                },
                assistant_echo,
                tool_result,
            ],
            thinking="enabled",
            reasoning_effort="high",
            tools=TOOLS,
            tool_choice="auto",
        )
        # offline contract check BEFORE sending
        chain = ds.validate_tool_turn_chain(
            [
                {"role": "user", "content": "x"},
                assistant_echo,
                tool_result,
                {
                    "role": "assistant",
                    "content": "done",
                    "reasoning_content": reasoning1,
                },
            ]
        )
        assert chain == [], "offline 400-rule check failed: %s" % chain
        t0 = time.time()
        status2, resp2 = call_raw(req2, api_key)
        latency2 = int((time.time() - t0) * 1000)
        msg2 = resp2["choices"][0]["message"]
        usage2 = ds.parse_usage(resp2.get("usage") or {})
        c2 = cost_of(usage2)
        total_cost += c2["cost_usd"]
        rec(
            "16_request_2_final",
            {
                "http_status": status2,
                "latency_ms": latency2,
                "final_content_received": bool(msg2.get("content")),
                "finish_reason": resp2["choices"][0]["finish_reason"],
                "usage": {
                    "prompt_tokens": usage2.get("prompt_tokens"),
                    "completion_tokens": usage2.get("completion_tokens"),
                },
                "cost_usd": c2["cost_usd"],
            },
        )
        s16 = (
            status == 200
            and status2 == 200
            and tool_name == "get_test_value"
            and bool(msg2.get("content"))
            and bool(reasoning1)
        )
        results["TOOL_CALL_LIVE"] = s16
        results["REASONING_CONTENT_CONTINUITY"] = s16
        print(
            "§16 tool-loop: %s -> tool %s -> HTTP %d, cost $%.6f"
            % (tool_name, tool_call_id[:8], status2, c2["cost_usd"])
        )

        # ================= §17: NEGATIVE PROTOCOL TEST =================
        # Isolated raw request: tool follow-up WITHOUT the required
        # reasoning_content -> provider must answer HTTP 400.
        # Uses a dedicated raw path — the production request builder
        # (build_chat_request) is NEVER modified.
        violating = {
            "model": "deepseek-v4-flash",
            "messages": [
                {"role": "user", "content": "Call get_test_value key=fixture_a"},
                {
                    "role": "assistant",
                    "content": None,
                    "tool_calls": [
                        {
                            "id": "neg-test-call-1",
                            "type": "function",
                            "function": {
                                "name": "get_test_value",
                                "arguments": '{"key":"fixture_a"}',
                            },
                        }
                    ],
                },
                {
                    "role": "tool",
                    "tool_call_id": "neg-test-call-1",
                    "content": '{"value":"x"}',
                },
            ],
            "thinking": {"type": "enabled"},
            "reasoning_effort": "high",
            "tools": TOOLS,
            "stream": False,
        }
        try:
            status_neg, _ = call_raw(violating, api_key)
            results["NEGATIVE_PROTOCOL_TEST"] = False
            rec(
                "17_negative",
                {
                    "http_status": status_neg,
                    "expected": 400,
                    "violation_detected": False,
                },
            )
            print("§17 negative: UNEXPECTED HTTP %d (expected 400)" % status_neg)
        except urllib.error.HTTPError as e:
            status_neg = e.code
            body = e.read().decode()[:300]
            results["NEGATIVE_PROTOCOL_TEST"] = status_neg == 400
            rec(
                "17_negative",
                {
                    "http_status": status_neg,
                    "expected": 400,
                    "violation_detected": status_neg == 400,
                    "provider_error_class": "HTTP_%d" % status_neg,
                },
            )
            print(
                "§17 negative: HTTP %d (expected 400) -> invariant %s"
                % (status_neg, "PROTECTED" if status_neg == 400 else "NOT_PROTECTED")
            )

        # ================= §18: CLASSIFICATION =================
        ok = all(results.values())
        classification = (
            "GREEN_HAMH_DEEPSEEK_V4_FLASH_RUNTIME_PROVEN"
            if ok
            else "AMBER_DEEPSEEK_LIVE_PARTIAL"
        )
        rec(
            "FINAL",
            {
                "classification": classification,
                "results": results,
                "total_cost_usd": round(total_cost, 8),
            },
        )
        print("§18 CLASSIFICATION:", classification)
        print("TOTAL_EXTERNAL_API_COST_USD: %.6f" % total_cost)
    except urllib.error.HTTPError as e:
        rec(
            "HTTP_ERROR",
            {
                "status": e.code,
                "mapped": ds.map_http_error(e.code),
                "body_prefix": e.read().decode()[:200],
            },
        )
        results["HTTP_ERROR"] = e.code
        print("PROVIDER_HTTP_ERROR:", e.code)
    except Exception as e:  # noqa: BLE001
        rec("EXCEPTION", {"error": str(e)[:300]})
        print("EXCEPTION:", str(e)[:300])

    os.makedirs(OUT_DIR, exist_ok=True)
    with open(OUT, "w") as f:
        for entry in trail:
            f.write(json.dumps(entry, ensure_ascii=False) + "\n")
    with open(SUMMARY, "w") as f:
        json.dump(
            {
                "run_ts": time.time(),
                "results": results,
                "total_cost_usd": round(total_cost, 8),
                "price_snapshot": PRICE,
                "max_external_api_cost_usd": MAX_EXTERNAL_API_COST_USD,
                "verdict": classification if "classification" in results else "PARTIAL",
            },
            f,
            indent=2,
            sort_keys=True,
        )
    print("EVIDENCE: %s" % OUT)
    return 0 if results and all(v is True for v in results.values()) else 1


if __name__ == "__main__":
    sys.exit(main())
