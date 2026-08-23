# Status and observability live proof

- Remote adapter health: HTTP `200`, service healthy, authenticated token boundary independently verified.
- Remote authenticated job read for a nonexistent job: HTTP `404`.
- The remote service exposes the old Baseline adapter and does not expose provider selection/execution fields for this closure implementation.
- Local provider-runtime tests prove the intended selected/actual provider-model correlation and execution-proof contract.
- `STATUS_API_LIVE=PASS_BASELINE_AUTH_ONLY`.
- `PROVIDER_MODEL_CORRELATION=PASS_OFFLINE_IMPLEMENTATION_NOT_LIVE_REMOTE`.
- `HAMH_STATUS=EXPECTED_NOT_AVAILABLE_ON_OLD_REMOTE_PROVIDER_PATH`.

No observability field was invented and no secret/token/header was recorded.
