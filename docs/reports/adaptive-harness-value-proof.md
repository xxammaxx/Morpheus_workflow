# Morpheus Adaptive Harness — Value Proof

Date: 2026-08-31

## Final classification

`AMBER_ADAPTIVE_VALUE_NOT_PROVEN_CONTROL_TOWER_OPERATIONAL_AMBER`

The adaptive foundation remains locally tested without a canonical A–E value
proof. A zero-cost `opencode/big-pickle` route and one disposable canonical
n8n run were verified; the run reached the real adapter and Control Tower but
ended at the plan contract gate. No paid or DeepSeek request was made.

## 1. Reality refresh

```text
CURRENT_BRANCH=feat/adaptive-harness-foundation
CURRENT_HEAD=2f796f4 (foundation commit; report commit follows)
ORIGIN_MAIN=cbd96c0d0e8c2c3fa47d12ea1c291975e9c0d7b6
PR_60_STATE=OPEN
PR_60_HEAD=4fcb4b6ac02f0e1f7a5d7202c01e8544cd20f9c4
PR_60_BASE=main
OPEN_ISSUES=10
LATEST_TAG=v1.2.0
```

At the initial refresh, the worktree contained three modified Continuation
files and untracked Adaptive-Harness files. The Continuation files were
classified as `ATOMIC_CONTINUATION`; the remaining files were classified as
`ADAPTIVE_HARNESS`. A binary diff and an untracked-file archive were created
under `/tmp/morpheus-adaptive-safety-20260831/` before branch manipulation.

## 2. Git isolation and PR #60

The Adaptive branch was created from `main`, so it contains no PR #60 commits.
The Continuation changes were kept in a dedicated local stash while the
Adaptive branch was created and are not present in the Adaptive branch.

```text
ADAPTIVE_BRANCH=feat/adaptive-harness-foundation
PR60_ADAPTIVE_FILES=0
PR60_SCOPE_CLEAN=PASS
PR60_MERGED=false
PR60_PRODUCTION_PROVEN=false
USER_WORK_LOST=false
```

PR #60 remains owner-gated and open. Its claims remain limited to atomic
Continuation behavior: delivery is at-least-once, consumers are idempotent,
and the logical effect is effectively-once where the tested fencing and
durability conditions hold. No `EXACTLY_ONCE` claim is made.

## 3. Benchmark design

The planned matched-compute comparison is:

```text
A  CURRENT_BASELINE
B  A + CONTEXT_COMPILER
C  B + REPO_EXPLORER
D  C + EXPERIENCE_TOP_1
E  C + EXPERIENCE_TOP_3
```

The task fixtures currently cover development, validation and holdout splits,
with repository navigation and serialization classes represented. The
available fixture set does not yet cover every requested task class, so that
limitation must be addressed before interpreting a larger result.

For every candidate, the planned manifest freezes code head, task-set hashes,
harness/context/explorer/experience policy, provider, model, model
parameters, environment and result hash. Development and validation may be
used for configuration; holdout must remain untouched until candidate freeze.
`SCAFFOLD_AWARE_ROUTING` is deferred.

## 4. Live run status

```text
LIVE_BENCHMARK_RUN=BLOCKED
SMOKE_RUN=NOT_RUN
FULL_ABLATION=NOT_RUN
HOLDOUT_RUN=NOT_RUN
BENCHMARK_PROVIDER=LM_STUDIO_SELECTED_BUT_UNAUTHENTICATED
ACTUAL_PROVIDER=UNKNOWN
BENCHMARK_MODEL=UNKNOWN
ACTUAL_MODEL=UNKNOWN
PAID_REQUESTS=0
DEEPSEEK_REQUESTS=0
ZERO_COST_PROVEN=NO_LIVE_REQUEST
HOLDOUT_LEAKAGE=false
```

The LM Studio probe returned an authentication-required response before model
execution. Ollama was unreachable. This is an infrastructure/policy blocker,
not a benchmark failure and not evidence for or against any harness factor.

## 5. Results

No candidate was run. Consequently all task, success, token, tool-call,
latency, retry, cost, transport, semantic and provider-provenance result
fields are `UNKNOWN`, not estimates.

