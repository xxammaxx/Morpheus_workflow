# Committed provider-runtime deployment proof

Run date: 2026-08-23.

## Source and rollback

- Repository: `xxammaxx/Morpheus_workflow` (public).
- Deployment source: fresh clean clone of GitHub `main`.
- `DEPLOY_HEAD=07fd2eebb864f5c7a582f715ec4abcc02a342a78`.
- Original dirty worktree was not used or modified.
- Pre-deploy rollback artifact was created under the private adapter state
  directory, included the previous adapter tree and systemd unit, and passed
  archive listing, gzip, and SHA256 verification.

## Deployed material

The documented adapter target received only committed source trees:

- `adapter/harness_adapter_v2.py` → adapter target;
- `runtime/contracts/` → `contracts/`;
- `runtime/hamh/` → `hamh/`;
- `runtime/providers/` → `providers/`.

Source and target SHA256 fingerprints matched for the adapter and all deployed
provider, HAMH, and contract Python modules. The documented
`autodev-harness-v2` systemd restart completed successfully.

## Post-deployment gates

- `ADAPTER_PROCESS=RUNNING`
- `ADAPTER_HEALTH=HTTP_200`
- `HARNESS_AUTH=PASS` (read-only unknown-job probe returned 404, not 401/403)
- `STATUS_BASELINE=PASS` (service active; n8n root and health endpoint HTTP 200)
- `ROOT_FREE_BYTES_POST_DEPLOY=6927085568`
- Deployed compileall: PASS.
- Deployed negative proof: `NO_ELIGIBLE_FREE_PROVIDER`, DeepSeek identifiers
  blocked, and `AUTOMATIC_PAID_AGENT_ESCALATION=false`.

## Live-provider boundary

The deployed runtime refresh was run through its real catalog entry point. It
returned `entry_count=0` with status-only credential inventory:

- `GROQ_API_KEY=false`
- `OPENROUTER_API_KEY=false`

No Groq/OpenRouter request was made. Account-class, zero-cost, selection-to-
execution, model correlation, and live bidirectional failover therefore remain
unproven and were correctly fail-closed. No DeepSeek or paid request occurred.

`DEPLOYMENT=PASS_COMMITTED_MAIN`
`FREE_FIRST_LIVE_CLOSURE=AMBER_NOT_RUN_NO_DEPLOYMENT_RUNTIME_CREDENTIALS`
