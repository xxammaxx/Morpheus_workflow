# Live provider authentication proof

Run date: 2026-08-23. Workspace: `/tmp/morpheus-free-first-closure-20260823`.

## Credential boundaries

- `OPENCODE_AUTH_STORE_ENTRY_GROQ=PRESENT`.
- `OPENCODE_AUTH_STORE_ENTRY_OPENROUTER=PRESENT`.
- OpenCode auth store mode was `600`; values were read only into ephemeral process memory.
- `GROQ_API_KEY` and `OPENROUTER_API_KEY` were never printed, persisted, committed, or written to evidence.
- `X-Harness-Token` was obtained ephemerally from the documented remote token file; authenticated `GET /v1/jobs/nonexistent` returned `404`, proving `HARNESS_AUTH=PASS` without exposing the token.

## Provider catalog probes

- `GROQ_AUTH=PASS`; `GROQ_CATALOG=PASS`; current catalog contained 13 models.
- `OPENROUTER_AUTH=PASS`; `OPENROUTER_CATALOG=PASS`; current catalog contained 422 models, including 22 zero-priced/free candidates.
- No DeepSeek or paid request was made.

The deployed remote service is healthy but is the pre-provider Baseline adapter: its deployed tree has no `ProviderRuntime` or `providers/` implementation. The repository runbook requires a separate adapter-deploy approval, so no redeploy was performed.
