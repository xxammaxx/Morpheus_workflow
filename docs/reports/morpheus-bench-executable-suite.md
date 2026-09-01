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
