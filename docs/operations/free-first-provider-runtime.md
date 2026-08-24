# Free-First Provider Runtime Operations

## Feature Switch

`AUTODEV_FREE_FIRST_ENABLED` is the existing runtime switch. Production
activation remains subject to the catalog, privacy, and cost gates below.

Useful settings:

- `AUTODEV_PROVIDER_CATALOG`: catalog snapshot path.
- `AUTODEV_PROVIDER_CAPABILITIES`: staged capability registry path.
- `AUTODEV_PROVIDER_FAILOVER_MAX`: bounded provider failover ceiling, default 3.
- `AUTODEV_PROVIDER_PROBE_LEASE`: root-only atomic maintenance-lease state;
  leases are provider-specific, expire within 120 seconds, and permit one
  diagnostic request.
- `AUTODEV_LOCAL_ZERO_COST_TRUSTED_ENDPOINTS`: explicit comma-separated local
  endpoint allowlist. An unknown or public endpoint is never classified as
  `LOCAL_ZERO_COST`.

## Maintenance

Refresh discovery and health outside n8n:

```text
PYTHONPATH=runtime python3 -m providers.refresh
```

The command writes only metadata. It never prints credential values, runs
capability probes, creates accounts, accepts terms, or makes payment changes.

The n8n operations API uses the existing root-only key at
`/var/lib/n8n-spec-kit/secrets/ghiw-n8n-api-key` (mode `0600`); the value is
never stored in the repository or evidence. Provider credentials remain in the
root-only `provider.env` state file.

## Status and Evidence

- Canonical run status remains `02 AutoDev API Status`.
- Adapter catalog metadata is available at authenticated
  `/v1/providers/catalog`.
- Attempt rows use additive provider/routing/cost fields. Existing fields and
  the `autodev_attempts` table remain the source of truth.
- No destructive migration is required for the JSON/Data Table contract;
  deployments that enforce fixed Data Table columns must add the fields
  `requested_model`, `resolved_model`, `actual_provider`, `actual_model`,
  `cost_class`, `quota_state`, `provider_health`, `routing_reason`,
  `fallback_chain`, `paid_escalation`, `paid_escalation_reason`, and
  `actual_cost` additively before activation.

## Safety

- `UNKNOWN` never enters the free pool.
- Positive cost on a free route quarantines the exact path.
- Provider failover is not semantic task retry.
- During an active probe lease, ordinary traffic to that provider fails closed;
  after success, failure, or TTL expiry the lease is released or expires.
- Free-pool exhaustion returns `NO_ELIGIBLE_FREE_PROVIDER`; it never falls
  back to DeepSeek or a paid provider.
- DeepSeek remains paid escalation only unless explicitly selected by policy.
- Disable the feature switch to restore the previous adapter path.

## V1 production state

The verified production free pool is OpenRouter plus Ollama. OpenRouter uses
the external `openrouter/free` hard-stop route; Ollama uses the explicitly
trusted private local endpoint. Groq transport is retained as an optional
future provider, but its account tier remains UNKNOWN and it is not free
eligible. Automatic paid escalation and DeepSeek execution remain disabled.

The maintenance-only variable `AUTODEV_MAINTENANCE_FAIL_PROVIDER` is unset by
default and was cleared after the final reverse-failover proof. It must never
be enabled outside a bounded, authorized maintenance run.
