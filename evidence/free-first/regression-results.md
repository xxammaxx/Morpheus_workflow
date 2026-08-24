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
