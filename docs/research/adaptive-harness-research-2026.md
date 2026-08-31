# Adaptive Harness Research Refresh — 2026-08-31

This is a design input, not Morpheus runtime evidence. The repository's own
measurements remain authoritative. Preprints and industry reports are not
treated as established facts.

| Source | Date / status | Relevant result | Morpheus decision |
|---|---|---|---|
| [Agentic Harness Engineering](https://arxiv.org/abs/2604.25850) | 2026, PREPRINT | Observability of components, experiences and decisions; reports cross-family transfer on its benchmarks. | EXPERIMENT: provenance-bound candidate deltas and outcome attribution. |
| [MemoHarness](https://arxiv.org/abs/2607.14159) | 2026, PREPRINT | Frames harness as context/tools/orchestration/memory/output layer; notes attribution and robustness limits. | ADOPT: treat configuration, not model name, as benchmark unit. |
| [Contextual Experience Replay](https://arxiv.org/abs/2506.06698) | 2025, PREPRINT | Training-free experience synthesis can improve a web-agent baseline in the reported setting. | EXPERIMENT: bounded retrieval ablations; no automatic rule promotion. |
| [SWE-agent](https://mlanthology.org/neurips/2024/yang2024neurips-sweagent/) | 2024, PEER_REVIEWED | Agent-computer interface and tool interaction materially affect coding-agent results. | ADOPT: measure tool and repository-navigation errors separately. |
| [Control Under Compression](https://www.roboticscenter.ai/research/papers/control-under-compression-reliability-frontiers-for-tool-using-agents-2608) | 2026, BENCHMARK / PREPRINT | Compression is evaluated with environment verification across budgets and task families. | EXPERIMENT: bounded context ablations; retain control core verbatim. |
| [Tool and Agent Selection survey](https://www.preprints.org/manuscript/202512.1050) | 2025, PREPRINT | Hierarchical/progressive tool exposure can reduce context overhead. | EXPERIMENT: task-restricted tool profiles; security gate required. |
| [Agent Harness Engineering survey](https://openreview.net/pdf/f358711a95aaaf61fdeffd4ef3fc60fba9b8da57.pdf) | 2026, SURVEY / PREPRINT | Summarizes rapidly evolving harness and evaluation practices. | DEFER: no paper claim is promoted to Morpheus evidence. |

## Research conclusions

The transferable design inference is that harness changes need component-level
observability, matched baselines, task splits and independent verification.
Reported token or success improvements are not copied into Morpheus. The first
implementation therefore uses deterministic scoring, explicit `UNKNOWN`, and a
holdout set inaccessible to the optimizer. Fine-tuning/LoRA is DEFERRED until a
stable error class survives harness experiments.

## Exclusion / uncertainty register

The named MAGE, HarnessLens, HarnessOpt-Bench, Harness the Memory, FastContext,
ERL, CompressAgent, HAL and hierarchical-MCP items were not all identifiable
as stable primary publications under those exact names in this refresh. They
are not used as design authority; related primary links above are recorded as
current leads. This is an explicit uncertainty, not a claim that the work does
not exist.
