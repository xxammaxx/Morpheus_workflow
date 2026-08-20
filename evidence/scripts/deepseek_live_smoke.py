#!/usr/bin/env python3
"""OPT-IN DeepSeek V4 Flash live smoke script (order section 24).

NOT executed in the HAMH build run: no DeepSeek credential exists in
.secrets/ and production policy does not provide one (DEEPSEEK_LIVE_PROOF=
NOT_RUN, honestly declared). When a credential is available:

    export DEEPSEEK_API_KEY='sk-...'
    python3 evidence/scripts/deepseek_live_smoke.py

The script verifies the exact contract that the Model Adapter encodes
(ADR H6):
  - thinking mode enabled/disabled
  - tool call (function) round-trip
  - reasoning_content echo-back across tool turns (400 rule)
  - subsequent tool turn
  - final response
  - no provider protocol error
  - complete audit trail (JSONL evidence file)

Requires ONLY stdlib (urllib). Writes evidence to
evidence/phase-d-hamh/results/deepseek-live-smoke.jsonl
"""

import json
import os
import sys
import time
import urllib.error
import urllib.request

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "runtime"))

from hamh import deepseek_adapter as ds  # noqa: E402

API_KEY = os.environ.get("DEEPSEEK_API_KEY")
BASE = ds.BASE_URLS["openai"]
OUT = os.path.join(
    os.path.dirname(__file__),
    "..",
    "phase-d-hamh",
    "results",
    "deepseek-live-smoke.jsonl",
)

TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "get_weather",
            "description": "Get current weather for a city",
            "parameters": {
                "type": "object",
                "properties": {"city": {"type": "string"}},
                "required": ["city"],
            },
        },
    }
]


def call(payload):
    method, url, headers, body = ds.to_http(payload, API_KEY, base="openai")
    req = urllib.request.Request(
        url, data=body.encode(), headers=headers, method=method
    )
    with urllib.request.urlopen(req, timeout=120) as r:
        return json.loads(r.read().decode())


def main():
    if not API_KEY:
        print("DEEPSEEK_LIVE_PROOF=NOT_RUN (no DEEPSEEK_API_KEY)")
        return 2

    run_id = "ds-live-%d" % int(time.time())
    trail = []

    def rec(event, data):
        trail.append(
            {"ts": time.time(), "run_id": run_id, "event": event, "data": data}
        )

    try:
        # 1. thinking mode + tool call round-trip
        payload = ds.build_chat_request(
            "deepseek-v4-flash",
            [
                {
                    "role": "user",
                    "content": "What is the weather in Berlin? Use the tool.",
                }
            ],
            thinking="enabled",
            reasoning_effort="high",
            tools=TOOLS,
            tool_choice="auto",
        )
        rec("request_1", {"model": payload["model"], "thinking": payload["thinking"]})
        resp = call(payload)
        choice = resp["choices"][0]
        msg = choice["message"]
        rec(
            "response_1",
            {
                "finish_reason": choice["finish_reason"],
                "has_reasoning": bool(msg.get("reasoning_content")),
                "tool_calls": msg.get("tool_calls") or [],
            },
        )
        assert msg.get("tool_calls"), "expected a tool call"

        # 2. echo-back turn: assistant reasoning_content MUST be passed back
        tool_call_id = msg["tool_calls"][0]["id"]
        assistant_echo = {
            "role": "assistant",
            "content": msg.get("content"),
            "reasoning_content": msg.get("reasoning_content"),
            "tool_calls": msg.get("tool_calls"),
        }
        tool_result = ds.build_tool_message(
            tool_call_id, json.dumps({"city": "Berlin", "temp_c": 18})
        )
        # offline contract check of the 400 rule BEFORE sending
        chain_check = ds.validate_tool_turn_chain(
            [
                {"role": "user", "content": "weather?"},
                assistant_echo,
                tool_result,
                {
                    "role": "assistant",
                    "content": "checking",
                    "reasoning_content": msg.get("reasoning_content"),
                },
            ]
        )
        rec("400_rule_offline_check", {"violations": chain_check})
        assert chain_check == [], "reasoning_content echo violation"

        payload2 = ds.build_chat_request(
            "deepseek-v4-flash",
            [
                {"role": "user", "content": "What is the weather in Berlin?"},
                assistant_echo,
                tool_result,
            ],
            thinking="enabled",
            reasoning_effort="high",
            tools=TOOLS,
            tool_choice="auto",
        )
        resp2 = call(payload2)
        final_msg = resp2["choices"][0]["message"]
        rec(
            "response_2_final",
            {
                "content": final_msg.get("content"),
                "finish_reason": resp2["choices"][0]["finish_reason"],
            },
        )
        rec("usage", ds.parse_usage(resp2.get("usage") or {}))

        # 3. non-thinking baseline call
        payload3 = ds.build_chat_request(
            "deepseek-v4-flash",
            [{"role": "user", "content": "Say OK."}],
            thinking="disabled",
            reasoning_effort="low",
        )
        resp3 = call(payload3)
        rec(
            "response_3_non_thinking",
            {
                "content": resp3["choices"][0]["message"].get("content"),
                "finish_reason": resp3["choices"][0]["finish_reason"],
            },
        )
        rec("FINAL", {"status": "PASS", "protocol_errors": 0})
        verdict = "GREEN_DEEPSEEK_LIVE_SMOKE_PASS"
        rc = 0
    except urllib.error.HTTPError as e:
        err = ds.map_http_error(e.code)
        rec(
            "HTTP_ERROR",
            {"status": e.code, "mapped": err, "body": e.read().decode()[:500]},
        )
        verdict = "RED_DEEPSEEK_LIVE_SMOKE_PROVIDER_ERROR"
        rc = 1
    except Exception as e:  # noqa: BLE001 - smoke script boundary
        rec("EXCEPTION", {"error": str(e)[:500]})
        verdict = "RED_DEEPSEEK_LIVE_SMOKE_EXCEPTION"
        rc = 1

    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    with open(OUT, "a") as f:
        for entry in trail:
            f.write(json.dumps(entry, ensure_ascii=False) + "\n")
    print(verdict)
    return rc


if __name__ == "__main__":
    sys.exit(main())
