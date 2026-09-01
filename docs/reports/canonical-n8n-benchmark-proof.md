# Morpheus canonical n8n benchmark proof

Date: 2026-08-31

## Result

One disposable benchmark task was sent through the deployed canonical path:

```text
benchmark task
→ POST /webhook/autodev/start
→ canonical autodev_runs row
→ 01 AutoDev Orchestrator
→ 10/20/30 workflows
→ Adapter v2
→ opencode/big-pickle
→ canonical PLAN_BLOCKED state
→ Control Tower projection
```

The task was read-only and marked benchmark-only. It used a public disposable
clone and did not mutate production code, infrastructure, secrets, or model
weights.

```text
BENCHMARK_EXPERIMENT_ID=morpheus-benchmark-disposable-canonical-20260831-r2
BENCHMARK_RUN_ID=run-mthenxhx-qvim85
N8N_CANONICAL_RUN_ID=run-mthenxhx-qvim85
AUTODEV_RUN_ID=run-mthenxhx-qvim85
ADAPTER_RUN_ID=run-mthenxhx-qvim85
CONTROL_TOWER_RUN_ID=run-mthenxhx-qvim85
N8N_RUN_STATE=PLAN_BLOCKED
N8N_RUN_REASON=CONTRACT_FAILURE
```

## Correlation and provenance

The adapter ledger contained the same `run_id` and deterministic job/attempt
IDs (`run-mthenxhx-qvim85:<stage>:1`). Adapter evidence recorded
`selected_provider=opencode`, `selected_model=big-pickle`, and for all three
research executions `actual_provider=opencode`, `actual_model=big-pickle`,
`actual_cost=0.0`, `execution_proof=PASS`. The plan execution failed closed at
the output contract gate, so it has no actual execution proof.

The Control Tower showed the same run in its canonical run projection, with
the terminal state `PLAN_BLOCKED` and reason `CONTRACT_FAILURE`. This proves
the run-ID chain but not the stronger full-correlation contract:

```text
run_id equality                         PASS
selected provider/model                 PASS
actual zero-cost research provenance    PASS
non-empty correlation_id propagation    FAIL / empty in current workflow
complete terminal task success          FAIL / PLAN_BLOCKED
CANONICAL_N8N_BENCHMARK_CORRELATION     PARTIAL
```

The current canonical workflow does not yet propagate the adaptive factor
policies, `benchmark_experiment_id`, and `correlation_id` into every adapter
attempt. No equality or value claim is fabricated to compensate for that.

## A–E, validation, and holdout

The direct adapter smoke already recorded `A/B/C` functional success, but it
was not a canonical n8n execution. Since the canonical run stopped at plan
contract validation and the adaptive policies are not wired through n8n,
canonical A–E cannot be attributed or compared:

```text
A_BASELINE=NOT_RUN_AS_CANONICAL_VALUE_TRIAL
B_CONTEXT=NOT_RUN
C_EXPLORER=NOT_RUN
D_EXPERIENCE_TOP1=NOT_RUN
E_EXPERIENCE_TOP3=NOT_RUN
VALIDATION=NOT_RUN
CANDIDATE_FREEZE=NOT_RUN
HOLDOUT=NOT_RUN
GENERALIZATION_PROVEN=NO
```

This is an honest infrastructure/contract blocker, not evidence that the
adaptive factors have or do not have value.

## Safety gates

```text
SAFE_ZERO_COST_ROUTE=PASS
BENCHMARK_PROVIDER=opencode
BENCHMARK_MODEL=big-pickle
PAID_REQUESTS=0
DEEPSEEK_REQUESTS=0
AUTOMATIC_PAID_ESCALATION=false
BENCHMARK_PRODUCTION_STATE_WRITES=0
N8N_SOLE_CONTROL_PLANE=true
SECOND_SOR=false
MODEL_WEIGHTS_CHANGED=false
AUTO_PROMOTION=false
RELEASE_CREATED=false
```

## Current recovery run — 2026-08-31

After deployment of the minimal plan-contract and provenance fix, the real
canonical path accepted a full metadata envelope. The provider-free contract
smoke `run-mthmymeg-1z6039` reached `DONE`; its n8n row, Control Tower detail,
and six adapter jobs agreed on all provenance fields. A separate
`opencode/big-pickle` run `run-mthmq1hw-4gyrdb` reached baseline and research,
then was aborted as a disposable cleanup when the three research calls did
not complete in the bounded observation window.