```text
BASELINE=NOT_RUN
CONTEXT_COMPILER=NOT_RUN
CONTEXT_PLUS_EXPLORER=NOT_RUN
EXPERIENCE_TOP1=NOT_RUN
EXPERIENCE_TOP3=NOT_RUN
VALIDATION_BASELINE=UNKNOWN
VALIDATION_BEST_CANDIDATE=UNKNOWN
HOLDOUT_BASELINE=UNKNOWN
HOLDOUT_BEST_CANDIDATE=UNKNOWN
HOLDOUT_DELTA=UNKNOWN
IMPROVEMENT_ATTRIBUTABLE=NO_EVIDENCE
GENERALIZATION_PROVEN=NO
```

Therefore the following gates are intentionally unanswered rather than
green: Context Value, Explorer Value, Experience Value, and Small-Model
Improvement. No claim is made that TOP-1 or TOP-3 is beneficial.

## 6. Infrastructure gates

```text
MORPHEUS_BENCH_IMPLEMENTED=YES
BASELINE_FREEZE=IMPLEMENTED_NOT_LIVE_PROVEN
HOLDOUT_ISOLATION=PASS
CONTEXT_COMPILER=PASS_LOCAL_CONTRACT_TESTS
REPO_EXPLORER=PASS_READ_ONLY_LOCAL_TESTS
EXPERIENCE_CONTRACT_STORE_DISTILLER_RETRIEVAL=PASS_LOCAL_CONTRACT_TESTS
MEMORY_POISONING_GATE=PASS
CANDIDATE_EVALUATION=PASS_LOCAL_CONTRACT_TESTS
ARCHITECTURE_GATE=PASS
SECURITY_GATE=PASS
SECRET_SCAN=PASS
MODEL_WEIGHTS_CHANGED=false
AUTO_PROMOTION=false
N8N_SOLE_CONTROL_PLANE=true
SECOND_SOR=false
BENCHMARK_PRODUCTION_STATE_WRITES=0
EXPERIENCE_STORE_CANONICAL_RUN_SOR=false
CONTROL_TOWER_ADAPTIVE_OBSERVABILITY=DEFERRED
```

The pre-isolation combined worktree reported `168 passed`; the isolated
Adaptive branch reports `153 passed`. `python3 -m compileall -q runtime`,
targeted Adaptive/contract/Continuation tests, `node --check`, `git diff
--check` and the repository secret scan are required before commit; the
unavailable `python` executable is an environment naming issue, not a test
result.

## 7. Limitations and next milestone

This is an implementation and isolation result, not a value proof. The
fixture set is small, the live runner is not wired to the Adaptive contract,
and no provider/model provenance exists for a task execution. A safe next
milestone is to provision or expose an already-authorized zero-cost local
route, run the one-to-two-task development smoke test, freeze the candidate
after development/validation, and only then run holdout once.

```text
OPEN_BLOCKERS=NO_SAFE_ZERO_COST_AUTHENTICATED_LIVE_ROUTE;PR60_OWNER_MERGE_GATE
NEXT_RECOMMENDED_MILESTONE=RUN_MATCHED_SMOKE_AND_ABLATION_AFTER_SAFE_LOCAL_AUTH
RELEASE_CREATED=false
PRODUCTION_DEPLOYED=ROLE_FIX_ONLY_REAL_RUNTIME
ADAPTIVE_RELEASE_DEPLOYED=false
PRODUCTION_PROVEN=false
```

## Reality refresh — 2026-09-01

The local adaptive head was pushed normally to PR #61 as `2e04ecae`. The
previous task placeholders were replaced by the versioned executable
`autodev.benchmark-task.v1` contract, frozen synthetic fixtures, and a
canonical-only runner. The task suite is now locally valid, but the live
value trial is not complete: the first baseline smoke reached `BUILDING` and
timed out; the second context smoke reached the canonical path and was
aborted as a disposable timeout. Neither is a value result.

