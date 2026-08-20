#!/usr/bin/env python3
"""HAMH trajectory runner — real build runs on DeepSeek V4 Flash.

Each run:
  1. clones the FROZEN task fixture into a disposable workspace
  2. resolves the HAMH harness (live, host service) and stores the
     resolution artifact IN the workspace (execution-path evidence)
  3. executes a REAL opencode build run (provider=deepseek,
     model=deepseek-v4-flash) against the workspace
  4. verifies the outcome (pytest) — VERIFIED_SUCCESS
  5. parses the opencode session storage into a trajectory summary
     (tool calls, duplicates, retries, tokens, cost)

Stdlib only. No secrets. Privacy: reasoning content is never extracted.
"""

import argparse
import json
import os
import shutil
import subprocess
import sys
import time
import urllib.request

HOME = os.path.expanduser("~")
STORAGE = os.path.join(HOME, ".local", "share", "opencode", "storage")
FIXTURE = os.path.join(
    os.path.dirname(os.path.abspath(__file__)), "..", "fixtures", "task_fixture"
)
RESOLVE_URL = os.environ.get("HAMH_RESOLVE_URL", "http://192.168.1.136:8090/v1/resolve")

# Pricing snapshot 2026-08-20 (USD/1M, off-peak) — used ONLY for cost
# estimation since opencode reports cost=0 for custom providers.
PRICE = {
    "input_cache_hit_per_1m": 0.007,
    "input_cache_miss_per_1m": 0.22,
    "output_per_1m": 0.66,
}


def resolve_hamh(run_id, workspace):
    """Call the deployed HAMH resolver; write artifact into workspace."""
    payload = {
        "provider": "deepseek",
        "model": "deepseek-v4-flash",
        "model_revision": "0731",
        "task_class": "build",
        "runtime_mode": "thinking",
    }
    req = urllib.request.Request(
        RESOLVE_URL,
        data=json.dumps(payload).encode(),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=15) as r:
            resolution = json.loads(r.read().decode())
    except Exception as exc:
        resolution = {"error": str(exc), "is_fallback": True}
    artifact = os.path.join(workspace, "evidence", "hamh-resolution.json")
    os.makedirs(os.path.dirname(artifact), exist_ok=True)
    with open(artifact, "w") as f:
        json.dump(
            {
                "run_id": run_id,
                "resolution": resolution,
            },
            f,
            indent=2,
            sort_keys=True,
        )
    return resolution


def list_sessions():
    """Sessions from the opencode SQLite store (v1.15+)."""
    db = os.path.join(os.path.dirname(STORAGE), "opencode.db")
    out = {}
    if not os.path.isfile(db):
        return out
    import sqlite3

    try:
        con = sqlite3.connect(db)
        rows = con.execute(
            "SELECT id, title, directory, time_created FROM session"
        ).fetchall()
        con.close()
    except Exception:
        return out
    for sid, title, directory, created in rows:
        out[sid] = {
            "title": title or "",
            "directory": directory or "",
            "created": created or 0,
        }
    return out


def find_session(before, run_id):
    """Find the new session; retry briefly — opencode commits the session
    to SQLite asynchronously after CLI exit."""
    for attempt in range(5):
        after = list_sessions()
        for sid, meta in after.items():
            if meta["title"] and run_id in meta["title"]:
                return sid, meta
        cands = [(sid, m) for sid, m in after.items() if sid not in before]
        cands.sort(key=lambda kv: kv[1]["created"], reverse=True)
        if cands:
            return cands[0]
        time.sleep(1.0)
    return None, None


