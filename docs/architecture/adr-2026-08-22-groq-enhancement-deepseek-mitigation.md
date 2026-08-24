# ADR-2026-08-22: Paid DeepSeek Agent-Routing Retirement

> STATUS=HISTORICAL_DELTA_SUPERSEDED_BY_IMPLEMENTED_V1
>
> This ADR is retained for provenance. The implemented V1 runtime and final
> closure evidence supersede its proposed state; the Control Tower is a
> separate V1.1 read-model change.

Status: PROPOSED

## Context

The current Morpheus execution system faces potential cost challenges with DeepSeek provider billing. The existing free-first provider pool in `runtime/providers/router.py` provides a foundation for potential improvement but may need bounded provider failover repair.

Key architectural constraints from existing accepted ADR-2026-08-21:
- n8n remains the control plane
- HAMH remains the harness authority
- The verifier remains result authority
- No new authorities, databases, or control planes
- Existing execution adapter owns provider selection and dispatch

## Problem Statement

**PROPOSED DeepSeek Paid Agent Routing Risk**: Morpheus catalog has DeepSeek as PAID/PRIVACY_GATED with explicit paid escalation capability, potentially creating budget overruns and requiring manual intervention. Local OpenCode has no DeepSeek mapping in active config, but historical backups/scripts remain.

**PROPOSED Groq Transport Issues**: Groq provider requests may fail due to missing or malformed User-Agent headers in `runtime/providers/adapters.py`, potentially causing execution failures and inconsistent routing.

**PROPOSED Bounded Provider Failover Repair**: Current failover in `runtime/providers/router.py` may need repair to prove bounded provider ownership and maintain failover-vs-task-retry separation.

## Decision

PROPOSED retirement of paid DeepSeek agent routing while maintaining historical evidence, and PROPOSED repair of Groq transport within the existing architecture:

```text
n8n control plane → adapter router → provider/model/endpoint → HAMH → backend
```

The PROPOSED changes include:

1. **PROPOSED Paid DeepSeek Agent-Routing Retirement**
   - Retire paid DeepSeek agent routing in `adapter/harness_adapter_v2.py`
   - Remove DeepSeek from provider selection in `runtime/providers/router.py`
   - Retain historical evidence of previous DeepSeek usage
   - Preserve explicit paid escalation capability for audit purposes
   - Implement alternative free-tier routing maintaining equivalent functionality

2. **PROPOSED Groq Transport Repair**
   - Fix User-Agent header construction in `runtime/providers/adapters.py`
   - Validate Groq endpoint connectivity using existing health monitoring
   - Ensure proper request formatting for existing OpenAI-compatible protocol

3. **PROPOSED Bounded Provider Failover Repair**
   - Prove/repair bounded provider failover in existing `runtime/providers/router.py`
   - Maintain existing bounded failover without persistence or recovery mechanisms
   - Ensure failover-vs-task-retry separation is preserved
   - Maintain feature-off behavior that preserves existing functionality

4. **PROPOSED Observability Enhancement**
   - Add provider-level health monitoring using existing `runtime/providers/catalog.py`
   - Implement routing decision logging with cost impact analysis
   - Extend existing status read model to expose provider routing fields
   - Ensure outbound ownership and requested/resolved/actual identity separation

5. **PROPOSED Shadow Readiness**
   - Implement shadow mode validation for provider configurations
   - Add comprehensive health check suites for failover scenarios
   - Create automated readiness scoring using existing metadata
   - Validate feature-off behavior maintains existing functionality

## Alternatives

### A. Separate Service for Provider Management

Rejected. Adds another authority, deployment complexity, and correlation boundary without operational necessity. The existing adapter already owns provider selection, dispatch, and metadata.

### B. Modify HAMH for Provider Logic

Rejected. HAMH is the harness authority and must remain focused on model/task/tool/context configuration, not provider quota, billing, or failover policy.

### C. Extend n8n Control Plane

Rejected. Duplicates provider policy in the control plane, cannot prove selected provider owns actual request, and mixes orchestration with execution concerns.

### D. Maintain Current DeepSeek Paid Usage

Rejected. DeepSeek billing risk creates unacceptable budget overruns and requires manual intervention.

## Consequences

### Positive

- **Cost Control**: Eliminates unexpected DeepSeek billing and optimizes free tier utilization
- **Improved Reliability**: Groq transport fixes and bounded failover repair reduce execution failures
- **Enhanced Observability**: Comprehensive monitoring improves troubleshooting and capacity planning
- **Better Shadow Validation**: Automated readiness scoring reduces promotion risk
- **Maintained Compatibility**: Existing authorities and interfaces remain unchanged

### Negative

- **Increased Complexity**: Enhanced monitoring and failover logic add operational overhead
- **Testing Burden**: Comprehensive validation requires extensive test coverage
- **Configuration Surface**: More provider options increase configuration complexity
- **Historical Data**: DeepSeek retirement may impact historical data analysis

