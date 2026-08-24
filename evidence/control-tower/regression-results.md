# Control Tower regression results

Offline dashboard tests cover projection sanitization, truthful timelines,
contract JSON, unknown/degraded status, GET-only upstream inspection, and
viewer header boundaries. Existing V1 targeted regression remains required
before release.

```text
CONTROL_TOWER_TESTS=8 PASS
V1_CONTRACTS=34 PASS
V1_VALIDATOR_EQUIVALENCE=34 PASS
ADAPTER_TESTS=PASS
N8N_JSON=12/12 PASS
COMPILEALL=PASS
DIFF_CHECK=PASS
PUBLIC_SECRET_SCAN=PASS
```
