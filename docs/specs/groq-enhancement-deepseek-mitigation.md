# Free-First Runtime Closure Specification

Status: SPECIFIED FOR IMPLEMENTATION
Issue: `xxammaxx/Morpheus_workflow#1`
Baseline: `7e215aa6150ecfdb3a4cec399528f074ce81d714`

## Problem

The committed baseline has a working n8n-to-`adapter/harness_adapter_v2.py`
execution boundary, but it does not contain a canonical provider catalog,
free-first standard dispatch, or provider-level failover. Provider code and
Delta documents observed in the original dirty worktree are uncommitted
reference material, not canonical baseline.

The closure must add only a truthful provider runtime seam. Groq transport must
identify the application without imitating a browser. Groq and OpenRouter must
be independent provider paths, while models discovered through OpenRouter must
not be counted as providers. Paid DeepSeek execution and automatic paid
escalation must be unavailable in Morpheus.

## Current Reality

- The adapter authenticates requests with `X-Harness-Token`.
- The validator reads the expected token from `TOKEN_FILE`, which is
  `AUTODEV_V2_STATE/token`, defaulting to `/var/lib/autodev-harness-v2/token`.
- The adapter supplies no token value itself. The service/runtime owner creates
  the file and the caller supplies the header. The trust boundary is the
  authenticated control-plane-to-execution-plane HTTP boundary.
- The committed adapter already records `provider`, `model`, `attempt_id`,
  failure fields, and timing in job records. It does not yet record a
  route-specific selected/resolved/actual provider execution proof.
- The committed baseline has no `runtime/providers/` package and no provider
  provider-acceptance tests. These are implementation targets, not existing
  interfaces.
- Local OpenCode's active configuration is outside this repository. The active
  file was read-only checked and has `opencode/big-pickle` and
  `zai/glm-4.5-flash`; it has no active DeepSeek mapping. Historical backups are
  evidence only and are not modified.
- The original dirty worktree reference contains a proposed
  `AUTODEV_PROVIDER_FAILOVER_MAX` read in the provider runtime. This Delta makes
  that exact spelling canonical only in the new runtime implementation.

## Target

### Provider catalog and zero-cost contract

Implement a stdlib-only provider package under `runtime/providers/` with these
concrete modules:

- `protocol.py`: request/response and catalog value helpers.
- `adapters.py`: OpenAI-compatible HTTP adapter and provider-specific endpoint
  configuration.
- `catalog.py`: dynamic discovery, policy application, health/quota state, and
  atomic catalog persistence.
- `capabilities.py`: staged capability evidence and role mapping.
- `router.py`: canonical standard-dispatch selection and bounded provider
  failover.
- `runtime.py`: adapter-facing selection and execution facade.
- `refresh.py`: new maintenance entry point for catalog refresh, available only
  after implementation.

These modules are new implementation targets in this clean baseline, not
current interfaces.

Every free decision is route-specific:

`provider × model × endpoint/tier × account_class`.

The route is free eligible only when all required evidence and runtime guards
hold: catalog pricing is zero, the account/tier is eligible, direct live proof
exists where required, adapter live proof exists, selection-to-execution proof
correlates the outbound request, privacy is allowed, health is usable, quota is
not exhausted, and automatic paid fallback is false. Unknown pricing or
missing evidence is never free eligible.

Evidence stages are distinct:

1. `CATALOG_FREE`
2. `ACCOUNT_FREE_ELIGIBLE`
3. `DIRECT_LIVE_PROVEN`
4. `ADAPTER_LIVE_PROVEN`
5. `SELECTION_TO_EXECUTION_PROVEN`

### Routing

The exact canonical adapter entry seam is
`adapter/harness_adapter_v2.py:_dispatch(...)`. It is the only standard job
dispatch entry point. It validates the existing input contract, constructs the
job, and starts the existing `run_job_thread(...)`; the provider runtime is
called from the worker path for provider-direct execution. The target provider
interfaces are:

```text
ProviderAdapter.discover_models() -> list[dict]
ProviderAdapter.invoke(ProviderRequest, timeout) -> ProviderResponse
ProviderRuntime.select(RouteRequest) -> RoutingDecision
ProviderRuntime.invoke_with_failover(RouteRequest, messages, task_class, timeout,
    attempt_id)
    -> ProviderExecution
```

`protocol.py` defines these concrete fields: `ProviderRequest(provider, model,
messages, endpoint, task_class, requested_capabilities, privacy_class,
routing_event_id, outbound_request_id)`, `ProviderResponse(text, provider,
requested_model, resolved_model, actual_provider, actual_model,
provider_request_id, usage, actual_cost, response_headers)`, `RouteRequest(provider,
model, task_class, requested_capabilities, privacy_class, free_first)`, and
`RoutingDecision(selected_provider, selected_model, endpoint, routing_event_id,
free_eligible, cost_class, account_class, routing_reason, fallback_chain)`. The
`ProviderExecution` result contains `decision`, `response`, `failover_chain`,
the unchanged semantic `attempt_id`, and `execution_proof`. The proof contains
`routing_event_id`, attempt, selected/actual identity, usage, cost, free status,
and failover metadata. `NoEligibleProvider` carries the stable code
`NO_ELIGIBLE_FREE_PROVIDER`; it is not a provider response.

