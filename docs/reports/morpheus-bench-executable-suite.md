# MorpheusBench executable suite

Date: 2026-09-01

## Contract and task design

All task files use the existing `autodev.benchmark-task.v1` contract. Each
definition contains an instruction, structured input, fixture setup,
execution mode, allow/deny tool policy, acceptance criteria, verifier,
bounded timeout/attempts, mutation policy, cleanup, expected failures, and
both fixture and task SHA-256 hashes. The suite uses four development tasks
(structured output, repository navigation, read-only analysis, tool
selection), two validation tasks (small fixture-only code change and failure
recovery), and two unseen holdout tasks.

The fixtures are JSON file maps. The local runner materializes them in a
temporary directory for setup/cleanup checks; the adapter's corresponding
bounded fixture path is a disposable workspace. No task can name an absolute
path, parent traversal, symlink escape, shell command, paid provider, or
DeepSeek route.

The loader also fails closed on untrusted instruction/input content: policy
override attempts, HTML/JavaScript, Mermaid payloads, paid or DeepSeek route
requests, shell construction, network access, and secret-file access are
covered by negative tests. The task security gate is `20 passed` in the
benchmark test module.

## Frozen splits

```text
TASKSET_FROZEN_BEFORE_VALUE_TRIAL=true
development=4;6e1d9cb88d5ab46bc99f4c6d0e85c69633e411af48490d2cae90848653c2b962
validation=2;95e039c3c0688fba9fd6b54709ed21904ea034887e022c41166b2157f6c59ca9
holdout=2;302ab5d75e8e32bc805dc69ced4af8886207394e7fae2e145002320cc0f5cef1
```

Holdout loading requires an explicit holdout phase. Optimizer and ordinary
development/validation calls fail closed. Experience records are accepted
only from verified development results and same-task records are excluded.

## Runner and evidence

`bench/runner/runner.py` performs task/schema/hash validation, runtime and
zero-cost preflight, canonical n8n intake, terminal polling, adapter evidence
collection, deterministic verification, idempotent result persistence, and
temporary-fixture cleanup. The runner never calls the adapter as a shortcut.
The only permitted live route is `opencode/big-pickle`; the current catalog
reported `HEALTHY`, `FREE_HARD_STOP`, and `free_eligible=true`, with automatic
paid escalation and DeepSeek explicitly disabled.

The baseline smoke `run-mb-bf5449adfc207d6b52d4` and context smoke
`run-mb-7df82a34c3e43aceb2a9` reached the real canonical path but remained
non-terminal and were recorded as timeouts before safe cleanup. A–E,
validation, candidate freeze, and one-time holdout are therefore not claimed.

## Limitations

No success, token, latency, or adaptive-value metric is inferred from the
non-terminal smokes. The current result is an operationally valid local suite
and a truthful live-pipeline blocker, not a harness value proof. No release,
promotion, model-weight change, LoRA, fine-tuning, or production mutation was
made.

## Runtime recovery attempt — 2026-09-01

The deployed parent-terminality fix was exercised with exactly one new
development task (`d-001`, `BASELINE`). The run reached terminal `FAILED`
instead of hanging in `BUILDING`; the adapter rejected Build before creating a
build job because the fixed `opencode/big-pickle` route has no live
`BUILD_CAPABLE`/tool-probe evidence. This is a real failure, not a valid smoke.

```text
RUN_ID=run-mb-4f2c8594725a8849db5d
TASK_ID=d-001
FACTOR=BASELINE
TASK_HASH=1d4adbcb595596a40e31ef84f938c12d3f396fe5d11f06e8f65a3fea57ee46f6
FIXTURE_HASH=3c31b7cda4be588d4aa11a1c052a3b089e751f847d8c333c029006e6814f62c3
TERMINAL_STATE=FAILED
VERIFICATION=FAIL
RUNNER_SMOKE_BASELINE=NOT_VALID_TERMINAL_CAPABILITY_GATE
RUNNER_SMOKE_CONTEXT=NOT_RUN
A_E_EXECUTION_READY=false
HOLDOUT_EXECUTION_COUNT=0
PAID_REQUESTS=0
DEEPSEEK_REQUESTS=0
```

Evidence: [`build-callback-recovery-2026-09-01.json`](../../evidence/morpheus-bench/build-callback-recovery-2026-09-01.json).

## Capability-refresh recovery smoke — 2026-09-01

After the capability refresh fix, the exactly-one-task BASELINE smoke reached
the real Build boundary with `opencode/big-pickle`. The Build job was created,
the provider was reached, and the job terminalized as a bounded task contract
failure (`BUILD_NO_CHANGES`) at zero cost. The verifier did not execute on this
Build-failure path, so the pipeline-readiness gate is intentionally not green
and CONTEXT_COMPILER was not started.

```text
RUN_ID=run-mb-722b6de824551f771150
TASK_ID=d-001
FACTOR=BASELINE
BUILD_DISPATCH_ACCEPTED=true
BUILD_JOB_CREATED=true
PROVIDER_REACHED=true
TERMINAL_STATE=FAILED
VERIFIER_EXECUTED=false
TASK_SUCCESS=false
BASELINE_PIPELINE_READY=NO
CONTEXT_SMOKE=NOT_RUN_BASELINE_GATE
```