```text
EXECUTABLE_TASK_SUITE=PASS_LOCAL
TASKSET_FROZEN_BEFORE_VALUE_TRIAL=true
DEV_TASK_COUNT=4
VALIDATION_TASK_COUNT=2
HOLDOUT_TASK_COUNT=2
DEV_SET_HASH=6e1d9cb88d5ab46bc99f4c6d0e85c69633e411af48490d2cae90848653c2b962
VALIDATION_SET_HASH=95e039c3c0688fba9fd6b54709ed21904ea034887e022c41166b2157f6c59ca9
HOLDOUT_SET_HASH=302ab5d75e8e32bc805dc69ced4af8886207394e7fae2e145002320cc0f5cef1
RUNNER=PASS_LOCAL;N8N_SOLE_CONTROL_PLANE=true
RUNNER_SMOKE_BASELINE=CANONICAL_RUN_TIMEOUT;run-mb-bf5449adfc207d6b52d4
RUNNER_SMOKE_CONTEXT=CANONICAL_RUN_TIMEOUT;run-mb-7df82a34c3e43aceb2a9
A_E_CANONICAL=NOT_RUN
VALIDATION=NOT_RUN
CANDIDATE_FREEZE=NOT_RUN
HOLDOUT=NOT_RUN
ADAPTIVE_HARNESS_VALUE=NOT_PROVEN
```

## 13. Superseding recovery and metadata evidence — 2026-08-31

The historical `PLAN_BLOCKED / CONTRACT_FAILURE` was reproduced as a model
semantic scope mismatch: a target was absent from `build_scope.allowed_files`.
The contract stayed strict; the planning prompt now states the invariant and
the same worker receives one bounded correction opportunity. The exact
failure, regression fixtures, validator equivalence, and live tamper results
are recorded in [`plan-contract-recovery.md`](plan-contract-recovery.md).

The deployed canonical metadata contract is
`autodev.adaptive-metadata.v1`. The embedded canonical smoke
`run-mthmymeg-1z6039` reached `DONE`, and six adapter jobs carried identical
experiment, factor, policy, config-hash, task-set-hash, and harness-version
metadata. The requested `opencode/big-pickle` smoke
`run-mthmq1hw-4gyrdb` reached baseline and research with the same metadata but
was safely aborted after provider latency; it is not a value result.

```text
PLAN_CONTRACT=PASS
PLAN_VALIDATOR_EQUIVALENCE=PASS
FACTOR_METADATA_CORRELATION=PASS
CANONICAL_SMOKE_RESULT=DONE_EMBEDDED_CONTRACT_CHAIN
OPENCODE_BIG_PICKLE_SMOKE=ABORTED_DISPOSABLE_PROVIDER_LATENCY
A_E_CANONICAL=NOT_RUN
VALIDATION=NOT_RUN
CANDIDATE_FREEZE=NOT_RUN
HOLDOUT=NOT_RUN
ADAPTIVE_HARNESS_VALUE=NOT_PROVEN
```

The available `bench/tasks` files still do not contain executable task inputs;
therefore no A–E, validation, freeze, or holdout numbers are fabricated.
Evidence: [`canonical-metadata-20260831.json`](../../evidence/adaptive-harness/canonical-metadata-20260831.json).

## 8. Reality refresh and live evidence — 2026-08-31

This section supersedes the initial blocked snapshot above. Repository, remote
PR, deployed runtime, and test evidence were rechecked on 2026-08-31.

```text
DATE=2026-08-31
START_BRANCH=feat/adaptive-harness-foundation
START_HEAD=e4bc99a996f227862c1abc14c5be849a060b0066
ORIGIN_MAIN=cbd96c0d0e8c2c3fa47d12ea1c291975e9c0d7b6
WORKTREE_CLEAN_AT_START=true

PR60_STATE=OPEN
PR60_REMOTE_HEAD=9a1d63ccee3a67283060a7040e02c0dad341846f
PR60_BASE=main
PR60_MERGEABLE=true
PR60_CHANGED_FILES=11
PR60_ADAPTIVE_FILES=0
PR60_SCOPE_CLEAN=PASS
PR60_MERGED=false
PR60_PRODUCTION_PROVEN=false
OWNER_ACTION_REQUIRED=MERGE_PR60_EXACT_HEAD_9a1d63ccee3a67283060a7040e02c0dad341846f

DEB4D20_EXISTS=true
DEB4D20_PURPOSE=local continuation idempotency hardening
DEB4D20_REQUIRED=true
DEB4D20_FIXES_REAL_DEFECT=true
DEB4D20_ADDS_REQUIRED_REGRESSION=true
DEB4D20_REDUNDANT=false
DEB4D20_SAFE=true
DEB4D20_PUSHED=true

PR61_STATE=OPEN
ADAPTIVE_BRANCH=feat/adaptive-harness-foundation
ADAPTIVE_EVIDENCE_BASE_HEAD=1666dda2d295fa359d647a6b693fd10b0d78fa49
ADAPTIVE_POST_PR60_INTEGRATION_GATE=PASS_NO_MAIN_ADVANCEMENT
```

