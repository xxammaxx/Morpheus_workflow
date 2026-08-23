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
- No runtime code changed; no deployment or unrelated holdouts were run.
