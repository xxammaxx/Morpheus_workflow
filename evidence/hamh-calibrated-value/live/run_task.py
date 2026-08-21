#!/usr/bin/env python3
"""HAMH calibrated-value pool runner — real build runs on DeepSeek V4 Flash.

Each run:
  1. copies the FROZEN task fixture (t-XXX) into a disposable workspace
  2. pre-checks the fixture is RED (at least one failing test)
  3. resolves the HAMH harness (live, host service) and stores the
     resolution artifact IN the workspace
  4. executes a REAL opencode build run (provider=deepseek,
     model=deepseek-v4-flash, agent=build) against the workspace
  5. verifies the outcome (pytest) — VERIFIED_SUCCESS
  6. parses the opencode SQLite session into a trajectory summary

Conditions:
  a = frozen baseline harness (thinking, reasoning_effort=high)
  b = candidate harness (baseline + extra prompt from --candidate-prompt-file)
  c = matched-compute control (baseline harness, reasoning_effort=max)

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
HERE = os.path.dirname(os.path.abspath(__file__))
POOL = os.path.normpath(os.path.join(HERE, "..", "fixtures", "pool"))
RESOLVE_URL = os.environ.get("HAMH_RESOLVE_URL", "http://192.168.1.136:8090/v1/resolve")

# Pricing snapshot 2026-08-20 (USD/1M, off-peak) — cost ESTIMATION only.
PRICE = {
    "input_cache_hit_per_1m": 0.007,
    "input_cache_miss_per_1m": 0.22,
    "output_per_1m": 0.66,
}


def resolve_hamh(run_id, workspace, harness="a", harness_id=None):
    payload = {
        "provider": "deepseek",
        "model": "deepseek-v4-flash",
        "model_revision": "0731",
        "task_class": "build",
        "runtime_mode": "thinking",
    }
    if harness_id:
        payload["harness_id"] = harness_id
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
            {"run_id": run_id, "harness": harness, "resolution": resolution},
            f,
            indent=2,
            sort_keys=True,
        )
    return resolution


def list_sessions():
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


def find_test_file(workspace):
    for fn in sorted(os.listdir(workspace)):
        if fn.startswith("test_") and fn.endswith(".py"):
            return fn
    return None


def run():
    ap = argparse.ArgumentParser()
    ap.add_argument("--run-id", required=True)
    ap.add_argument("--task", required=True, help="t-XXX fixture id")
    ap.add_argument("--work-root", default="/tmp/opencode/hamh-cal-runs")
    ap.add_argument("--out-dir", default=os.path.join(HERE, "..", "results", "runs"))
    ap.add_argument("--timeout", type=int, default=480)
    ap.add_argument("--harness", default="a", choices=["a", "b", "c"])
    ap.add_argument("--candidate-prompt-file", default=None)
    ap.add_argument("--variant", default="high", help="reasoning effort (c=max)")
    args = ap.parse_args()

    task_dir = os.path.join(POOL, args.task)
    if not os.path.isdir(task_dir):
        print(
            json.dumps(
                {"run_id": args.run_id, "error": "UNKNOWN_TASK", "task": args.task}
            )
        )
        return 1

    workspace = os.path.join(args.work_root, args.run_id)
    shutil.rmtree(workspace, ignore_errors=True)
    os.makedirs(workspace)
    subprocess.run(["cp", "-r", task_dir + os.sep + ".", workspace], check=True)
    # strip non-source artifacts copied by pytest runs
    for junk in (".pytest_cache", "__pycache__"):
        subprocess.run(
            ["rm", "-rf", os.path.join(workspace, junk)], capture_output=True
        )

    test_file = find_test_file(workspace)
    if not test_file:
        print(json.dumps({"run_id": args.run_id, "error": "NO_TEST_FILE_FOUND"}))
        return 1

    pre = subprocess.run(
        ["python3", "-m", "pytest", test_file, "-q"],
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
                    "detail": "fixture tests passed before agent run — corrupted fixture",
                }
            )
        )
        return 1

    resolution = resolve_hamh(args.run_id, workspace, harness=args.harness)

    extra_prompt = ""
    if args.harness == "b" and args.candidate_prompt_file:
        extra_prompt = "\n\n" + open(args.candidate_prompt_file).read().strip()

    before = list_sessions()
    prompt = (
        "In this repository, the test suite has a failing test. "
        "Inspect the code and tests, find the root cause, fix the bug in "
        "the module ONLY (never modify the test file), and verify all tests "
        "pass by running: python3 -m pytest %s -q%s" % (test_file, extra_prompt)
    )
    title = "hamh-cal-%s" % args.run_id
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
        "--variant",
        args.variant,
        prompt,
    ]
    t0 = time.time()
    try:
        res = subprocess.run(cmd, capture_output=True, text=True, timeout=args.timeout)
        opencode_rc = res.returncode
    except subprocess.TimeoutExpired:
        opencode_rc = "TIMEOUT"
    latency_s = int(time.time() - t0)

    ver = subprocess.run(
        ["python3", "-m", "pytest", test_file, "-q"],
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

    sid, _ = find_session(before, args.run_id)
    traj = parse_trajectory(sid) if sid else {"session_id": None}
    first_pass = verified and opencode_rc == 0

    summary = {
        "run_id": args.run_id,
        "task": args.task,
        "harness": args.harness,
        "provider": "deepseek",
        "model": "deepseek-v4-flash",
        "model_revision": "0731",
        "task_class": "build",
        "runtime_mode": "thinking",
        "reasoning_effort": args.variant,
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
    os.makedirs(args.out_dir, exist_ok=True)
    out_path = os.path.join(args.out_dir, args.run_id + ".json")
    with open(out_path, "w") as f:
        json.dump(summary, f, indent=1, sort_keys=True)
    print(json.dumps(summary, indent=1, sort_keys=True))
    return 0


if __name__ == "__main__":
    sys.exit(run())
