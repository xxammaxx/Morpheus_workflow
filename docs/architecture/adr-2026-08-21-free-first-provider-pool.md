# ADR-2026-08-21: Free-First Provider Pool in the Execution Adapter

Status: ACCEPTED

## Context

The n8n AutoDev workflows are the control plane, HAMH owns harness resolution,
and the existing adapter is the authenticated execution boundary. Provider
selection must control the real outbound request without adding an orchestrator,
retry controller, verifier, or status database.

Provider cost is an effective property of provider, model, endpoint, account
class, and quota. A provider therefore cannot be classified globally as free.
Unknown pricing is never eligible for the free pool.

## Decision

Free-first routing lives in the existing execution adapter, immediately before
HAMH resolution and execution dispatch:

```text
n8n control plane -> adapter router -> provider/model/endpoint -> HAMH -> backend
```

The router is a pure selection component with bounded provider failover. The
adapter records the routing decision and the execution proof fields in the
existing job ledger. HAMH receives the selected provider/model and remains the
sole harness authority. n8n and the verifier are unchanged authorities.

The runtime uses a dynamic catalog refresh and normalized provider protocol.
Provider-specific adapters are limited to discovery, quota/health parsing, and
non-OpenAI-compatible invocation. The default production switch is disabled
until shadow/canary approval; the previous adapter path remains the rollback
baseline.

Free execution has a hard invariant: an expected free route has expected cost
zero. A positive observed or provider-reported cost emits
`UNEXPECTED_BILLABLE_USAGE` and quarantines the exact provider/model/endpoint
from the free pool.

## Alternatives

### A. Route in n8n

Rejected. It duplicates provider policy in the control plane, cannot prove that
the selected provider owns the actual request, and mixes orchestration with
execution concerns.

### B. Route inside HAMH

Rejected. HAMH is the harness authority and must remain model/task/tool/context
configuration, not provider quota, billing, or failover policy.

### C. Separate routing service

Rejected for this change. It adds another authority, deployment, health surface,
and correlation boundary without a current operational need.

### D. Existing execution adapter

Chosen. It already owns `_dispatch()`, provider/model metadata, the append-only
ledger, HAMH resolution, and the authenticated backend boundary. This provides
minimal coupling, deterministic tests, bounded failover, and backward
compatibility without a second control plane.

## Consequences

- Provider catalog, quota, health, privacy, cost, and routing decisions are
  metadata-first and reusable by the existing status read model.
- Missing credentials and privacy consent disable only the affected provider.
- Dynamic discovery can remove or reclassify models without workflow changes.
- External provider live proof remains credential-dependent and is never
  inferred from routing metadata.
- Existing OpenCode/LM Studio and DeepSeek paths remain the rollback baseline.
