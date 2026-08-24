# Morpheus V1 final security closure — 2026-08-24

```text
PUBLIC_SECRET_SCAN=PASS
N8N_API_SECRET_STORAGE=PASS root-only mode 0600 credential store
PROVIDER_SECRET_STORAGE=PASS root-only /var/lib/autodev-harness-v2/provider.env mode 0600
HARNESS_TOKEN_STORAGE=PASS root-only mode 0600
PROVIDER_PROBE_LEASE=PASS provider-scoped atomic lease, max TTL 120s
LEASE_CLEANUP=PASS released after final probe
MAINTENANCE_SEAM_DEFAULT=OFF
SECRET_VALUES_EXPOSED=false
```

The current GitHub Git operation path is the `gh` keyring/OAuth helper. A
`GITHUB_PERSONAL_ACCESS_TOKEN` environment variable name is present locally,
but its value and identity were not inspected or recorded. The previously
exposed GitHub token is not server-side revocation-proven in this run.

```text
GITHUB_TOKEN_ROTATION=HUMAN_ACTION_REQUIRED
CURRENT_GIT_AUTH_SOURCE=gh keyring/OAuth helper (status-only)
SECURITY_REVIEW_FINAL=BLOCKED_ONLY_BY_OLD_TOKEN_REVOCATION_PROOF
```

Required human action: revoke the previously exposed GitHub personal access
token in GitHub Settings → Developer settings → Personal access tokens. No
other provider, n8n, architecture, billing, or credential action is required.
