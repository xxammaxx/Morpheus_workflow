# Canonical n8n intake run-ID recovery — 2026-09-02

## Result

The provider-free live replay of `POST /webhook/autodev/start` returned
`HTTP 200` with `Content-Type: application/json` and an empty response body.
The same raw empty-body behavior was observed on the status webhook. No
provider request was sent.

The repository trace showed that `00 AutoDev API Start` persisted the run row
before the response path, but attached `Respond 202` to the downstream
`Pass Intake` branch. The minimal fix in commit
`81f0d2d3147959e6664924a5d13425af51abdbd6` connects `Insert Run Row` directly
to `Respond 202` and projects the canonical `run_id` from
`Prepare Run Row.data[0].run_id`. The orchestrator remains on its separate
continuation path.

## Deployment blocker

The documented PVE n8n API key and the live CT `N8N_API_KEY` both returned
`401 unauthorized` for the n8n Public API. Therefore the tested fix could not
be imported into live n8n, and deployed-head provenance remains unproven.
No direct database update or UI-only runtime patch was used.

```text
CANONICAL_INTAKE_CONTRACT_E2E=NOT_RUN_POST_FIX
DEPLOYMENT_HEAD_MATCH=BLOCKED
EXACT_ROUTE_PROBE=NOT_RUN
BASELINE=NOT_RUN
CONTEXT=NOT_RUN
HOLDOUT_EXECUTION_COUNT=0
PAID_REQUESTS=0
DEEPSEEK_REQUESTS=0
ACTUAL_COST=0
```

The local workflow regression suite and full repository suite passed before
the deployment attempt: `173 passed`; Python compilation, generated n8n Code
node syntax, and `git diff --check` also passed.
