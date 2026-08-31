# ADR: Atomic continuation idempotency claim

## Decision

The n8n control gateway obtains a durable claim before inserting a canonical
continuation run or delivering `01 AutoDev Orchestrator`. The same n8n-side
SQLite service also performs `ATOMIC_ACCEPT_ORCHESTRATION` immediately before
the orchestrator's first run-state write. Its only table is
`continuation_claims`, whose `identity_key` is the primary key. The claim store
contains claim, delivery, and fencing metadata only; `autodev_runs` remains
the canonical run-state source of truth.

The identity is `(project_id, source_run_id, correlation_id)`. The existing
deterministic `run-cont-<digest>` is retained. A successful `POST /claim` is
the only path allowed to persist the continuation row. `POST
/orchestration/accept` is the durable consumer guard: only its `accepted=true`
result may initialize the orchestrator. Repeated delivery with the same
`run_id` returns `accepted=false` but may safely resume the same canonical
initialization. The first run-state transition is independently conditional
on `autodev_runs.state = ACCEPTED`, so only one delivery can cross into
`BASELINING`.

Claims use `CLAIMED` and `STARTED` states with a bounded lease. `STARTED` in
the claim store means durable delivery acceptance, not canonical run
completion. A retry after a crash before downstream acceptance can reclaim the
same canonical run ID after the lease expires; it never creates a new run.
Fencing generations prevent a stale worker from accepting a recovered
delivery. A retry after acceptance is safe because the canonical
`ACCEPTED -> BASELINING` transition is the logical-start guard.

## Boundaries and ownership

- `CANONICAL_RUN_SOR=autodev_runs` (n8n Data Table)
- `CLAIM_STORE_ROLE=IDEMPOTENCY_ONLY`
- `CONTROL_TOWER_SECOND_SOR=NO`
- `DID_DASHBOARD_BECOME_CONTROL_PLANE=false`
- `UNIQUE_CONSTRAINT=PRIMARY KEY(continuation_claims.identity_key)`
- `EXACTLY_ONCE_SIDE_EFFECT_BOUNDARY=autodev_runs ACCEPTED -> BASELINING conditional transition`
- `DELIVERY_SEMANTICS=AT_LEAST_ONCE`
- `CONSUMER_SEMANTICS=IDEMPOTENT`
- `LOGICAL_EFFECT_SEMANTICS=EFFECTIVELY_ONCE`
- `SQLITE_DURABILITY=journal_mode=WAL, synchronous=FULL, busy_timeout=10000ms`

## Rejected alternative

n8n Data Table `upsert` is not sufficient: its implementation transactionally
updates matching rows and, when no row was updated, inserts a new row. Data
Table user columns have no public unique-index/insert-if-absent contract, so
two concurrent requests can both observe no matching row. Internal n8n tables
are not modified.