def parse_trajectory(session_id):
    """Extract trajectory facts from the opencode SQLite store."""
    db = os.path.join(os.path.dirname(STORAGE), "opencode.db")
    facts = {
        "session_id": session_id,
        "messages": 0,
        "assistant_messages": 0,
        "tool_calls": [],
        "tool_call_ids": [],
        "file_reads": [],
        "file_edits": [],
        "bash_commands": [],
        "text_output_chars": 0,
        "tokens": {
            "input": 0,
            "output": 0,
            "reasoning": 0,
            "cache_read": 0,
            "cache_write": 0,
        },
        "cost_usd": 0.0,
        "finish": None,
        "steps": 0,
        "retries": 0,
    }
    if not os.path.isfile(db) or not session_id:
        return facts
    import sqlite3

    con = sqlite3.connect(db)
    try:
        msgs = con.execute(
            "SELECT id, data FROM message WHERE session_id=? ORDER BY time_created",
            (session_id,),
        ).fetchall()
        facts["messages"] = len(msgs)
        for mid, mdata in msgs:
            try:
                m = json.loads(mdata)
            except Exception:
                continue
            if m.get("role") != "assistant":
                continue
            facts["assistant_messages"] += 1
            t = m.get("tokens") or {}
            facts["tokens"]["input"] += t.get("input") or 0
            facts["tokens"]["output"] += t.get("output") or 0
            facts["tokens"]["reasoning"] += t.get("reasoning") or 0
            c = t.get("cache") or {}
            facts["tokens"]["cache_read"] += c.get("read") or 0
            facts["tokens"]["cache_write"] += c.get("write") or 0
            if m.get("finish"):
                facts["finish"] = m["finish"]
            parts = con.execute(
                "SELECT data FROM part WHERE message_id=?", (mid,)
            ).fetchall()
            for (pdata,) in parts:
                try:
                    p = json.loads(pdata)
                except Exception:
                    continue
                ptype = p.get("type")
                if ptype == "step-finish":
                    facts["steps"] += 1
                    pt = p.get("tokens") or {}
                    facts["tokens"]["input"] += pt.get("input") or 0
                    facts["tokens"]["output"] += pt.get("output") or 0
                elif ptype == "tool":
                    st = p.get("state") or {}
                    tool = p.get("tool") or st.get("tool") or ""
                    inp = st.get("input") or {}
                    if tool == "bash":
                        cmd = str(inp.get("command") or "")[:150]
                        facts["bash_commands"].append(cmd)
                        if "pytest" in cmd:
                            facts["retries"] += 1
                    elif tool in ("read", "glob", "grep", "list"):
                        target = inp.get("filePath") or inp.get("pattern") or ""
                        facts["file_reads"].append(str(target)[:150])
                    elif tool in ("edit", "write"):
                        target = inp.get("filePath") or ""
                        facts["file_edits"].append(str(target)[:150])
                    call_id = p.get("callID") or st.get("callID") or ""
                    if call_id:
                        facts["tool_call_ids"].append(call_id)
                    if tool:
                        facts["tool_calls"].append(
                            {
                                "tool": tool,
                                "call_id": call_id,
                                "ts": p.get("time", {}).get("created"),
                            }
                        )
                elif ptype == "text":
                    facts["text_output_chars"] += len(p.get("text") or "")
    finally:
        con.close()
    seen = set()
    dups = 0
    for cid in facts["tool_call_ids"]:
        if cid in seen:
            dups += 1
        seen.add(cid)
    facts["duplicate_calls"] = dups
    # cost: opencode reports 0 for custom providers -> estimate from tokens
    t = facts["tokens"]
    if t["input"] > 0 or t["output"] > 0:
        est = (
            t["cache_read"] / 1e6 * PRICE["input_cache_hit_per_1m"]
            + max(t["input"] - t["cache_read"], 0)
            / 1e6
            * PRICE["input_cache_miss_per_1m"]
            + t["output"] / 1e6 * PRICE["output_per_1m"]
        )
        facts["cost_usd"] = round(max(facts["cost_usd"], est), 8)
    return facts
    msgs = []
    for fn in os.listdir(msg_dir):
        if not fn.endswith(".json"):
            continue
        try:
            with open(os.path.join(msg_dir, fn)) as f:
                msgs.append(json.load(f))
        except Exception:
            continue
    facts["messages"] = len(msgs)
    for m in msgs:
        role = m.get("role")
        if role == "assistant":
            facts["assistant_messages"] += 1
            t = m.get("tokens") or {}
            facts["tokens"]["input"] += t.get("input") or 0
            facts["tokens"]["output"] += t.get("output") or 0
            facts["tokens"]["reasoning"] += t.get("reasoning") or 0
            c = t.get("cache") or {}
            facts["tokens"]["cache_read"] += c.get("read") or 0
            facts["tokens"]["cache_write"] += c.get("write") or 0
            facts["cost_usd"] += m.get("cost") or 0
            if m.get("finish"):
                facts["finish"] = m["finish"]
        elif role == "user" and m.get("summary", {}).get("diffs"):
            # agent retried the same step (self-correction loop)
            facts["retries"] += 1
    # parts: tool calls / reads / edits
    if os.path.isdir(part_dir):
        for fn in os.listdir(part_dir):
            if not fn.endswith(".json"):
                continue
            try:
                with open(os.path.join(part_dir, fn)) as f:
                    p = json.load(f)
            except Exception:
                continue
            ptype = p.get("type")
            if ptype == "step-finish":
                facts["steps"] += 1
                t = p.get("tokens") or {}
                facts["cost_usd"] += p.get("cost") or 0
            elif ptype == "tool":
                ti = p.get("tool") or p.get("state", {}).get("tool")
                if p.get("state", {}).get("input", {}).get("tool"):
                    ti = p["state"]["input"]["tool"]
                inp = p.get("state", {}).get("input") or p.get("input") or {}
                if ti in ("read", "glob", "grep", "list"):
                    target = inp.get("filePath") or inp.get("pattern") or ""
                    facts["file_reads"].append(str(target)[:120])
                elif ti in ("edit", "write"):
                    target = inp.get("filePath") or ""
                    facts["file_edits"].append(str(target)[:120])
                call_id = p.get("state", {}).get("callID") or p.get("callID")
                if call_id:
                    facts["tool_call_ids"].append(call_id)
                facts["tool_calls"].append(
                    {
                        "tool": ti,
                        "call_id": call_id or "",
                        "ts": p.get("time", {}).get("created"),
                    }
                )
            elif ptype == "text":
                facts["text_output_chars"] += len(p.get("text") or "")
    # dedupe + duplicates metric
    seen = set()
    dups = 0
    for cid in facts["tool_call_ids"]:
        if cid in seen:
            dups += 1
        seen.add(cid)
    facts["duplicate_calls"] = dups
    # cost: if provider reports 0, estimate from tokens (cache-aware)
    if facts["cost_usd"] <= 0:
        t = facts["tokens"]
        est = (
            t["cache_read"] / 1e6 * PRICE["input_cache_hit_per_1m"]
            + (t["input"] - t["cache_read"]) / 1e6 * PRICE["input_cache_miss_per_1m"]
            + t["output"] / 1e6 * PRICE["output_per_1m"]
        )
        if t["input"] > 0 or t["output"] > 0:
            facts["cost_usd"] = round(max(est, 0.0), 8)
    return facts


