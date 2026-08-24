# Morpheus V1 production canary — 2026-08-24

The canary used the deployed n8n-adjacent adapter path and the local Ollama
route. It consumed no external provider request.

```text
PRODUCTION_CANARY_RUN_ID=run-final-production-canary-20260824
PRODUCTION_CANARY=PASS
N8N_TO_ADAPTER=PASS
SELECTED_PROVIDER=ollama
SELECTED_MODEL=qwen3:1.7b
ACTUAL_PROVIDER=ollama
ACTUAL_MODEL=qwen3:1.7b
EXECUTION_PROOF=PASS
TERMINAL_STATUS=completed
EXTERNAL_OPENROUTER_REQUESTS=0
```

After the canary, adapter health remained HTTP 200, with zero running jobs;
temporary maintenance variables were absent and the provider lease was in the
released state.
