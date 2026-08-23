# Regression results

- Bootstrap regression: PASS.
- Provider runtime: PASS.
- Provider adapter integration: PASS.
- Contracts: PASS, 34/34.
- Validator equivalence: PASS, 34/34.
- Compileall and `git diff --check`: PASS.
- Deployed runtime fingerprint, adapter health, harness auth, and credential
  persistence: PASS.
- OpenRouter catalog route: PASS; bounded completion: HTTP 429, no retry.
- Groq catalog: PASS; account class UNKNOWN, zero promoted routes.
- `test_provider_transport.py` and `test_adapter_auth.py`: repository files
  not present in this worktree; no result is claimed for them.