def run():
    ap = argparse.ArgumentParser()
    ap.add_argument("--run-id", required=True)
    ap.add_argument("--work-root", default="/tmp/opencode/hamh-runs")
    ap.add_argument("--timeout", type=int, default=420)
    ap.add_argument("--reasoning-effort", default="high")
    ap.add_argument("--no-resolve", action="store_true")
    args = ap.parse_args()

    workspace = os.path.join(args.work_root, args.run_id)
    shutil.rmtree(workspace, ignore_errors=True)
    os.makedirs(workspace)

    # 1. copy fixture CONTENTS into disposable workspace (files must sit in
    #    the workspace ROOT where the tests run; note: cp -r src/ dst would
    #    nest the folder — use src/. to copy the contents)
    subprocess.run(["cp", "-r", FIXTURE + os.sep + ".", workspace], check=True)
    # PRE-CHECK: the fixture must be RED before the agent run (1 failing
    # test). If it is green, the fixture is corrupted and the run would be
    # silently invalid — abort instead.
    pre = subprocess.run(
        ["python3", "-m", "pytest", "test_calc.py", "-q"],
        cwd=workspace,
        capture_output=True,
        text=True,
        timeout=120,
    )
    if pre.returncode == 0:
        print(
            json.dumps(
                {
                    "run_id": args.run_id,
                    "error": "FIXTURE_PRE_CHECK_FAILED",
                    "detail": "fixture tests passed before agent run — corrupted "
                    "fixture, refusing to run",
                }
            )
        )
        return 1
    with open(os.path.join(workspace, "evidence_run.txt"), "w") as f:
        f.write("run_id=%s\n" % args.run_id)

    # 2. HAMH resolution
    resolution = resolve_hamh(args.run_id, workspace)

    # 3. opencode build run (cwd MUST be the workspace — verified: opencode
    #    records the process cwd as session directory)
    before = list_sessions()
    prompt = (
        "In this repository, the test suite has a failing test. "
        "Inspect the code and tests, find the root cause, fix the bug in "
        "calc.py ONLY (never modify the test file), and verify all tests "
        "pass by running: python3 -m pytest test_calc.py -q"
    )
    title = "hamh-run-%s" % args.run_id
    cmd = [
        "opencode",
        "run",
        "--dir",
        workspace,
        "--title",
        title,
        "--model",
        "deepseek/deepseek-v4-flash",
        "--agent",
        "build",
        prompt,
    ]
    t0 = time.time()
    try:
        res = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=args.timeout,
        )
        opencode_rc = res.returncode
    except subprocess.TimeoutExpired:
        opencode_rc = "TIMEOUT"
    latency_s = int(time.time() - t0)

    # 4. verification
    ver = subprocess.run(
        ["python3", "-m", "pytest", "test_calc.py", "-q"],
        cwd=workspace,
        capture_output=True,
        text=True,
        timeout=120,
    )
    verified = ver.returncode == 0
    vout = ver.stdout + ver.stderr
    passed = 0
    failed = 0
    for line in vout.splitlines():
        if line.startswith("FAILED"):
            failed += 1
        if "passed" in line:
            parts = line.split()
            for i, p in enumerate(parts):
                if p == "passed":
                    passed = int(parts[i - 1])

    # 5. trajectory parse
    sid, _ = find_session(before, args.run_id)
    traj = parse_trajectory(sid) if sid else {"session_id": None}
    first_pass = verified and opencode_rc == 0

    summary = {
        "run_id": args.run_id,
        "provider": "deepseek",
        "model": "deepseek-v4-flash",
        "model_revision": "0731",
        "task_class": "build",
        "runtime_mode": "thinking",
        "reasoning_effort": args.reasoning_effort,
        "resolution": {
            "resolved_harness_id": resolution.get("resolved_harness_id"),
            "is_fallback": resolution.get("is_fallback"),
            "fingerprint": resolution.get("fingerprint"),
            "resolver_error": resolution.get("error"),
        },
        "opencode_rc": opencode_rc,
        "latency_s": latency_s,
        "verified_success": verified,
        "first_pass_success": first_pass,
        "pytest": {"passed": passed, "failed": failed},
        "trajectory": traj,
        "ts": time.time(),
    }
    print(json.dumps(summary, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    sys.exit(run())
