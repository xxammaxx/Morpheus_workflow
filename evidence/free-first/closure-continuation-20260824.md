# Morpheus V1 closure continuation — 2026-08-24

This evidence records the closure work performed from the canonical
`a8dc75a5b43088ac1c8f21bc6eba54e15f485cd9` baseline. No credential values,
tokens, cookies, request headers, or provider response secrets are recorded.

## Runtime and n8n

```
REMOTE_MAIN_HEAD=evidence recorded at final commit
DEPLOYED_ADAPTER_VERSION=2.0.0
DEPLOYED_ADAPTER_HEALTH=PASS
N8N_API_AUTH=PASS
N8N_API_KEY_STORAGE=root-only /var/lib/n8n-spec-kit/secrets/ghiw-n8n-api-key, mode 0600
N8N_REPO_WORKFLOWS=12/12 valid
N8N_DEPLOYED_CANONICAL_WORKFLOWS=12/12 active and name-correlated
N8N_EXECUTION_LIST=PASS
N8N_ACTIVE_EXECUTIONS=0 at probe time
```

The existing n8n read key was used transiently for the official read API. Its
value is not present in this repository or evidence.

## Provider lease and durability

The provider-scoped maintenance lease is persisted as a root-only atomic state
file, has a maximum TTL of 120 seconds, permits one authorized probe, blocks
ordinary traffic for the leased provider, rejects wrong/exhausted leases, and
rejects DeepSeek and paid providers. The complete T1–T10 acceptance test passes.

The closure run found and fixed two persistence defects: successful live proof
was not saved, and a later catalog refresh discarded promotion fields. Both are
now covered by the existing catalog save/merge path and reload tests.

## Live zero-cost routes

```
OPENROUTER_SELECTION_TO_EXECUTION=PASS
OPENROUTER_ZERO_COST=PASS_CATALOG_HARD_ZERO
OPENROUTER_PROMOTED_AFTER_RELOAD=PASS
OPENROUTER_MODEL_REQUESTS_THIS_RUN=1
OLLAMA_ENDPOINT=http://192.168.1.50:11434/v1 (explicit trusted private endpoint)
OLLAMA_SELECTION_TO_EXECUTION=PASS
OLLAMA_ZERO_COST=PASS_CATALOG_HARD_ZERO
OLLAMA_PROMOTED_AFTER_RELOAD=PASS
FREE_POOL_SIZE=2
FREE_POOL_PROVIDERS=openrouter,ollama
DEEPSEEK_REQUESTS=0
PAID_REQUESTS=0
```

Embedding-only Ollama models are excluded from chat capabilities. Unknown or
public endpoints are not classified as local zero-cost; the production Ollama
endpoint is explicitly allowlisted in the root-only provider environment.

## E2E and recovery

```
ADAPTER_LOCAL_CANARY=PASS
GOLDEN_JOURNEY_RUN_ID=run-mt6unuge-agsdu4
GOLDEN_JOURNEY=DONE / ALL_HARD_GATES_GREEN
FAILURE_RECOVERY_RUN_ID=run-mt6uony8-jjp9hf
FAILURE_RECOVERY=VERIFY_FAILED_WITH_DELTA -> FIX_REQUIRED -> DONE
RESTART_RECOVERY=PASS
```

The n8n golden journey used the existing deterministic embedded backend for
control-plane gates. The separate adapter canary exercised real Ollama
selection-to-execution and correlated selected/actual provider and model.

## Regression and remaining gates

```
TARGETED_V1_REGRESSION=PASS
N8N_JSON=12/12 PASS
PUBLIC_SECRET_SCAN=PASS
SECURITY_REVIEW=PASS for implemented changes
COST_REVIEW=PASS for implemented changes
```

The original Groq account-tier evidence remains unavailable and no Groq
completion was attempted. The authorized OpenRouter+Ollama equivalence path is
therefore used for provider-pool redundancy. A second external OpenRouter
request was deliberately not made: the one-shot budget was exhausted by the
isolated proof. Consequently, live bidirectional failover is only proven in
the OpenRouter→Ollama direction in this continuation; the reverse external
direction remains unclaimed and Issue #1 is not closed on a false-green basis.

