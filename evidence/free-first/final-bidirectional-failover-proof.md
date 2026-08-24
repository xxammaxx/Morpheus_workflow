# Morpheus V1 bidirectional failover proof — 2026-08-24

This is sanitized evidence. No prompt, credential, token, request header, or
provider secret is stored here.

## Reverse direction (this closure run)

```text
ATTEMPT_ID=attempt-final-reverse-20260824
FIRST_SELECTED_PROVIDER=ollama
FIRST_PROVIDER_ATTEMPT=ollama
FIRST_PROVIDER_FAILURE=CONTROLLED_RETRYABLE
SECOND_SELECTED_PROVIDER=openrouter
OPENROUTER_ROUTE=openrouter/free
OPENROUTER_HTTP_SUCCESS=true
OPENROUTER_ACTUAL_PROVIDER=true
OPENROUTER_RESOLVED_MODEL=cohere/north-mini-code:free
OPENROUTER_ZERO_COST=PASS_CATALOG_HARD_ZERO
SEMANTIC_RETRY_CREATED=false
OPENROUTER_NEW_REQUESTS_THIS_RUN=1
FAILOVER_OLLAMA_TO_OPENROUTER=PASS_LIVE
```

The request entered the deployed adapter with Ollama preferred. The
maintenance-only seam produced a provider-scoped retryable failure for Ollama;
the same semantic attempt then executed once through the leased OpenRouter
`openrouter/free` route and completed with `execution_proof=PASS`. The provider
lease and temporary maintenance environment were released and cleared after
the attempt.

The forward direction remains the previously committed live proof:

```text
FAILOVER_OPENROUTER_TO_OLLAMA=PASS_LIVE
BIDIRECTIONAL_PROVIDER_FAILOVER=PASS_LIVE
FREE_POOL_SIZE=2
FREE_POOL_PROVIDERS=openrouter,ollama
```

Provider request IDs and prompts are intentionally not persisted in public
evidence. The deployed runtime's sanitized execution result is the source for
the correlation above.