```text
PLAN_CONTRACT=PASS_LOCAL_AND_DEPLOYED
CANONICAL_METADATA_CONTRACT=autodev.adaptive-metadata.v1
EXPERIMENT_ID_PROPAGATION=PASS
FACTOR_PROPAGATION=PASS
CONFIG_HASH_PROPAGATION=PASS
CANONICAL_EMBEDDED_SMOKE=run-mthmymeg-1z6039 / DONE
OPENCODE_BIG_PICKLE_SMOKE=run-mthmq1hw-4gyrdb / ABORTED
A_E_CANONICAL=NOT_RUN
VALIDATION=NOT_RUN
CANDIDATE_FREEZE=NOT_RUN
HOLDOUT=NOT_RUN
```

The current MorpheusBench task files provide hashes and labels but no
executable repository/task payloads. Running A–E would require inventing task
content, so the value proof remains open. See
[`plan-contract-recovery.md`](plan-contract-recovery.md) and
[`canonical-metadata-20260831.json`](../../evidence/adaptive-harness/canonical-metadata-20260831.json).

## Executable suite implementation — 2026-09-01

The former hash-only placeholders are now executable task definitions with
bounded setup, tools, mutation policy, verifier, timeout, cleanup, and
immutable fixture/task hashes. The runner starts runs only through the
canonical n8n start webhook and persists idempotent evidence keyed by
experiment, task, factor, and config hash. Development and validation
loaders cannot open holdout; experience selection accepts only verified prior
development records and excludes the same task.

The live baseline smoke `run-mb-bf5449adfc207d6b52d4` and context smoke
`run-mb-7df82a34c3e43aceb2a9` both reached the real n8n/adapter chain, but the
deployed orchestration remained non-terminal at the build/research boundary.
They were recorded as timeouts and safely aborted. Consequently no A–E,
validation, candidate freeze, or holdout claim is made.

```text
TASK_SCHEMA_GATE=PASS_LOCAL
TASK_FIXTURE_GATE=PASS_LOCAL
TASK_PATH_SECURITY_GATE=PASS_LOCAL
HOLDOUT_ISOLATION=PASS_LOCAL
HOLDOUT_EXPERIENCE_LEAKAGE=PASS_LOCAL
RUNNER_CANONICAL_N8N_PATH=PASS_INTAKE;FAIL_TERMINAL_COMPLETION
RUNNER_RESULT_PERSISTENCE=PASS_TIMEOUT_EVIDENCE
PAID_REQUESTS=0
DEEPSEEK_REQUESTS=0
```

## BUILD recovery — 2026-09-01

The forensic trace is recorded in
[`build-callback-recovery-2026-09-01.json`](../../evidence/morpheus-bench/build-callback-recovery-2026-09-01.json).
The first broken edge was the adapter's capability gate during the n8n Build
dispatch. The live `opencode/big-pickle` entry was healthy and zero-cost, but
did not carry `BUILD_CAPABLE` or a passing tool-probe record. The adapter
returned HTTP 400 before creating `run_id:build:1`; consequently no provider
request, worker result, or callback existed to consume. This is not provider
latency and not callback transport loss.

The parent workflow had a separate terminality defect: an Execute Workflow
error stopped the branch while the row remained `BUILDING`. Commit `bfb4ba6`
sets `Run Build.onError=continueRegularOutput`, allowing the existing
`Post-Build -> Build Failed` path to persist `FAILED / BLOCKED / BUILD_FAILED`.
The fix was deployed to the active orchestrator, and run
`run-mb-4f2c8594725a8849db5d` proved the terminal failure transition.

```text
BUILD_FAILURE_CLASS=NO_ELIGIBLE_FREE_MODEL;BUILD_STATE_TRANSITION_MISSING
BUILD_CALLBACK_SENT=false
BUILD_CALLBACK_ACCEPTED=false
BUILD_FIX_DEPLOYED=true
BUILD_FIX_RUNTIME_PROOF=FAILED_RUN_TERMINAL
RUNNER_SMOKE_BASELINE=FAILED_TERMINAL_CAPABILITY_GATE
RUNNER_SMOKE_CONTEXT=NOT_RUN
A_E=NOT_RUN
VALIDATION=NOT_RUN
HOLDOUT_EXECUTION_COUNT=0
```

No model capability was overridden and no paid or DeepSeek route was used.

## Capability refresh recovery — 2026-09-01

The post-fix BASELINE `run-mb-722b6de824551f771150` accepted Build, created
`build:1`, and reached Big-Pickle. It terminalized with
`CONTRACT_FAILURE / BUILD_NO_CHANGES`; the verifier did not execute on that
failure path. `BASELINE_PIPELINE_READY=NO`, so CONTEXT_COMPILER was not run.