`deb4d20` was not accepted from its subject line. Its continuation claim
store and tests were inspected, and a real rebinding gap was found: a new
identity could previously claim an existing `run_id`. The follow-up PR60 head
`9a1d63c` rejects that ownership conflict and adds a regression test. The
isolated PR60 tree passed 22 targeted continuation tests and `153 passed` in
the full repository suite. Required semantics remain:

```text
DELIVERY_SEMANTICS=AT_LEAST_ONCE
CONSUMER_SEMANTICS=IDEMPOTENT
LOGICAL_EFFECT_SEMANTICS=EFFECTIVELY_ONCE
```

The PR60 sentinel found zero Adaptive files. No merge was performed because
there was no owner authorization for the exact new remote head.

## 9. Zero-cost route and matched live smoke

The local LM Studio endpoint was unreachable. The reachable LM Studio endpoint
returned `401` and explicitly required its existing Bearer credential; no
auth bypass or credential change was attempted. Ollama was unreachable and
no existing healthy Ollama service/model was available. The existing adapter
runtime exposed a healthy hard-stop free route:

```text
SAFE_ZERO_COST_ROUTE=PASS
BENCHMARK_PROVIDER=opencode
BENCHMARK_MODEL=big-pickle
ACTUAL_PROVIDER=opencode
ACTUAL_MODEL=big-pickle
ROUTE_AUTHORIZED=true
ROUTE_ZERO_COST=true
ROUTE_MODEL_DISCOVERED=true
ROUTE_HEALTHY=true
ACTUAL_COST=0.0
DEEPSEEK_REQUESTS=0
PAID_REQUESTS=0
AUTOMATIC_PAID_ESCALATION=false
```

The existing adapter token was supplied through a protected stdin pipe. No
token value was printed, stored in evidence, passed in process arguments, or
committed. The live adapter jobs completed with execution proof `PASS`:

```text
BASELINE_TASKS=1
BASELINE_SUCCESS=1
CONTEXT_TASKS=1
CONTEXT_SUCCESS=1
EXPLORER_TASKS=1
EXPLORER_SUCCESS=1
CONTEXT_SUCCESS_DELTA=0
EXPLORER_SUCCESS_DELTA=0
BASELINE_INPUT_TOKENS=UNKNOWN
CONTEXT_INPUT_TOKENS=UNKNOWN
EXPLORER_INPUT_TOKENS=UNKNOWN
BASELINE_OUTPUT_TOKENS=UNKNOWN
CONTEXT_OUTPUT_TOKENS=UNKNOWN
EXPLORER_OUTPUT_TOKENS=UNKNOWN
BASELINE_TOOL_CALLS=UNKNOWN
CONTEXT_TOOL_CALLS=UNKNOWN
EXPLORER_TOOL_CALLS=UNKNOWN
BASELINE_RETRIES=UNKNOWN
CONTEXT_RETRIES=UNKNOWN
EXPLORER_RETRIES=UNKNOWN
```

The provider reported zero usage fields rather than measurable token counts,
so zero was not interpreted as a token result. The direct adapter durations
were approximately 25s baseline, 31s context, and 32s explorer. Prompt
characters were 116, 2267, and 2150 respectively; this is diagnostic only and
not a token measurement. The run used the same provider/model/configuration
and the same development task. Context Compiler and Repository Explorer were
read-only; recorded production-state writes were zero.

