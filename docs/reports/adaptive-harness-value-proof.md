# Morpheus Adaptive Harness — Value Proof

Date: 2026-08-31

## Final classification

`AMBER_ADAPTIVE_HARNESS_LIVE_EVALUATION_BLOCKED`

The adaptive foundation is isolated and locally tested, but no live
baseline/candidate evidence is claimed. The first smoke run was not started:
the only discovered local model endpoint (`LM Studio`,
`192.168.1.50:1234`) requires an `LM_API_TOKEN` that is not available in the
approved environment, and Ollama is not listening. No paid or DeepSeek request
was made.

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
PRODUCTION_DEPLOYED=false
PRODUCTION_PROVEN=false
```
