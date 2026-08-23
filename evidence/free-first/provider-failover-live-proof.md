# Provider failover proof

Offline implementation coverage is green:

- Groq -> OpenRouter failover: PASS.
- OpenRouter -> Groq failover: PASS.
- Semantic attempt identity unchanged in both directions: PASS.
- Provider failover is separate from semantic retry: PASS.

Live bidirectional provider failover was not executed. The canonical remote adapter is the old deployed Baseline adapter without the committed provider runtime, and the runbook marks adapter redeploy as a separate approval step. Groq also remained fail-closed because its account class was not proven; OpenRouter live completion attempts were rate-limited/model-unavailable.

`FAILOVER_GROQ_TO_OPENROUTER=NOT_RUN_DEPLOYMENT_AND_FREE_PROOF_BLOCKED`

`FAILOVER_OPENROUTER_TO_GROQ=NOT_RUN_DEPLOYMENT_AND_FREE_PROOF_BLOCKED`

`MODEL_FAILOVER=BOUNDED_ATTEMPT_404_NOT_PROVEN`

`SEMANTIC_RETRY_SEPARATION=PASS_OFFLINE_NOT_LIVE`
