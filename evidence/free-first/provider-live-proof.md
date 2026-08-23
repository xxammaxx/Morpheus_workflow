# Provider Live Proof

## Current run

- No provider API credentials were present in the shell environment.
- LM Studio at the historically configured address was unreachable.
- Therefore no external provider live request is claimed in this run.
- The existing DeepSeek proof remains historical evidence and was not falsely
  reused as a fresh current call.

## Offline real-request proof

`runtime/tests/test_provider_adapter_integration.py` starts a local HTTP provider,
routes through the actual adapter `_dispatch()` seam, sends a real HTTP request,
and verifies selected provider/model, outbound request, actual response, usage,
and execution proof. This is a contract/integration proof, not an external live
provider proof.
