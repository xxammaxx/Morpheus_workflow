# Free-First Provider Runtime Operations

## Feature Switch

`AUTODEV_FREE_FIRST_ENABLED` defaults to `false`. Enable only in a shadow or
canary environment after catalog, privacy, and cost policy review.

Useful settings:

- `AUTODEV_PROVIDER_CATALOG`: catalog snapshot path.
- `AUTODEV_PROVIDER_CAPABILITIES`: staged capability registry path.
- `AUTODEV_PROVIDER_FAILOVER_MAX`: bounded provider failover ceiling, default 3.

## Maintenance

Refresh discovery and health outside n8n:

```text
PYTHONPATH=runtime python3 -m providers.refresh
```

The command writes only metadata. It never prints credential values, runs
capability probes, creates accounts, accepts terms, or makes payment changes.

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
- DeepSeek remains paid escalation only unless explicitly selected by policy.
- Disable the feature switch to restore the previous adapter path.
