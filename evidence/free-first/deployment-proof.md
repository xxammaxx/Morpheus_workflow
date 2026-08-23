# Deployment Proof

Deployment state: `SHADOW_READY` / `CANARY_READY`, not production cutover.

- Repository code and n8n workflow exports are updated.
- Live n8n and adapter health are GREEN.
- Provider runtime is disabled by default for production safety.
- No systemd unit was changed and no production workflow was activated.
- Catalog refresh is a maintenance command: `python3 -m providers.refresh`.
- Production activation requires explicit shadow/canary approval and provider
  credentials/privacy decisions.
