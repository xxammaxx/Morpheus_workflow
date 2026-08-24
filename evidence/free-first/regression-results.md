# Targeted regression results — 2026-08-24

- Contracts: PASS, 34/34.
- Validator equivalence: PASS, 34/34.
- Bootstrap, provider runtime, adapter integration, adapter auth, and
  provider transport: PASS.
- Credential bridge regression: PASS.
- `compileall`: PASS.
- `git diff --check`: PASS.
- Public secret scan: PASS; only status-only credential-presence references
  and test fixtures were found, no secret values.
- Repository n8n inventory: 12/12 JSON workflows parse.
- Deployed Groq one-shot used the existing adapter/runtime and returned HTTP
  200 with 13 models; no runtime code changed and no redeployment was needed.
- Current OpenRouter key read-only check returned HTTP 200 and `is_free_tier`;
  no model request was sent because free-request reset/remaining was absent.
- No runtime code changed; no deployment or unrelated holdouts were run.

# Quota-isolation continuation — 2026-08-24

- Focused provider/contracts/adapter/auth tests: `7 passed`.
- `compileall`: PASS.
- n8n repository workflow inventory: `12 found / 12 valid JSON`.
- `git diff --check`: PASS.
- Public evidence scan: PASS after treating credential-name references and
  status-only evidence as non-secret; no credential values, headers, cookies,
  or tokens were added.
- Runtime code was unchanged; redeployment was not required.

# Final V1 closure run — 2026-08-24

- Maintenance-only controlled Ollama failure seam: PASS; default OFF,
  provider-scoped, retryable, and covered by provider runtime tests.
- Reverse live failover: PASS; Ollama first, controlled retryable failure,
  same semantic attempt, one OpenRouter `openrouter/free` HTTP 200, resolved
  model recorded, no semantic retry.
- Forward live failover: PASS from prior closure evidence; bidirectional live
  failover: PASS.
- Production Ollama canary: PASS; selected and actual provider/model were
  `ollama` / `qwen3:1.7b`; no external request used by the canary.
- Production state: free-first enabled by the existing runtime default,
  promoted pool OpenRouter + Ollama, automatic paid escalation false,
  DeepSeek ineligible; controlled exhaustion returned
  `NO_ELIGIBLE_FREE_PROVIDER`.
- Final targeted suite: contracts 34/34, validator equivalence 34/34,
  bootstrap/runtime/lease/adapter/auth PASS, compileall PASS, n8n JSON 12/12,
  diff-check PASS, public secret scan PASS.
- Security remains blocked only by server-side revocation proof for the
  previously exposed GitHub token; no token value was inspected or recorded.
