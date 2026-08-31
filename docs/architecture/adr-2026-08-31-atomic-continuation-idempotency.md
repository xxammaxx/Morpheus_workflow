# ADR: Atomic continuation idempotency claim

## Decision

The n8n control gateway obtains a durable claim before inserting a canonical
continuation run or invoking `01 AutoDev Orchestrator`. The claim guard is a
small n8n-side service backed by SQLite. Its only table is
`continuation_claims`, whose `identity_key` is the primary key. The claim store
contains idempotency metadata only; `autodev_runs` remains the canonical run
state source of truth.

The identity is `(project_id, source_run_id, correlation_id)`. The existing
deterministic `run-cont-<digest>` is retained. A successful `POST /claim` is
the only path allowed to persist the continuation row and start downstream.
Subsequent requests receive the same canonical run ID and do not start the
orchestrator.

Claims use `CLAIMED` and `STARTED` states with a bounded lease. n8n marks the
claim `STARTED` only after the orchestrator call returns. A retry after a
crash before downstream start can reclaim the same canonical run ID after the
lease expires; it never creates a new run. The unavoidable crash window after
an external side effect and before its acknowledgement remains a downstream
idempotency concern and is not claimed as proven by this ADR.

## Boundaries and ownership

- `CANONICAL_RUN_SOR=autodev_runs` (n8n Data Table)
- `CLAIM_STORE_ROLE=IDEMPOTENCY_ONLY`
- `CONTROL_TOWER_SECOND_SOR=NO`
- `DID_DASHBOARD_BECOME_CONTROL_PLANE=false`
- `UNIQUE_CONSTRAINT=PRIMARY KEY(continuation_claims.identity_key)`
- `EXACTLY_ONCE_SIDE_EFFECT_BOUNDARY=Atomic Continuation Claim -> Insert Run Row -> Run Orchestrator`

## Rejected alternative

n8n Data Table `upsert` is not sufficient: its implementation transactionally
updates matching rows and, when no row was updated, inserts a new row. Data
Table user columns have no public unique-index/insert-if-absent contract, so
two concurrent requests can both observe no matching row. Internal n8n tables
are not modified.
