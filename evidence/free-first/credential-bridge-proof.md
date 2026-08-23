# Credential bridge proof

`CREDENTIAL_BRIDGE=PASS` for the explicitly authorized Groq/OpenRouter bridge.

- Source store: `~/.local/share/opencode/auth.json`, mode `0600`.
- Source status: `GROQ=PRESENT`, `OPENROUTER=PRESENT`.
- Parser observed provider records with a `key` field; no values, prefixes,
  lengths, hashes, or account identifiers were recorded.
- Transfer channel: SSH stdin only, to `root@pve`.
- Remote store: `/var/lib/autodev-harness-v2/provider.env`, `root:root`, mode
  `0600`; atomic temporary-file write and rename.
- Drop-in: `/etc/systemd/system/autodev-harness-v2.service.d/20-provider-credentials.conf`.
- Drop-in contains only the `EnvironmentFile` directive and no secret values.
- `daemon-reload`, service restart, active-state check, and adapter health all
  passed.
- Running service environment reported `GROQ_API_KEY=true` and
  `OPENROUTER_API_KEY=true` status-only.

`CREDENTIAL_PERSISTENCE_CREATED=YES_ROOT_ONLY_RUNTIME_SECRET_STORE`
`CREDENTIAL_PERSISTENCE_PUBLIC=false`
`CREDENTIAL_PERSISTENCE_REPO=false`
`SECRET_VALUES_EXPOSED=false`

The bridge implementation and fixture tests are public at
`scripts/sync_opencode_provider_credentials.py` and
`scripts/test_sync_opencode_provider_credentials.py`.
