# Targeted regression results

All requested local targeted checks passed:

- Contract validation: 34 passed, 0 failed.
- Validator equivalence: 34 passed, 0 failed.
- Provider runtime: all listed cases passed, including both failover directions, unchanged semantic attempt, dynamic discovery, DeepSeek/paid exclusion, endpoint ownership, and execution-proof contract.
- Provider adapter integration: selection-to-execution and actual provider/model correlation passed.
- Provider transport: User-Agent and auth/header-redaction tests passed.
- Adapter auth: callback allowlist and `X-Harness-Token` tests passed.
- n8n workflow JSON parse: PASS.
- `python3 -m compileall -q runtime adapter workflow`: PASS.
- `git diff --check`: PASS.
- Dynamic refresh with ephemeral credentials: 422 OpenRouter models and 13 Groq models discovered; no credential values emitted.
- Controlled free-pool exhaustion: `NO_ELIGIBLE_FREE_PROVIDER`, no paid/DeepSeek invocation.

`FULL_REGRESSION=NOT_RUN_SEPARATE_HOLDOUT_SCOPE`.
