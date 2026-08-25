# Dynamic OpenCode free-model routing

Canonical OpenCode jobs use the logical route `morpheus-dynamic-free`. The
physical provider/model is selected at run start from OpenCode's refreshed
catalog, the current API-key auth inventory, authoritative zero-cost metadata,
and task capability requirements.

The router fails closed for unknown pricing, unauthenticated providers,
DeepSeek, paid escalation, and missing hard capabilities. Vision work requires
live image-input metadata; build work requires a passing tool probe; strict
structured work requires a proven structured-output score.

Transport failures retry the same model at most once. A second transient
failure excludes that provider/model for the current `RUN_ID`; fatal credential
or model failures exclude immediately. Verifier-proven semantic failures are
tracked separately and exclude the model/task pair after the configured
threshold. Routing events are appended to the existing adapter `runs.jsonl`
ledger, so exclusions survive an adapter restart without creating another
source of truth.

Credential maintenance:

```text
python3 scripts/sync_opencode_credentials.py --target-user <discovered-user>
```

The script reads the source OpenCode auth store, copies API-key records only,
preserves OAuth/session records, writes CT8001's auth store atomically with a
0600 mode and root-only backup, and reports metadata only. Credentials travel
through authenticated local container control on stdin, never argv, logs, or
evidence.
