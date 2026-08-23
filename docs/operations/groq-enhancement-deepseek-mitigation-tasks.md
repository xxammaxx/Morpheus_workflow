# Free-First Runtime Closure Tasks

Issue: `xxammaxx/Morpheus_workflow#1`

Each task is atomic, mapped to a real baseline seam or an explicitly named
target file, and has an executable verification.

## T1 Authentication and Baseline Contract

- Current seam: `adapter/harness_adapter_v2.py`, `Handler._auth()` and
  `TOKEN_FILE`.
- Document token supplier, `X-Harness-Token` header, file location, and trust
  boundary without values.
- Add an offline auth regression test using a temporary token file and
  `Handler._auth()`; no current adapter auth test exists.

## T2 Provider Protocol and Catalog

- Target files: `runtime/providers/protocol.py`, `catalog.py`, `adapters.py`.
- Define `ProviderRequest`, `ProviderResponse`, `RouteRequest`, and the
  `RoutingDecision`, `ProviderExecution`, and `ProviderAdapter` discovery/invoke
  signatures in `protocol.py`, including required fields and the
  `NoEligibleProvider` code.
- Add route identity, zero-cost evidence stages, account class, privacy, health,
  quota, capability, and quarantine state.
- Discover model metadata through provider adapters; never hardcode a screenshot
  catalog as the authoritative free pool.
- Verify with `runtime/tests/test_provider_runtime.py` and contract validation.

## T3 Capability Evidence

- Target file: `runtime/providers/capabilities.py`.
- Preserve existing task/profile names (`research`, `plan`, `build`, `fix`,
  `review`, `verify`, `baseline`) and map staged probes to those roles.
- Verify staged evidence is persisted without credentials or prompts.

## T4 Groq Transport

- Target file: `runtime/providers/adapters.py`.
- Add a stable honest application User-Agent only when the caller did not
  provide one. Preserve explicit provider-owned headers, content type, and body.
- Reject/strip caller Authorization, cookies, API-key headers, and raw headers.
- Verify with `python3 runtime/tests/test_provider_transport.py` that headers
  are allowlisted and secrets never enter results.

## T5 Canonical Provider Routing

- Target files: `runtime/providers/router.py`, `runtime/providers/runtime.py`.
- `ProviderRuntime.select(RouteRequest)` returns the route decision;
  `ProviderRuntime.invoke_with_failover(..., attempt_id)` returns a
  `ProviderExecution` containing the unchanged semantic `attempt_id`, an
  `execution_proof`, and response, or `NO_ELIGIBLE_FREE_PROVIDER`.
- Read `AUTODEV_PROVIDER_FAILOVER_MAX`, default `3`, clamp to one or higher.
- Route only route-specific free-eligible candidates by default.
- Distinguish model failover, provider failover, and semantic task retry.
- Verify both provider failover directions using deterministic local HTTP
  fixtures, with unchanged semantic attempt identity.

## T6 Standard Adapter Dispatch

- Target seam: `_dispatch()` and new `ProviderRuntime.invoke_with_failover(...)`
  helper in
  `adapter/harness_adapter_v2.py`.
- `_dispatch()` passes `route_decision` to `new_job()` and `run_job_thread()`;
  the provider-direct branch calls `_provider_direct_completion()` and passes
  `ProviderExecution` to `finalize_job()`.
- Integrate the provider runtime into the existing dispatch path, retaining the
  existing n8n adapter boundary and job ledger.
- Persist only real selected/resolved/actual identity, usage, cost/free status,
  failure, and failover fields.
- Verify `test_provider_adapter_integration.py` proves selection controls the
  outbound request.

## T7 DeepSeek and Paid Guard

- Target seams: provider policy, router, and `_dispatch()`.
- `AUTOMATIC_PAID_AGENT_ESCALATION` is an implementation constant/policy guard,
  not an environment override; it is always `False` for Morpheus agent
  execution.
- Make DeepSeek ineligible for Morpheus agent execution and force automatic paid
  escalation false. Preserve historical evidence and do not change OpenCode.
- Verify free-pool exhaustion returns `NO_ELIGIBLE_FREE_PROVIDER` and makes no
  paid or DeepSeek request.

## T8 Contracts and Workflow Validation

- Target files: provider schemas and `runtime/contracts/registry.py`, only as
  required by real persisted provider records.
- Add the exact target schema
  `runtime/contracts/schemas/provider.execution-proof.v1.schema.json`, register
  `provider.execution-proof.v1`, and validate canonical/invalid samples embedded
  in `runtime/tests/test_provider_runtime.py`.
- Validate canonical samples and invalid cases using the existing Python
  contract runner. Validate every changed n8n JSON with `python3 -m json.tool`.

## T9 Review Gates

- Architecture review: current/target truth, standard dispatch authority,
  provider/model distinction, failover, and no invented interfaces.
- Security/cost review: token boundary, credential separation, zero-cost proof,
  privacy, paid/DeepSeek exclusion, and secret leakage.
- Implementability review: every file/function/command exists or is explicitly a
  target and every acceptance gate is executable.
- Repair all valid blocking findings and repeat until zero remain.

## T10 Live Evidence and Regression

- Prove Groq adapter status 200 and selection-to-execution only on an authorized
  zero-cost route.
- Reconfirm OpenRouter with one minimal smoke request and route-specific proof.
- Refresh the dynamic catalog and promote only 2-4 capability-backed role
  candidates.
- Run targeted provider, adapter, contract, HTTP, routing, exclusion,
  observability, and n8n JSON tests, then `git diff --check`.
- Keep the known 18 collection failures as separate holdouts if unchanged.

Live evidence is opt-in and does not replace offline tests. No provider secret or
full response is written.

## Completion Gates

`DELTA_SPECKIT_GATE=PASS` requires T1-T9 documented and three reviews with zero
valid blocking findings. `IMPLEMENTATION_ENTRY_GATE=PASS` follows only after
the issue, spec, plan, tasks, ADR, and review results are present.