No trusted Experience item exists in the repository, so Top-1 and Top-3 were
not fabricated or run. Validation, candidate freeze, and holdout were not
performed because the matched smoke produced no improvement and the current
adapter smoke is not wired as a canonical n8n benchmark execution.

```text
MATCHED_SMOKE=PASS
DEVELOPMENT_ABLATION=PARTIAL_A_BASELINE_B_CONTEXT_C_EXPLORER
EXPERIENCE_TOP1=NOT_RUN
EXPERIENCE_TOP3=NOT_RUN
VALIDATION_BASELINE=NOT_RUN
VALIDATION_BEST_CANDIDATE=NOT_RUN
HOLDOUT_BASELINE=NOT_RUN
HOLDOUT_BEST_CANDIDATE=NOT_RUN
HOLDOUT_DELTA=UNKNOWN
BEST_HARNESS_CONFIGURATION=NONE_PROVEN
BEST_CHANGED_FACTOR=NONE
IMPROVEMENT_ATTRIBUTABLE=NO
GENERALIZATION_PROVEN=NO
SMALL_MODEL_USED=UNKNOWN
SMALL_MODEL_IMPROVEMENT_PROVEN=NO
```

## 10. Control Tower live correlation boundary

The deployed Control Tower was reachable at `http://192.168.1.136:8092`,
version `1.2.0`. The adapter smoke IDs were visible as `LIVE` events through
the Control Tower debugging endpoint, but they were not present in the
Control Tower overview's canonical run projection. Therefore the stronger
equality claim was not made:

```text
BENCHMARK_RUN_ID == CONTROL_TOWER_RUN_ID == N8N_CANONICAL_RUN_ID=NOT_PROVEN
ADAPTER_TO_CONTROL_TOWER_DEBUGGING=PASS
N8N_CANONICAL_OVERVIEW_CORRELATION=NOT_PROVEN
```

The Control Tower is read-only with respect to its own state and routes
commands through the existing n8n gateway. No direct dashboard database write
or benchmark production-state write was introduced.

## 11. Scientific gates and final classification

```text
CONTEXT_COMPILER_VALUE_PROVEN=NO
REPO_EXPLORER_VALUE_PROVEN=NO
EXPERIENCE_VALUE_PROVEN=NO
HOLDOUT_ISOLATION=PASS_LOCAL_TESTS
MEMORY_POISONING_GATE=PASS_LOCAL_TESTS
ARCHITECTURE_GATE=PASS
SECURITY_GATE=PASS
SECRET_SCAN=PASS
MODEL_WEIGHTS_CHANGED=false
AUTO_PROMOTION=false
ADAPTIVE_ROUTING_EXPERIMENT=DEFERRED
N8N_SOLE_CONTROL_PLANE=true
SECOND_SOR=false
BENCHMARK_PRODUCTION_STATE_WRITES=0
EXPERIENCE_STORE_CANONICAL_RUN_SOR=false
CONTROL_TOWER_ADAPTIVE_OBSERVABILITY=DEFERRED
FINAL_CLASSIFICATION=AMBER_ADAPTIVE_HARNESS_DEV_SMOKE_NO_VALUE_PROOF
OPEN_BLOCKERS=PR60_OWNER_MERGE_GATE;NO_VALIDATION_OR_HOLDOUT_AFTER_ZERO_DELTA;CANONICAL_N8N_BENCHMARK_WIRING_NOT_PROVEN
NEXT_RECOMMENDED_MILESTONE=OWNER_MERGE_PR60_EXACT_HEAD_THEN_WIRE_A_DISPOSABLE_CANONICAL_N8N_BENCHMARK_RUN
RELEASE_CREATED=false
PRODUCTION_DEPLOYED=false
PRODUCTION_PROVEN=false
```

The negative result is retained: on one matched task, all three direct
adapter configurations succeeded, with no measurable success improvement and
longer observed wall-clock time for the added context. This is a valid smoke
and route proof, not a value proof or generalization claim.

## 12. Current superseding evidence — canonical n8n path

