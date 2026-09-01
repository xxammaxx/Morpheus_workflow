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
