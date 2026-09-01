# Plan contract recovery — 2026-08-31

## Root cause

The historical canonical run `run-mthenxhx-qvim85` reached the real adapter and
provider, then failed closed at the plan semantic gate. The raw model text was
not persisted; the redacted adapter ledger preserved the contract error. The
parsed plan had concrete target files that were not all present in
`build_scope.allowed_files`.

```text
PLAN_FAILURE_RUN_ID=run-mthenxhx-qvim85
PLAN_RAW_OUTPUT_AVAILABLE=NO_REDACTED_RAW_PERSISTENCE_BY_POLICY
PLAN_RAW_OUTPUT_SECRET_SAFE=NOT_PERSISTED
PLAN_PARSED_OUTPUT=OBJECT_RECONSTRUCTED_BEFORE_GATE
PLAN_NORMALIZED_OUTPUT=CANONICAL_PLAN_OBJECT
PLAN_CONTRACT_VERSION=autodev.plan.v1
PLAN_VALIDATOR_IMPLEMENTATION=JSON_SCHEMA_REGISTRY + EMBEDDED_JS_VALIDATOR
PLAN_VALIDATION_ERROR=targets outside allowed_files
PLAN_FAILURE_JSON_PATH=$.build_scope
PLAN_FAILURE_FIELD=allowed_files
PLAN_FAILURE_EXPECTED=every targets.files path occurs verbatim in allowed_files
PLAN_FAILURE_ACTUAL=runtime/providers/router.py was outside allowed_files
PLAN_FAILURE_CLASS=MODEL_SEMANTIC_FAILURE;PROMPT_CONTRACT_MISMATCH
```

This was not a parser, serializer, schema-version, or missing-field failure.
The contract was semantically correct and remains strict. The repair makes the
invariant explicit in the planning prompt, maps model fields deterministically,
and gives the same worker one bounded correction opportunity. Missing semantic
content is never invented; unresolved output remains `CONTRACT_FAILURE`.

## Contract and security gates

The adaptive provenance contract is the single JSON Schema source of truth:
`autodev.adaptive-metadata.v1`. Python registry validation and the generated
n8n JavaScript validator consume that schema. The factor enum is fixed to
`BASELINE`, `CONTEXT_COMPILER`, `CONTEXT_PLUS_EXPLORER`, `EXPERIENCE_TOP1`, and
`EXPERIENCE_TOP3`.

Regression coverage includes a valid fixture, the exact historical scope
failure, missing required data, wrong types, unknown properties, invalid enum,
empty critical fields, prompt/rebind mismatch, and config-hash mutation. Live
adapter tamper requests returned `ADAPTIVE_METADATA_REBIND` and
`ADAPTIVE_METADATA_INVALID` without creating jobs.

## Runtime proof

The adapter, schema, n8n workflows, additive `autodev_runs` columns, and
read-only Control Tower projection were deployed on 2026-08-31. The canonical
embedded contract smoke `run-mthmymeg-1z6039` reached `DONE`; six adapter jobs
carried identical experiment, task, split, factor, policy, config-hash,
task-set-hash, and harness-version metadata. The requested opencode/big-pickle
smoke `run-mthmq1hw-4gyrdb` propagated metadata through baseline and research,
but was aborted as a disposable provider-latency cleanup after research did
not complete. It is not counted as a benchmark success.

Evidence: [`canonical-metadata-20260831.json`](../../evidence/adaptive-harness/canonical-metadata-20260831.json).

```text
PLAN_FAILURE_REPRODUCED=PASS
PLAN_FAILURE_ROOT_CAUSE=KNOWN
PLAN_FIX_IMPLEMENTED=YES
PLAN_REGRESSION_TEST=PASS
PLAN_VALIDATOR_EQUIVALENCE=PASS
PLAN_SECURITY_GATE=PASS
CANONICAL_RUN_ID_CORRELATION=PASS
EXPERIMENT_ID_PROPAGATION=PASS
FACTOR_PROPAGATION=PASS
CONFIG_HASH_PROPAGATION=PASS
CANONICAL_VALUE_TRIAL_READY=NO
```

## Remaining blocker

The repository's MorpheusBench task files currently contain task IDs, classes,
and content hashes but no executable repository/task inputs. No real A–E,
validation, candidate freeze, or one-time holdout result can therefore be
claimed without inventing fixtures or a runner. The correct next milestone is
to provide the already-approved real task inputs/runner, then execute all
factors through the deployed n8n start webhook with matched compute.