### Neutral

- **Performance Impact**: Minimal overhead from monitoring and logging
- **Learning Curve**: Team needs to understand new failover and monitoring concepts
- **Documentation**: Updated documentation required for new features

## Implementation Strategy

### Phase 1: Paid DeepSeek Agent-Routing Retirement
1. Retire paid DeepSeek agent routing in `adapter/harness_adapter_v2.py`
2. Remove DeepSeek from provider selection in `runtime/providers/router.py`
3. Retain historical evidence of previous DeepSeek usage
4. Preserve explicit paid escalation capability for audit purposes
5. Implement alternative free-tier routing maintaining equivalent functionality

### Phase 2: Groq Transport Repair
1. Fix User-Agent header construction in `runtime/providers/adapters.py`
2. Validate Groq endpoint connectivity using existing health monitoring
3. Ensure proper request formatting for existing OpenAI-compatible protocol

### Phase 3: Bounded Provider Failover Repair
1. Prove/repair bounded provider failover in existing `runtime/providers/router.py`
2. Maintain existing bounded failover without persistence or recovery mechanisms
3. Ensure failover-vs-task-retry separation is preserved
4. Maintain feature-off behavior that preserves existing functionality

### Phase 4: Observability and Shadow Readiness
1. Add provider-level health monitoring using existing `runtime/providers/catalog.py`
2. Implement routing decision logging with cost impact analysis
3. Extend existing status read model to expose provider routing fields
4. Implement shadow mode validation for provider configurations
5. Validate feature-off behavior maintains existing functionality

## PROPOSED Success Criteria (Future Implementation)

1. **PROPOSED DeepSeek Retirement**: Zero DeepSeek billing events in both Morpheus and OpenCode execution
2. **PROPOSED Groq Transport**: 100% of Groq requests include properly formatted User-Agent headers
3. **PROPOSED Bounded Failover**: Proves outbound ownership and maintains failover-vs-task-retry separation
4. **PROPOSED Observability**: 100% routing decision coverage with cost impact
5. **PROPOSED Shadow**: Automated readiness scoring with > 90% accuracy

## PROPOSED Monitoring and Validation (Future Implementation)

- **PROPOSED DeepSeek Usage**: Continuous monitoring to ensure no DeepSeek calls are made
- **PROPOSED Groq Transport**: Success rate and header validation monitoring
- **PROPOSED Failover Events**: Bounded provider failover validation and outbound ownership proof
- **PROPOSED Shadow Validation**: Comprehensive test coverage and readiness scoring
- **PROPOSED Cost Impact**: Actual vs. expected cost comparison with variance alerts

## PROPOSED Rollback Plan (Future Implementation)

1. **PROPOSED Configuration Revert**: Restore DeepSeek configuration in `adapter/harness_adapter_v2.py`
2. **PROPOSED Feature Disable**: Turn off new features while maintaining core functionality
3. **PROPOSED Validation**: Compare rollback performance against baseline metrics
4. **PROPOSED Evidence Preservation**: Maintain historical evidence in `evidence/free-first/`

## PROPOSED Dependencies (Future Implementation)

- **PROPOSED Existing Adapter**: Free-first provider pool implementation in `runtime/providers/router.py`
- **PROPOSED HAMH Compatibility**: No changes required to harness authority
- **PROPOSED n8n Integration**: No changes required to control plane
- **PROPOSED Monitoring Infrastructure**: Existing logging and alerting systems
- **PROPOSED Historical Data**: Retention of previous DeepSeek usage patterns

## PROPOSED Historical Evidence Retention (Future Implementation)

- **PROPOSED DeepSeek Usage Logs**: Maintain historical records of DeepSeek usage patterns (FUTURE ARTIFACT: deepseek-history.log)
- **PROPOSED Cost Impact Analysis**: Preserve cost data before and after DeepSeek retirement (FUTURE ARTIFACT: cost-impact.log)
- **PROPOSED Performance Baselines**: Retain performance metrics for comparison (FUTURE ARTIFACT: performance-baseline.log)
- **PROPOSED Configuration History**: Maintain version history of provider configurations (FUTURE ARTIFACT: config-history.log)
- **PROPOSED Audit Trails**: Preserve audit logs for compliance and analysis (FUTURE ARTIFACT: audit-trails.log)

## PROPOSED Future Considerations (Future Implementation)

- **PROPOSED Provider Expansion**: Potential addition of other free-tier providers
- **PROPOSED Cost Optimization**: Advanced cost forecasting and optimization
- **PROPOSED Enhanced Monitoring**: Additional metrics and alerting capabilities
- **PROPOSED Historical Analysis**: Long-term impact analysis of DeepSeek retirement
