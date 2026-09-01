# Adaptive Harness Architecture

Morpheus adds an offline adaptive layer around the existing n8n control plane.
n8n remains the sole control plane and `autodev_runs` remains canonical run
state. Benchmark, context and experience stores are evidence/read models only.

```mermaid
flowchart LR
  R[(Verified run evidence)] --> B[MorpheusBench]
  B --> D[Experience distiller]
  D --> E[(Experience bank)]
  E --> C[Context compiler]
  R --> C
  C --> W[Existing worker]
  W --> V[Existing deterministic verifier]
  V --> B
  B --> L[Candidate evaluation lab]
  L --> G{security + regression + holdout}
  G -->|recommend only| P[Owner / PR promotion gate]
  N[n8n control plane] -. authority .-> W
```

The adaptive layer can propose and test one bounded component delta. It cannot
change authorization, holdout membership, paid-routing policy, DeepSeek policy,
verifier authority, or production state.
