# Groq Enhancement and DeepSeek Retirement - Proposed Runbook

> STATUS=HISTORICAL_DELTA_SUPERSEDED_BY_IMPLEMENTED_V1
>
> Retained unchanged as historical provenance. Current runtime truth is in
> the V1 closure evidence; the read-only Control Tower begins separately in
> V1.1.

## Current State

- D1: User-Agent headers are absent today in `runtime/providers/adapters.py`
- D2: Free pool operates with individual provider quotas
- D3: Bounded failover exists in `runtime/providers/router.py` but needs repair
- D4: DeepSeek remains selectable via explicit paid escalation today in `adapter/harness_adapter_v2.py`
- D5: Active OpenCode config is external to repo (`~/.config/opencode/opencode.json` and policy file)
- D6: Observability uses existing `runtime/providers/catalog.py`
- D7: Shadow validation uses existing infrastructure

## Environment Variables

### Current
- `AUTODEV_FREE_FIRST_ENABLED`: Enable free-first provider routing (default: false)
- `AUTODEV_PROVIDER_CATALOG`: Provider catalog snapshot path
- `AUTODEV_PROVIDER_CAPABILITIES`: Staged capability registry path
- `AUTODB_PROVIDER_FAILOVER_MAX`: Bounded provider failover ceiling (default: 3)
- `GROQ_API_KEY`: Groq API credential

### PROPOSED (Future Implementation)
- `AUTODEV_GROQ_TRANSPORT_ENABLED`: Enable Groq transport fixes
- `AUTODB_BOUNDED_FAILOVER_ENABLED`: Enable bounded provider failover repair
- `AUTODEV_DEEPSEEK_PAID_RETIRED`: Retire paid DeepSeek agent routing
- `AUTODEV_SHADOW_READINESS_ENABLED`: Enable shadow mode validation

## Files

### Current
- `runtime/providers/adapters.py`: Provider adapters including Groq
- `runtime/providers/catalog.py`: Provider metadata and health states
- `runtime/providers/router.py`: Free-first routing and failover logic
- `runtime/providers/runtime.py`: Provider runtime execution
- `adapter/harness_adapter_v2.py`: Execution adapter

### PROPOSED Test/Evidence Files (Future)
- `evidence/free-first/groq-transport.log`
- `evidence/free-first/free-pool.log`
- `evidence/free-first/failover.log`
- `evidence/free-first/deepseek-retirement.log`
- `evidence/free-first/observability.log`
- `evidence/free-first/shadow-readiness.log`

## Maintenance

### Current Command
```bash
PYTHONPATH=runtime python3 -m providers.refresh
```

### Current Endpoint
```bash
curl -X GET "http://your-morpheus-instance/v1/providers/catalog" \
  -H "Authorization: Bearer $AUTODB_API_TOKEN"
```

## PROPOSED Procedures (Future Implementation)

### D1 PROPOSED Groq Transport Fix
- Fix User-Agent headers in `runtime/providers/adapters.py`
- Validate Groq endpoint connectivity
- Ensure proper request formatting

### D2 PROPOSED Free Pool Enhancement
- Create unified free tier eligibility in `runtime/providers/router.py`
- Implement shared quota management
- Add cost validation

### D3 PROPOSED Bounded Failover Repair
- Repair bounded provider failover in `runtime/providers/router.py`
- Implement outbound ownership proof
- Preserve failover-vs-task-retry separation

### D4 PROPOSED DeepSeek Retirement (Morpheus)
- Retire paid DeepSeek routing in `adapter/harness_adapter_v2.py`
- Remove DeepSeek from provider selection
- Preserve paid escalation for audit

### D5 PROPOSED DeepSeek Retirement (OpenCode)
- Update external OpenCode config (`~/.config/opencode/opencode.json`)
- Remove DeepSeek from OpenCode workflows
- Preserve historical evidence

### D6 PROPOSED Observability Enhancement
- Add health monitoring in `runtime/providers/catalog.py`
- Implement routing decision logging
- Extend status read model

### D7 PROPOSED Shadow Readiness
- Implement shadow validation for provider configurations
- Add health check suite for failover scenarios
- Create automated readiness scoring

## Constraints

- No live/paid DeepSeek calls before authorization
- No production cutover without explicit approval
- All evidence stored as flat files under `evidence/free-first/`
- No new authorities, databases, or control planes
