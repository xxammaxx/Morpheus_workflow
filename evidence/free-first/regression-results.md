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
- OpenRouter `/api/v1/key`: HTTP 200; free-tier true; daily/weekly/monthly
  usage 0; no reset fields exposed.
- Groq authenticated models read-only check: HTTP 403; account class UNKNOWN,
  zero promoted routes; no completion.
- `test_provider_transport.py` and `test_adapter_auth.py`: repository files
  not present in this worktree; no result is claimed for them.