The following is the current result of the requested reality refresh and
canonical disposable run. Detailed correlation evidence is recorded in
[`canonical-n8n-benchmark-proof.md`](canonical-n8n-benchmark-proof.md).

```text
DATE=2026-08-31
CONTROL_TOWER_URL=http://192.168.1.136:8092
CONTROL_TOWER_VERSION=1.2.0
N8N_URL=http://192.168.1.52:5678
N8N_VERSION=2.26.8
N8N_REACHABLE=PASS
ADAPTER_URL=http://192.168.1.136:8081
ADAPTER_VERSION=2.0.0
ADAPTER_REACHABLE=PASS
ZERO_COST_PROVIDER=opencode
ZERO_COST_MODEL=big-pickle
ZERO_COST_ROUTE_HEALTH=PASS
PAID_REQUESTS=0
DEEPSEEK_REQUESTS=0

CANONICAL_BENCHMARK_RUN_ID=run-mthenxhx-qvim85
N8N_CANONICAL_RUN_ID=run-mthenxhx-qvim85
AUTODEV_RUN_ID=run-mthenxhx-qvim85
ADAPTER_RUN_ID=run-mthenxhx-qvim85
CONTROL_TOWER_RUN_ID=run-mthenxhx-qvim85
CANONICAL_RUN_TERMINAL_STATE=PLAN_BLOCKED
CANONICAL_RUN_REASON=CONTRACT_FAILURE
CANONICAL_N8N_BENCHMARK_CORRELATION=PARTIAL

SELECTED_PROVIDER=opencode
SELECTED_MODEL=big-pickle
ACTUAL_PROVIDER=opencode
ACTUAL_MODEL=big-pickle
ACTUAL_COST=0
RESEARCH_EXECUTION_PROOF=PASS
PLAN_EXECUTION_PROOF=CONTRACT_FAILURE

MATCHED_SMOKE_A_B_C=PASS_DIRECT_ADAPTER_ONLY
VALUE_GAIN=NOT_PROVEN
EXPERIENCE_TOP1=NOT_RUN
EXPERIENCE_TOP3=NOT_RUN
VALIDATION=NOT_RUN
HOLDOUT=NOT_RUN
CANDIDATE_FREEZE=NOT_RUN
GENERALIZATION_PROVEN=NO
```

The run IDs are equal across n8n intake, the canonical `autodev_runs` row,
adapter jobs, and the Control Tower projection. The stronger full-correlation
gate remains `PARTIAL`, because the current n8n intake does not propagate a
non-empty `correlation_id`, and the run terminated before plan/build attempts
could provide complete end-to-end provenance. The attempted run is retained
as negative evidence; it is not counted as a successful benchmark task.

The current adaptive implementation exposes local contracts for context,
exploration, and experience, but the canonical n8n workflow does not yet
carry factor policies or experiment IDs through the adapter. Therefore A–E,
validation, candidate freeze, and holdout are intentionally `NOT_RUN` rather
than inferred from the direct adapter smoke. This is the blocking milestone
for a future value-proof run.

```text
ROLE_MAPPING_ROOT_CAUSE=systemd operator_token loaded from viewer-token;
  legacy role_for_token also treated a token collision as OPERATOR
ROLE_FIX_IMPLEMENTED=YES_IN_PR62_AND_DEPLOYED
ROLE_GATE=PASS
AUTH_GATE=PASS
CSRF_GATE=PASS
ARBITRARY_COMMAND_GATE=PASS
ARBITRARY_TARGET_GATE=PASS
CONTROL_TOWER_OPERATIONAL_ACCEPTANCE=AMBER
ARCHITECTURE_GATE=PASS
SECURITY_GATE=PASS
MEMORY_POISONING_GATE=PASS_LOCAL_TESTS
HOLDOUT_ISOLATION=PASS_LOCAL_TESTS
N8N_SOLE_CONTROL_PLANE=true
SECOND_SOR=false
BENCHMARK_PRODUCTION_STATE_WRITES=0
RELEASE_CREATED=false
PRODUCTION_DEPLOYED=ROLE_FIX_ONLY_REAL_RUNTIME
ADAPTIVE_RELEASE_DEPLOYED=false
PRODUCTION_PROVEN=false
```
