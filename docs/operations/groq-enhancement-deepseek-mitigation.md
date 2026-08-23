# Free-First Runtime Closure Runbook

Issue: `xxammaxx/Morpheus_workflow#1`

## Preconditions

- Work only in the clean isolated workspace.
- Keep the original dirty source worktree read-only.
- Confirm the issue is open and the current commit is known.
- Do not read or print credential values.
- Do not call DeepSeek or any paid route.

## Authentication Boundary

The Morpheus execution adapter validates `X-Harness-Token` in
`adapter/harness_adapter_v2.py` using the content of `TOKEN_FILE`, derived from
`AUTODEV_V2_STATE` and defaulting under `/var/lib/autodev-harness-v2`. The
control-plane/service owner supplies the header. OpenCode credentials are a
separate system and are not read by Morpheus.

## Configuration Contract

Current committed baseline has no provider environment variables. The provider
runtime introduced by this issue defines only these new runtime controls:

- `AUTODEV_FREE_FIRST_ENABLED`: enables provider routing; default `false`.
- `AUTODEV_PROVIDER_CATALOG`: catalog snapshot path; default
  `/var/lib/autodev-harness-v2/provider-catalog.json`.
- `AUTODEV_PROVIDER_CAPABILITIES`: capability evidence path; default next to
  the catalog as `provider-capabilities.json`.
- `AUTODEV_PROVIDER_FAILOVER_MAX`: maximum provider candidates attempted for one
  dispatch; default `3`, minimum effective value `1`. It does not increment a
  semantic harness attempt and does not implement shared quota.
- `AUTODEV_GROQ_ACCOUNT_CLASS` and `AUTODEV_OPENROUTER_ACCOUNT_CLASS`: explicit
  deployment account-class evidence; `unknown` is never free eligible.
- `AUTODEV_GROQ_USAGE_TERMS_APPROVED` and
  `AUTODEV_OPENROUTER_USAGE_TERMS_APPROVED`: affirmative usage-policy evidence
  required for discovery entries.
- `AUTODEV_GROQ_PRIVACY_APPROVED` and
  `AUTODEV_OPENROUTER_PRIVACY_APPROVED`: affirmative privacy-policy evidence
  required for private-code routes.

Provider credentials are environment inputs owned by deployment and are never
written to evidence. The runtime must not infer free eligibility from the mere
presence of a credential.

## Refresh and Discovery

The provider catalog maintenance entry point is a new target created by T2:

`PYTHONPATH=runtime python3 -m providers.refresh`

It discovers currently advertised models through the configured provider
adapters, applies route-specific cost/account/privacy policy, loads staged
capability evidence, refreshes health/quota metadata, and writes the catalog
atomically. Discovery is dynamic; model names from screenshots or old evidence
are not hardcoded as the free pool.

The pipeline is:

`discover -> zero-cost filter -> availability filter -> capability filter -> privacy filter -> health/quota filter -> deterministic rank -> route`.

OpenRouter model multiplicity is model redundancy. It is not provider
redundancy. Provider redundancy is established only by independent Groq and
OpenRouter selection-to-execution proofs.

## Standard Dispatch and Failover

The existing adapter remains the execution boundary. The exact canonical
standard dispatch seam is `_dispatch()` in
`adapter/harness_adapter_v2.py`. Its target flow is:

`_dispatch()` validates and normalizes caller preferences ->
`ProviderRuntime.select(RouteRequest)` -> HAMH resolve with explicit
`harness_provider`/`harness_model` mapped from the selected route ->
`new_job(route_decision=...)` -> `run_job_thread(route_decision=...)` ->
`_provider_direct_completion()` -> `ProviderRuntime.invoke_with_failover(...)`
-> `finalize_job(provider_execution=...)`.

The provider runtime is called from the existing worker path for
provider-direct jobs; it is not a second control plane. Local `embedded` and
`opencode-builder-8001` jobs without a route decision retain the existing
backend handlers and cannot enter external provider failover.

1. `_dispatch()` validates the existing contract and treats caller provider/model
   as a constrained preference, never as authority.
2. Build a route request from the existing harness task class/profile.
3. Select only eligible free routes unless the request is the existing local
   backend path.
4. Invoke the selected adapter and record selected/resolved/actual identity.
5. On only a retryable technical provider failure, attempt the next bounded free
   provider.
6. Keep the same semantic task attempt and record the provider failover chain.
7. If no free route remains, return `NO_ELIGIBLE_FREE_PROVIDER`.

Provider failover is not a semantic retry. A semantic retry remains owned by the
existing harness attempt loop and is not incremented by provider switching.
The catalog endpoint must exactly match the configured adapter endpoint; a
mismatch fails before any request. Provider POSTs carry the stable outbound
request ID as an idempotency key.

## Groq Transport Procedure

The adapter uses the new OpenAI-compatible Groq endpoint configured in
`runtime/providers/adapters.py`. The request builder adds the application
User-Agent only if absent. Explicit headers win. Validate the request shape with
the HTTP transport test before any live proof.

For live proof, use a non-paid, authorized Groq account route and record only
status, selected/actual identity, usage metadata, and zero-cost evidence. Never
record the API key, authorization header, raw token, or full sensitive response.

## OpenRouter Procedure

Use the new OpenAI-compatible adapter in `runtime/providers/adapters.py` and
dynamically discovered model
metadata. A model is free eligible only after the route-specific evidence stages
are satisfied. Confirm one minimal completion and correlate selection to actual
request without spending beyond the verified free route.

## DeepSeek Retirement Procedure

- Reject DeepSeek during eligible catalog/routing selection.
- Reject DeepSeek identifiers in provider names and model names, including
  DeepSeek models exposed through OpenRouter.
- Ignore paid escalation requests for Morpheus agent execution.
- Do not add or modify local OpenCode configuration.
- Preserve historical DeepSeek evidence as read-only history.
- When all free routes are disabled/unavailable, assert
  `NO_ELIGIBLE_FREE_PROVIDER` and assert no DeepSeek/paid adapter invocation.

## Observability Review

Check the actual persisted job/routing record, not only catalog metadata. The
minimum correlation is selected provider/model, response actual/resolved
provider/model, semantic attempt, usage, cost/free status, failure, and
provider-failover outcome. Fields unavailable at a seam are marked
`NOT_REQUIRED`, not fabricated.

## Security Boundary Limitations

The committed adapter currently uses its configured LAN HTTP listener and a
file-backed shared token. This Delta does not claim TLS/mTLS or change that
deployment boundary; network restriction and transport encryption require a
separate infrastructure issue. Provider changes do not weaken the token check,
expose token values, or add callback destinations. Offline tests use a
temporary token file and redacted values only.

## Rollback

Rollback is a normal git revert of the provider implementation commits in the
clean workspace. Do not reset or restore the original dirty worktree. Historical
evidence is retained. No runtime rollback command is invented by this Delta.

## Out Of Scope

Shared quota, shadow, canary, production cutover, dashboards, account/payment
management, and local OpenCode configuration changes are not runbook steps.
