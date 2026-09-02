# Provider route stability recovery — 2026-09-01

## Classification

`AMBER_MORPHEUSBENCH_PROVIDER_ROUTE_PIPELINE_BLOCKED`

The capability precheck for `opencode/big-pickle` passed, but the canonical
run did not prove a provider response. The selected route was then rebound by
the production transport-failover loop. This is invalid benchmark evidence.

## Proven root cause

The deployed OpenCode worker runs inside `bwrap --ro-bind / /`. OpenCode
requires writable runtime state under `/root/.local/share/opencode`; the first
direct forensic invocation failed before provider transport while opening
`opencode.log`. Making only the log directory writable exposed the next
failure, SQLite `PRAGMA wal_checkpoint(PASSIVE)`, proving that the database/WAL
also require writable run-local state.

Therefore the first broken edge is:

```text
adapter OpenCode invocation → OpenCode writable runtime state
```

## Route consequence

The failed canonical `research.code` job selected `opencode/big-pickle`, had no
actual provider/model, and then traversed 44 free fallback candidates. The
`research.docs` and `research.tests` jobs also had no actual identity. The
precheck proved eligibility, not execution.

PR #66 supplies writable run-local OpenCode state while preserving `auth.json`
read-only. PR #67 adds benchmark-only `FAIL_CLOSED` route pinning: one bounded
retry may repeat the same route, but route drift or missing actual identity
invalidates the benchmark and cannot select another provider/model. Production
fallback remains unchanged outside benchmark metadata.

No BASELINE or CONTEXT smoke is valid until these exact heads are deployed
together and a live exact-route probe passes.

## Exact-route qualification probe — 2026-09-01

`BAD_TASK_CLASS` was a probe-envelope blocker, not provider or route evidence.
The authoritative HAMH v1 enum is `research|plan|build|review|verify|baseline`;
the corrected probe used the existing `plan` value and required no runtime
code change. It selected `opencode/big-pickle` with `FAIL_CLOSED`, but failed
before the OpenCode process while creating the builder workspace (`Permission
denied`). No provider request/response or writable OpenCode-state proof exists.
`EXACT_ROUTE_PROBE=FAIL`; BASELINE and CONTEXT were not started.

See [`exact-route-probe-2026-09-01.json`](../../evidence/morpheus-bench/exact-route-probe-2026-09-01.json).

## Creation-order recovery — 2026-09-02

The builder permission blocker was isolated to host workspace creation before
the first CT filesystem operation. The adapter now establishes mapped CT8001
ownership and restrictive `0700`, verifies mapped access, and only then runs
`git init`. Route policy and provider selection are unchanged.
