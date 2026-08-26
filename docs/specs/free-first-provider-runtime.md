# Free-First Provider Runtime Specification

## Operational Note: Fail-Closed Free-First Behavior

The dynamic free-model routing operates in a **fail-closed** mode for free-first provider selection:

- **Unknown providers** never enter the free pool
- **Positive costs** on free routes quarantine the exact path
- **Free-pool exhaustion** returns `NO_ELIGIBLE_FREE_PROVIDER` (no fallback to paid providers)
- **DeepSeek** remains paid escalation only unless explicitly selected by policy
- **During active probe leases**, ordinary traffic fails closed to that provider

## Verification Command

To verify the current fail-closed free-first behavior:

```bash
PYTHONPATH=runtime python3 -m pytest -q dashboard/tests
python3 -m compileall -q dashboard
```

These commands validate the runtime implementation and ensure the fail-closed behavior is correctly enforced.
