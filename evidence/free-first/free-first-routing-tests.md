# Free-First Routing Tests

PASS:

- cost class and zero-cost eligibility
- UNKNOWN never eligible
- rate-limit header normalization
- free-first deterministic selection
- capability filtering
- privacy filtering
- provider selection to actual HTTP request
- actual model correlation
- provider failover ceiling
- reasoned paid escalation
- contract validation
- unexpected billing quarantine

Commands:

```text
python3 runtime/tests/test_provider_runtime.py
python3 runtime/tests/test_provider_adapter_integration.py
python3 runtime/tests/test_contracts.py
```
