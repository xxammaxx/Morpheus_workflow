#!/usr/bin/env python3
"""HAMH weakness mining on real trajectories (§23).

Aggregates failure/rework patterns across the baseline runs:
  - failed edits (edit tool status=error)
  - edit retries (edit on the same file after an error)
  - duplicate reads (same file read more than once)
  - repeated pytest executions (re-verification loops)
  - excessive tool loops (tool_calls > median * 2)

A pattern only counts as evidence if observed in >= 2 independent runs
(MIN_EVIDENCE_RUNS=2, order §23). Output: sorted patterns + per-run facts.
"""

import glob
import json
import os
import sqlite3
import sys

HOME = os.path.expanduser("~")
DB = os.path.join(HOME, ".local", "share", "opencode", "opencode.db")
MIN_RUNS = 2


def load_session(session_id):
    con = sqlite3.connect(DB)
    out = {"edits": [], "reads": [], "bash": [], "tool_calls": []}
    try:
        msgs = con.execute(
            "SELECT id, data FROM message WHERE session_id=? ORDER BY time_created",
            (session_id,),
        ).fetchall()
        for mid, mdata in msgs:
            parts = con.execute(
                "SELECT data FROM part WHERE message_id=?", (mid,)
            ).fetchall()
            for (pdata,) in parts:
                try:
                    p = json.loads(pdata)
                except Exception:
                    continue
                if p.get("type") != "tool":
                    continue
                st = p.get("state") or {}
                tool = p.get("tool") or ""
                inp = st.get("input") or {}
                out["tool_calls"].append(tool)
                if tool == "edit":
                    out["edits"].append(
                        {
                            "path": inp.get("filePath"),
                            "status": st.get("status"),
                            "error": st.get("error"),
                            "output": st.get("output"),
                        }
                    )
                elif tool in ("read", "glob", "grep", "list"):
                    out["reads"].append(
                        str(inp.get("filePath") or inp.get("pattern") or "")
                    )
                elif tool == "bash":
                    out["bash"].append(str(inp.get("command") or ""))
    finally:
        con.close()
    return out


def mine_run(session_id, run_id):
    s = load_session(session_id)
    patterns = []
    # failed edits
    failed_edits = [e for e in s["edits"] if e.get("status") == "error"]
    if failed_edits:
        patterns.append("frequent_malformed_edits")
    # edit retry: an error edit followed by a successful edit on same path
    edit_paths = [e.get("path") for e in s["edits"]]
    edit_retry = False
    for i in range(len(s["edits"]) - 1):
        if s["edits"][i].get("status") == "error" and s["edits"][i].get("path") == s[
            "edits"
        ][i + 1].get("path"):
            edit_retry = True
    if edit_retry:
        patterns.append("late_editing")
    # duplicate reads of the same file
    seen = set()
    dup_read = False
    for r in s["reads"]:
        if r in seen:
            dup_read = True
        seen.add(r)
    if dup_read:
        patterns.append("same_file_repeatedly_reopened")
    # repeated pytest verification (>= 3 runs of pytest in one trajectory)
    pytest_runs = sum(1 for c in s["bash"] if "pytest" in c)
    if pytest_runs >= 3:
        patterns.append("excessive_tool_loops")
    # excessive tool calls (>= 14, i.e. > 2x typical)
    if len(s["tool_calls"]) >= 14:
        patterns.append("excessive_tool_loops")
    return {
        "run_id": run_id,
        "session_id": session_id,
        "tool_calls": len(s["tool_calls"]),
        "reads": len(s["reads"]),
        "edits": len(s["edits"]),
        "failed_edits": len(failed_edits),
        "edit_retry": edit_retry,
        "dup_read": dup_read,
        "pytest_runs": pytest_runs,
        "patterns": patterns,
        "edit_statuses": [e.get("status") for e in s["edits"]],
    }


def main():
    runs_dir = sys.argv[1] if len(sys.argv) > 1 else "/tmp/opencode/baseline3"
    run_facts = []
    for f in sorted(glob.glob(os.path.join(runs_dir, "e*.json"))):
        d = json.load(open(f))
        sid = d.get("trajectory", {}).get("session_id")
        if not sid:
            continue
        facts = mine_run(sid, d["run_id"])
        facts["verified"] = d["verified_success"]
        run_facts.append(facts)

    counts = {}
    for rf in run_facts:
        for p in rf["patterns"]:
            counts[p] = counts.get(p, 0) + 1

    print("PER-RUN FACTS:")
    for rf in run_facts:
        print(
            "  %s v=%s tools=%d reads=%d edits=%d failed_edits=%d "
            "edit_retry=%s dup_read=%s pytest=%d patterns=%s"
            % (
                rf["run_id"],
                rf["verified"],
                rf["tool_calls"],
                rf["reads"],
                rf["edits"],
                rf["failed_edits"],
                rf["edit_retry"],
                rf["dup_read"],
                rf["pytest_runs"],
                rf["patterns"],
            )
        )
    print("\nAGGREGATED (min %d runs):" % MIN_RUNS)
    qualified = sorted(
        ((p, c) for p, c in counts.items() if c >= MIN_RUNS),
        key=lambda kv: (-kv[1], kv[0]),
    )
    for p, c in qualified:
        print("  %s: %d runs" % (p, c))
    if not qualified:
        print("  (none)")
    print("\nTOTAL_RUNS=%d" % len(run_facts))
    return 0


if __name__ == "__main__":
    sys.exit(main())
