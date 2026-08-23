# ADR-2026-08-22: Free-First Provider Pool and DeepSeek Retirement

Status: ACCEPTED FOR THIS DELTA
Issue: `xxammaxx/Morpheus_workflow#1`
Date: 2026-08-23

## Context

The committed system has one authenticated execution adapter between n8n and
workers. The adapter already owns job identity, semantic attempts, contracts,
HAMH resolution, and the append-only execution ledger. The committed baseline
does not contain a provider runtime. The original dirty worktree contains
uncommitted provider experiments and inaccurate Delta documents; neither is
canonical.

The target needs a free-first route across Groq and OpenRouter without confusing
model count with provider redundancy, while preventing unexpected paid usage.
DeepSeek must remain historical evidence only for Morpheus agent execution.

## Decision

Add a stdlib-only provider layer under `runtime/providers/` and integrate it at
the exact existing adapter seam `adapter/harness_adapter_v2.py:_dispatch()`.
Keep n8n as the control plane, the adapter as the execution boundary, HAMH as
harness/profile authority, and the provider router as the sole provider
selection/failover authority.

The router selects a route using the existing task/profile vocabulary and a
route-specific zero-cost contract. The route key is provider, model,
endpoint/tier, and account class. Unknown cost or incomplete live evidence is
ineligible. Provider failover is bounded by `AUTODEV_PROVIDER_FAILOVER_MAX`
(default 3, minimum 1), stays within one semantic task attempt, and never
selects paid or DeepSeek routes.

HAMH `provider`/`model` inputs remain profile preferences. Route identity uses
separate `route_*` and `selected_*` fields, while `backend` remains backend
routing. The router decision is authoritative over caller preferences and is
resolved before HAMH profile selection. The selected decision is passed from
`_dispatch()` to `new_job()` and `run_job_thread()`; provider-direct execution
then calls `_provider_direct_completion()` and `finalize_job()` with a
`ProviderExecution` result. Local backend jobs have no external route and do
not enter provider failover.

Groq's adapter sets a stable honest application User-Agent only when no explicit
User-Agent exists. Existing explicit headers and request semantics retain
precedence.

HAMH `provider`/`model` inputs remain profile preferences. Route identity uses
separate `route_*` and `selected_*` fields, while `backend` remains backend
routing. The router decision is authoritative over caller preferences and is
resolved before HAMH profile selection.

Observability records selected, resolved, and actual identity only when the
transport can prove it, alongside real usage/cost/free status and provider
failover. Unsupported fields are not fabricated.

## Authentication and Authority Boundaries

`Handler._auth()` validates `X-Harness-Token` against `TOKEN_FILE`, derived from
`AUTODEV_V2_STATE`. The service/control-plane owner supplies the header. This is
separate from OpenCode credentials. The provider layer receives provider
credentials from deployment environment variables and never persists their
values.

## Alternatives Rejected

### Add a second control plane or router

Rejected. It would split dispatch authority and make selection-to-execution
ownership unverifiable.

### Treat OpenRouter free models as provider redundancy

Rejected. Multiple models under one provider do not provide independent provider
transport or account redundancy.

### Preserve automatic paid DeepSeek escalation

Rejected. The closure's safety invariant is no automatic paid agent escalation;
free-pool exhaustion must stop with `NO_ELIGIBLE_FREE_PROVIDER`.

### Implement shared quota, shadow, or canary now

Rejected for this delta. Shared quota is not implemented in the real seam.
Shadow and canary are post-closure follow-ups, not acceptance contracts.

### Change local OpenCode configuration

Rejected. The active local configuration has zero DeepSeek mappings and is a
separate credential/runtime system. Historical backups remain untouched.

## Consequences

Positive:

- Groq transport has an explicit application identity without browser spoofing.
- Provider/model identity is separated and outbound ownership is testable.
- Free routes fail closed when cost or account evidence is incomplete.
- Provider failure does not consume a semantic task retry.
- Paid and DeepSeek execution are excluded from normal Morpheus dispatch.

Costs and limitations:

- Live zero-cost proof is route/account-specific and can expire with provider
  policy or model catalog changes.
- Quota state is observed per route; no shared quota is provided.
- Dynamic discovery requires credentials supplied by deployment but never logs
  them.
- Shadow, canary, and production cutover remain outside this issue.

## Verification

- Contract tests validate provider records and rejection paths.
- HTTP transport tests prove default-only User-Agent behavior and header
  precedence.
- Runtime tests prove dynamic discovery, capability filtering, zero-cost guards,
  bidirectional provider failover, semantic-retry separation, paid/DeepSeek
  exclusion, and free-pool exhaustion.
- Adapter integration proves selected provider/model owns the outbound request.
- Groq and OpenRouter live proofs are route-specific and value-redacted.
- n8n workflow JSON and `git diff --check` are validated.

## Follow-Up

Shared quota, shadow, canary, and production cutover require a separate issue
with fresh contracts and authorization.
