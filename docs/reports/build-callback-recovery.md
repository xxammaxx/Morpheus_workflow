# BUILD callback recovery — 2026-09-01

## Classification

```text
BUILD_FAILURE_REPRODUCED=PASS
BUILD_FAILURE_CLASS=BUILD_CALLBACK_NOT_SENT;BUILD_STATE_TRANSITION_MISSING;NO_ELIGIBLE_FREE_MODEL
BUILD_FAILURE_ROOT_CAUSE=The deployed adapter rejects opencode/big-pickle at its live capability gate before creating build:1. BUILD_CAPABLE=false and no tool-probe PASS are present. The prior n8n Execute Workflow error path then stopped without persisting a terminal failure.
```

The first broken edge is the Build dispatch from n8n to the adapter. This is
not provider latency: no Build provider request, provider response, adapter
terminal result, or callback exists in the reproduced failure.

## Chronology

| UTC timestamp | Producer → consumer | State | HTTP | Contract/result |
|---|---|---|---:|---|
| 06:26:28.000 | adapter → n8n, plan completion | PLANNING → PLANNING | 200 | `autodev.plan.v1`, `PLAN_GATE_APPROVED` |
| 06:26:28.401 | n8n Build State Update → `autodev_runs` | PLANNING → BUILDING | 200 | `autodev.run-row.v1`, row 312 persisted |
| 06:26:32.607 | n8n Run Build → adapter `POST /v1/jobs` | BUILDING → BUILDING | 400 | `autodev.build-input.v1`, `NO_ELIGIBLE_FREE_MODEL` |
| 08:34:04.979 | n8n Build Failed Update → `autodev_runs` | BUILDING → FAILED | 200 | `autodev.run-row.v1`, `BLOCKED / BUILD_FAILED` |

The first three rows are the failed reproduction run
`run-mb-bf5449adfc207d6b52d4` (n8n execution `16679`). The last row is the
post-fix disposable smoke `run-mb-4f2c8594725a8849db5d`, execution `16849`.

## Callback and state contract

The adapter implements an optional `resume_url` envelope with
`run_id`, `job_id`, `attempt_id`, `job_type`, `status`, `result`, and `error`.
The canonical generated Build workflow does not supply `resume_url`; it polls
`GET /v1/jobs/{job_id}` instead. Therefore the failed request cannot be
classified as callback transport, authentication, schema, or identity loss:
the Build job was never accepted and no callback was produced.

Before the fix, the expected failure transition was present in the generated
workflow but unreachable when `Run Build` raised an Execute Workflow error.
The minimal fix sets `Run Build.onError=continueRegularOutput`, exposing the
existing `Post-Build → Build OK? → Build Failed` branch. It does not change
model selection, task inputs, or terminality semantics.

## Fix and deployment

```text
FIX_HEAD=bfb4ba6
BUILD_FIX_IMPLEMENTED=PASS
BUILD_FIX_DEPLOYED=PASS
SOURCE_WORKFLOW_SHA256=5c472e8a827b7b8886ed9047ca65362cf195b15f2d34709be7bac3a3aed0c234
GENERATED_WORKFLOW_SHA256=298ecce704e4cac8e0bb7102040a74648d4bde88b5cc5fa66565d64b067155f0
DEPLOYED_WORKFLOW_SHA256=298ecce704e4cac8e0bb7102040a74648d4bde88b5cc5fa66565d64b067155f0
WORKFLOW_DRIFT=false
```

The deployed workflow is active. The regression test failed before the fix
because `onError` was absent and passes after the fix. The new smoke proves
the failure is terminal, but not successful: it ends `FAILED` at the adapter
capability gate.

## Gates

```text
PAID_REQUESTS=0
DEEPSEEK_REQUESTS=0
HOLDOUT_EXECUTION_COUNT=0
CONTEXT_SMOKE=NOT_RUN_BASELINE_GATE
A_E_EXECUTION_READY=false
```

The remaining owner/runtime action is to restore or explicitly prove a
zero-cost Build-capable route for `opencode/big-pickle` without bypassing the
adapter capability gate. No routing redesign or capability override was made.