The router selects a route before HAMH resolution. HAMH resolves the harness
profile for the selected route; it does not select an outbound provider.

The canonical path is:

`standard dispatch -> free route A -> technical provider failure -> free route B`.

The implementation must distinguish:

- model failover: same provider, different model;
- provider failover: different provider, same semantic request;
- semantic task retry: a new task attempt controlled by the existing harness.

Provider failover does not increment the harness semantic attempt and does not
create a second controller or router. The bounded ceiling is read from
`AUTODEV_PROVIDER_FAILOVER_MAX`, defaults to `3`, is clamped to at least one,
and limits provider candidates attempted for one dispatch. It is not a quota
sharing mechanism and it is not a task retry budget.

The first external provider pool is exactly Groq plus OpenRouter, after each
route independently reaches selection-to-execution and zero-cost proof. The
router must not treat OpenRouter's free model count as provider redundancy.

### Identity and precedence

`backend` remains the existing execution-backend selector. Existing
`provider`/`model` request fields remain HAMH profile preferences for
compatibility and are never proof of outbound ownership. The provider runtime
uses separate fields:

- `route_provider`, `route_model`, `route_endpoint`, `route_account_class`:
  authoritative router decision;
- `harness_provider`, `harness_model`: HAMH resolution inputs;
- `selected_provider`, `selected_model`: persisted route decision;
- `resolved_model`, `actual_provider`, `actual_model`: transport evidence only.

Caller-supplied provider/model values are constrained preferences. `_dispatch()`
passes them to the router; the router may reject or replace them. An ineligible,
paid, privacy-gated, or retired preference cannot control the outbound request.

### Provider failure policy

Only these failures permit technical provider failover within the same semantic
attempt: connection/DNS/TLS failure before a response, client timeout before a
response is received, HTTP 408, HTTP 429, and HTTP 500/502/503/504. HTTP 429 or
provider quota exhaustion marks that route temporarily unavailable in the
decision state. HTTP 400/401/403/404/422, content-policy/security responses,
malformed requests, and an uncertain timeout after request bytes may have been
processed are terminal and do not trigger a second provider call. The final
error maps to existing adapter `failure_class=PROVIDER_FAILURE` with a stable,
non-secret failure signature.

The candidate list is unique by route identity and capped by
`AUTODEV_PROVIDER_FAILOVER_MAX`. A provider switch is never a semantic retry.
The catalog endpoint must exactly equal the configured adapter endpoint before
the request is sent. POST requests carry the stable outbound request ID as an
idempotency key. Missing, malformed, negative, or non-finite provider cost is
not zero-cost proof and fails the execution proof.

### Groq transport

The OpenAI-compatible request builder must set an honest stable application
identity, for example `Morpheus-AutoDev/<version>`, only when `User-Agent` is
absent. Explicit provider-owned headers retain precedence. Caller-supplied
`Authorization`, cookies, API-key headers, and equivalent credentials are never
accepted; the adapter injects `Authorization` from its provider-specific
deployment credential. `Content-Type`, request body, and provider credentials
remain unchanged.

### DeepSeek and paid escalation

Morpheus route eligibility must reject DeepSeek identifiers in provider names or
model names, including DeepSeek models exposed through OpenRouter. It must not
be selected automatically, used as fallback, retried as a provider route, or
used for paid escalation. `AUTOMATIC_PAID_AGENT_ESCALATION` is hard false in the
runtime policy. If all free candidates are unavailable, the result is
`NO_ELIGIBLE_FREE_PROVIDER` and no paid adapter is called. Historical DeepSeek
evidence remains untouched.

### Observability

Existing fields remain current where already present. The provider runtime must
add only fields it can populate from the real request/response seam:

- `selected_provider`, `selected_model`, `routing_reason`: target fields;
- `resolved_model`, `actual_provider`, `actual_model`: target fields populated
  from the response and transport headers where available;
- `attempt`: existing harness attempt identity, not provider failover count;
- `usage`, `actual_cost`, `free_eligible`: target execution evidence;
- `failover`: target provider-failover chain and outcome.

The persisted `provider.execution-proof.v1` record has mandatory
`routing_event_id`, `attempt_id`, `selected_provider`, `selected_model`,
`free_eligible`, and `execution_proof`; optional actual/resolved identity,
usage, cost, and failover fields are null when the transport cannot prove them.
`NOT_REQUIRED` is used only for fields explicitly outside a seam, never for
missing required evidence. `routing_event_id` correlates route selection,
outbound request, response, and adapter ledger record.

