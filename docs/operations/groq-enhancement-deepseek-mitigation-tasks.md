# Groq Enhancement and DeepSeek Retirement - Proposed Atomic Tasks

## D1 PROPOSED Groq Transport Fix

**Task**: PROPOSED Fix User-Agent Header Construction

**Files**:
- `runtime/providers/adapters.py`
- `runtime/providers/protocol.py`

**Action**: PROPOSED fix User-Agent headers in `runtime/providers/adapters.py`

**Test**: PROPOSED unit tests in `runtime/tests/test_provider_adapter_integration.py`

**Evidence**: `evidence/free-first/groq-transport.log` (FUTURE ARTIFACT)

---

## D2 PROPOSED Free Pool Enhancement

**Task**: PROPOSED Implement Unified Free Tier Eligibility

**Files**:
- `runtime/providers/router.py`
- `runtime/providers/catalog.py`
- `runtime/providers/protocol.py`

**Action**: PROPOSED create unified free tier eligibility in `runtime/providers/router.py`

**Test**: PROPOSED integration tests in `runtime/tests/test_provider_runtime.py`

**Evidence**: `evidence/free-first/free-pool.log` (FUTURE ARTIFACT)

---

## D3 PROPOSED Bounded Failover Repair

**Task**: PROPOSED Repair Bounded Provider Failover

**Files**:
- `runtime/providers/router.py`
- `runtime/providers/catalog.py`

**Action**: PROPOSED repair bounded provider failover in `runtime/providers/router.py`

**Test**: PROPOSED integration tests in `runtime/tests/test_provider_runtime.py`

**Evidence**: `evidence/free-first/failover.log` (FUTURE ARTIFACT)

---

## D4 PROPOSED DeepSeek Retirement (Morpheus)

**Task**: PROPOSED Retire Paid DeepSeek Agent Routing

**Files**:
- `adapter/harness_adapter_v2.py`
- `runtime/providers/router.py`

**Action**: PROPOSED retire paid DeepSeek routing in `adapter/harness_adapter_v2.py`

**Test**: PROPOSED integration tests in `runtime/tests/test_provider_runtime.py`

**Evidence**: `evidence/free-first/deepseek-retirement.log` (FUTURE ARTIFACT)

---

## D5 PROPOSED DeepSeek Retirement (OpenCode)

**Task**: PROPOSED Retire DeepSeek from OpenCode Execution

**Files**:
- `adapter/harness_adapter_v2.py`
- External: `~/.config/opencode/opencode.json`
- External: OpenCode policy file

**Action**: PROPOSED update external OpenCode configuration to remove DeepSeek

**Test**: PROPOSED integration tests in `runtime/tests/test_provider_runtime.py`

**Evidence**: `evidence/free-first/deepseek-retirement.log` (FUTURE ARTIFACT)

---

## D6 PROPOSED Observability Enhancement

**Task**: PROPOSED Implement Provider-Level Health Monitoring

**Files**:
- `runtime/providers/catalog.py`
- `runtime/providers/router.py`
- `adapter/harness_adapter_v2.py`

**Action**: PROPOSED add health monitoring in `runtime/providers/catalog.py`

**Test**: PROPOSED integration tests in `runtime/tests/test_provider_runtime.py`

**Evidence**: `evidence/free-first/observability.log` (FUTURE ARTIFACT)

---

## D7 PROPOSED Shadow Readiness

**Task**: PROPOSED Implement Shadow Mode Validation

**Files**:
- `runtime/providers/catalog.py`
- `runtime/providers/router.py`
- `adapter/harness_adapter_v2.py`

**Action**: PROPOSED implement shadow validation for provider configurations

**Test**: PROPOSED integration tests in `runtime/tests/test_provider_runtime.py`

**Evidence**: `evidence/free-first/shadow-readiness.log` (FUTURE ARTIFACT)

## Constraints

- All tasks are PROPOSED and not yet implemented
- No live/paid DeepSeek calls before authorization
- No production cutover without explicit approval
- Evidence stored as flat files under `evidence/free-first/`
- No new authorities, databases, or control planes