Privacy is explicit route metadata. A route is eligible for `PRIVATE_CODE` or
`PRIVATE_REPOSITORY` only when its catalog entry contains versioned
`privacy_policy` evidence with `version`, `provider_policy_ref`,
`request_data_class`, `retention_class`, and `approved=true`. Missing, stale,
contradictory, or non-approved privacy evidence fails closed. Prompts and
request bodies are never persisted in catalog, routing proof, telemetry, or
error strings.

`response_headers` is transient and allowlisted to non-secret identity and
rate-limit metadata. It never contains `Authorization`, cookies, API keys, or
raw headers and is not persisted outside the execution proof's allowlisted
fields.

Catalog authority is split: adapters discover, policy evaluation classifies,
the live-proof verifier promotes evidence stages, and the router selects. The
router does not rewrite evidence. Catalog/capability writes are atomic,
deployment-owned files; invalid, contradictory, or stale records fail closed.

Quota and health are catalog state, not claims of shared quota. Shared quota is
out of scope. Shadow and canary contracts are post-closure follow-up and are
not acceptance criteria. Production cutover is not part of this issue.

## Authentication Contract

The adapter endpoint requires:

- validator: `Handler._auth()` in `adapter/harness_adapter_v2.py`;
- expected secret source: `TOKEN_FILE`, derived from `AUTODEV_V2_STATE`;
- supplier: the service/control-plane caller that owns the token file and sends
  the request;
- header: `X-Harness-Token`;
- protection: execution-plane job, batch, and artifact endpoints are not
  reachable as unauthenticated control-plane actions.

The contract documents no token value. Morpheus's token is unrelated to
OpenCode's credentials. No code reads OpenCode `auth.json` for this contract.

## Acceptance Criteria

- [ ] Four Delta artifacts agree on current reality and target files.
- [ ] Groq default User-Agent is present, stable, non-secret, and default-only.
- [ ] Explicit headers, auth, content type, and body are preserved.
- [ ] Dynamic catalog discovery filters by zero-cost evidence, availability,
      capability, privacy, health, and quota.
- [ ] Groq and OpenRouter each have route-specific live selection-to-execution
      and zero-cost evidence, or are excluded from the free pool.
- [ ] Standard dispatch performs bounded technical provider failover without a
      semantic task retry.
- [ ] Both failover directions are covered by deterministic tests; live proof is
      attempted only with controlled health state and no limit exhaustion.
- [ ] DeepSeek is absent from Morpheus eligible/routing/fallback/retry/escalation
      paths, and free-pool exhaustion returns `NO_ELIGIBLE_FREE_PROVIDER`.
- [ ] Observability correlates selected and actual identity, attempt, usage,
      cost/free status, failure, and failover where available.
- [ ] No paid request, automatic paid fallback, shared quota, shadow, canary, or
      production cutover is introduced.
- [ ] Targeted tests and `git diff --check` pass.

## Test Definitions

### Current-baseline checks

These are executable before implementation and prove the starting seam only:

- `python3 runtime/tests/test_contracts.py`
- `python3 runtime/tests/test_validator_equivalence.py`
- `python3 -m json.tool "n8n/workflows/autodev/00 AutoDev API Start.json"`
- `git diff --check`

### Post-implementation checks

These become executable only after the named target modules/tests are added:

- `python3 runtime/tests/test_provider_runtime.py`
- `python3 runtime/tests/test_provider_adapter_integration.py`
- `python3 runtime/tests/test_provider_transport.py`
- `python3 runtime/tests/test_adapter_auth.py`
- `PYTHONPATH=runtime python3 -m providers.refresh`

Provider contract samples and invalid samples are embedded in
`runtime/tests/test_provider_runtime.py`; the exact persisted schema is
`runtime/contracts/schemas/provider.execution-proof.v1.schema.json`, registered
in `runtime/contracts/registry.py` and validated by
`python3 runtime/tests/test_contracts.py`.

The offline tests cover HTTP 408/429/5xx, connection failure, terminal
4xx/security failure, uncertain timeout, both Groq->OpenRouter and
OpenRouter->Groq failover directions, unchanged `attempt_id`, caller
preference rejection, and exact `NO_ELIGIBLE_FREE_PROVIDER` behavior. Live
commands are opt-in evidence runs after offline tests pass; they use deployment
credentials, finite timeouts, redacted evidence, and no DeepSeek/paid route.

Live Groq/OpenRouter evidence is recorded without credentials or raw response
secrets. Paid and DeepSeek live calls are prohibited. The known 18 collection
holdouts remain a separate full-regression status.

## Non-Goals

- Shared quota implementation.
- Shadow or canary readiness contracts.
- Production cutover.
- Local OpenCode configuration changes.
- New n8n workflows, databases, dashboards, or control planes.
- Automatic paid fallback or paid provider testing.
