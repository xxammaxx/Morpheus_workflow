# Groq Enhancement and DeepSeek Retirement Specification

Status: DRAFT / NOT_IMPLEMENTED

## Problem

PROPOSED SCOPE D1-D7: Morpheus execution faces potential reliability and cost challenges:

1. **D1 PROPOSED Groq Transport Issues**: Groq provider requests may fail due to missing or malformed User-Agent headers in `runtime/providers/adapters.py`
2. **D2 PROPOSED Provider Pool Fragmentation**: Limited free tier availability across Groq and OpenRouter may create routing bottlenecks
3. **D3 PROPOSED Bounded Provider Failover**: Current failover in `runtime/providers/router.py` may need repair to prove bounded provider ownership
4. **D4 PROPOSED Morpheus DeepSeek Risk**: Morpheus catalog has DeepSeek as PAID/PRIVACY_GATED with explicit paid escalation capability
5. **D5 PROPOSED OpenCode DeepSeek Risk**: Active local OpenCode config currently has no DeepSeek mapping; retirement is proposed
6. **D6 PROPOSED Observability Gaps**: Limited visibility into provider health and routing decisions in existing `runtime/providers/catalog.py`
7. **D7 PROPOSED Shadow Limitations**: Current shadow mode lacks comprehensive readiness validation for production failover

## Current Reality

Based on existing codebase analysis:
- `runtime/providers/adapters.py` contains Groq adapter where User-Agent headers are absent today
- `runtime/providers/router.py` implements free-first routing with bounded failover
- `runtime/providers/catalog.py` manages provider metadata and health states
- `adapter/harness_adapter_v2.py` handles execution with existing provider paths
- Morpheus catalog has DeepSeek as PAID/PRIVACY_GATED; DeepSeek remains selectable only via explicit paid escalation today
- Local OpenCode active config currently has no DeepSeek mapping; retirement is proposed
- Router currently restricts build/fix/plan to lmstudio only
- No live/paid/DeepSeek calls authorized before production cutover

## Scope

### PROPOSED Scope (D1-D7)

**D1 PROPOSED Groq User-Agent Transport Fix**
- Fix User-Agent header construction in `runtime/providers/adapters.py` for Groq requests
- Validate Groq endpoint connectivity using existing health monitoring
- Ensure proper request formatting for existing OpenAI-compatible protocol

**D2 PROPOSED Groq+OpenRouter Free Pool**
- Create unified free tier eligibility checking in `runtime/providers/router.py`
- Implement shared quota management between Groq and OpenRouter
- Add cost validation to prevent unexpected billing from both providers

**D3 PROPOSED Bounded Provider Failover Repair**
- Prove/repair bounded provider failover in existing `runtime/providers/router.py`
- Maintain existing bounded failover without persistence or recovery mechanisms
- Ensure failover-vs-task-retry separation is preserved

**D4 PROPOSED Morpheus DeepSeek Agent Retirement**
- Retire paid DeepSeek agent routing in `adapter/harness_adapter_v2.py`
- Remove DeepSeek from provider selection in `runtime/providers/router.py`
- Maintain explicit paid escalation capability for audit purposes
- Implement alternative free-tier routing maintaining equivalent functionality

**D5 PROPOSED Local OpenCode DeepSeek Agent Retirement**
- Retire DeepSeek from local OpenCode agent execution in `adapter/harness_adapter_v2.py`
- Update OpenCode configuration to use alternative providers
- Ensure OpenCode workflows use only approved free-tier providers
- Preserve historical evidence of previous DeepSeek usage

**D6 PROPOSED Status/Observability Proof**
- Add provider-level health monitoring using existing `runtime/providers/catalog.py`
- Implement routing decision logging with cost impact analysis
- Extend existing status read model to expose provider routing fields
- Ensure outbound ownership and requested/resolved/actual identity separation

**D7 PROPOSED Read-Only Shadow Readiness**
- Implement shadow mode validation for provider configurations
- Add comprehensive health check suites for failover scenarios
- Create automated readiness scoring using existing metadata
- Validate feature-off behavior maintains existing functionality

### Non-Scope

- Transport retry/backoff mechanisms
- Dashboard implementations
- TLS 1.3/certificate pinning
- Persistence or recovery mechanisms
- Account management or payment processing
- New workflow types or n8n control plane modifications
- Multi-region deployment or geographic failover
- Build/fix/plan routing to external providers (currently restricted to lmstudio)

## Cost

- **Implementation**: Zero additional cost for existing infrastructure
- **Runtime**: Minimal overhead from enhanced logging and monitoring
- **Testing**: Shadow mode validation uses existing compute resources
- **Mitigation**: Eliminates unexpected DeepSeek billing costs
- **Optimization**: Reduces paid escalation through improved free tier utilization

## Privacy

- **Data Minimization**: Only essential routing metadata collected and stored
- **Consent**: No new data collection beyond existing execution logs
- **Retention**: Routing logs retained according to existing policies
- **Compliance**: Maintains compliance with existing data protection standards

## PROPOSED Acceptance Criteria (Future Implementation Gates)

### D1 PROPOSED Groq User-Agent Transport Fix
- [ ] All Groq requests in `runtime/providers/adapters.py` include properly formatted User-Agent headers
- [ ] Groq endpoint connectivity validated before routing using existing health checks
- [ ] Transport failures trigger appropriate failover to alternative providers
- [ ] No live/paid Groq calls before authorization and production cutover
- [ ] Outbound ownership proven for all Groq requests

### D2 PROPOSED Groq+OpenRouter Free Pool
- [ ] Unified free tier eligibility checking prevents paid fallback in `runtime/providers/router.py`
- [ ] Shared quota management prevents simultaneous quota exhaustion
- [ ] Cost validation quarantines providers with unexpected billing
- [ ] No live/paid calls from either provider before authorization
- [ ] Requested/resolved/actual identity separation maintained

### D3 PROPOSED Bounded Provider Failover Repair
- [ ] Bounded provider failover in `runtime/providers/router.py` proves outbound ownership
- [ ] Requested/resolved/actual identity separation is maintained
- [ ] Failover-vs-task-retry separation is preserved
- [ ] Feature-off behavior maintains existing functionality
- [ ] No paid escalation occurs during failover

### D4 PROPOSED Morpheus DeepSeek Agent Retirement
- [ ] Paid DeepSeek agent routing retired in `adapter/harness_adapter_v2.py`
- [ ] DeepSeek removed from provider selection in `runtime/providers/router.py`
- [ ] Explicit paid escalation capability preserved for audit purposes
- [ ] Alternative free-tier routing maintains equivalent functionality
- [ ] No live/paid DeepSeek calls before authorization

### D5 PROPOSED Local OpenCode DeepSeek Agent Retirement
- [ ] DeepSeek retired from local OpenCode agent execution in `adapter/harness_adapter_v2.py`
- [ ] OpenCode configuration updated to use alternative providers
- [ ] OpenCode workflows use only approved free-tier providers
- [ ] Historical evidence of previous DeepSeek usage preserved
- [ ] No live/paid DeepSeek calls before authorization

### D6 PROPOSED Status/Observability Proof
- [ ] Provider-level health monitoring using existing `runtime/providers/catalog.py`
- [ ] Routing decisions logged with cost impact analysis
- [ ] Existing status read model exposes provider routing fields without database changes
- [ ] Outbound ownership and requested/resolved/actual identity separation proven
- [ ] No new authorities or control planes introduced

### D7 PROPOSED Read-Only Shadow Readiness
- [ ] Shadow mode validates all provider configurations
- [ ] Comprehensive health check suite for failover scenarios
- [ ] Automated readiness scoring for production promotion
- [ ] Shadow performance metrics compared against production baselines
- [ ] Feature-off behavior validation maintains existing functionality

### Canonical Existing Free-First Criteria (Must Be Preserved)
- [ ] Outbound ownership proven for all provider requests
- [ ] Requested/resolved/actual identity separation maintained
- [ ] No paid escalation occurs during normal operation
- [ ] Failover distinct from semantic task retry
- [ ] Feature-off restoration maintains existing functionality

## PROPOSED Test Definitions (Future Implementation)

### D1 PROPOSED Transport Validation
- Unit tests for User-Agent header construction in `runtime/providers/adapters.py`
- Integration tests for Groq endpoint connectivity validation
- Failover trigger validation under persistent transport failures

### D2 PROPOSED Free Pool Testing
- Unit tests for unified free tier eligibility in `runtime/providers/router.py`
- Integration tests for shared quota management
- Cost validation and quarantine scenario tests

### D3 PROPOSED Bounded Failover Testing
- Unit tests for bounded provider failover in `runtime/providers/router.py`
- Integration tests for outbound ownership proof
- Failover-vs-task-retry separation validation

### D4/D5 PROPOSED DeepSeek Testing
- Unit tests for DeepSeek retirement in `adapter/harness_adapter_v2.py`
- Integration tests for alternative routing
- Configuration validation tests for both Morpheus and OpenCode

### D6 PROPOSED Observability Testing
- Integration tests for provider health monitoring in `runtime/providers/catalog.py`
- Routing decision logging validation
- Status read model field exposure tests

### D7 PROPOSED Shadow Testing
- Comprehensive validation of shadow mode readiness criteria
- Health check suite validation for failover scenarios
- Automated readiness scoring accuracy tests
- Feature-off behavior validation tests
- Tests using `runtime/tests/test_provider_runtime.py`

## Rollback Strategy

1. **Configuration Rollback**: Revert provider configuration in `runtime/providers/router.py` and `adapter/harness_adapter_v2.py`
2. **Feature Flag**: Disable new features while maintaining existing functionality
3. **Validation**: Compare rollback performance against baseline metrics
4. **Evidence Preservation**: Maintain historical evidence in `evidence/free-first/`

## PROPOSED Evidence Requirements (Future Implementation)

### D1 PROPOSED Transport Evidence
- Successful Groq requests with proper headers (FUTURE ARTIFACT: groq-transport-success.log)
- Endpoint connectivity validation logs (FUTURE ARTIFACT: groq-connectivity.log)
- Failover event records (FUTURE ARTIFACT: groq-failover.log)

### D2 PROPOSED Free Pool Evidence
- Unified free tier usage logs (FUTURE ARTIFACT: free-pool-usage.log)
- Cost validation results (FUTURE ARTIFACT: cost-validation.log)
- Shared quota management logs (FUTURE ARTIFACT: quota-management.log)

### D3 PROPOSED Bounded Failover Evidence
- Bounded provider failover validation logs (FUTURE ARTIFACT: failover-validation.log)
- Outbound ownership proof records (FUTURE ARTIFACT: outbound-ownership.log)
- Requested/resolved/actual identity separation logs (FUTURE ARTIFACT: identity-separation.log)
- Failover-vs-task-retry separation validation (FUTURE ARTIFACT: failover-distinction.log)

### D4/D5 PROPOSED DeepSeek Evidence
- DeepSeek retirement verification logs (FUTURE ARTIFACT: deepseek-retirement.log)
- Alternative routing configuration records (FUTURE ARTIFACT: alternative-routing.log)
- OpenCode configuration validation logs (FUTURE ARTIFACT: opencode-config.log)
- Historical evidence preservation records (FUTURE ARTIFACT: deepseek-history.log)

### D6 PROPOSED Observability Evidence
- Provider health monitoring logs (FUTURE ARTIFACT: health-monitoring.log)
- Routing decision logs with cost impact (FUTURE ARTIFACT: routing-decisions.log)
- Status read model field verification (FUTURE ARTIFACT: status-fields.log)
- Outbound ownership validation records (FUTURE ARTIFACT: observability-ownership.log)

### D7 PROPOSED Shadow Evidence
- Shadow mode validation reports (FUTURE ARTIFACT: shadow-validation.log)
- Health check suite execution records (FUTURE ARTIFACT: health-checks.log)
- Automated readiness scoring logs (FUTURE ARTIFACT: readiness-scoring.log)
- Feature-off behavior validation records (FUTURE ARTIFACT: feature-off-validation.log)

## GitHub Source of Truth

Status: DEFERRED - Governance audit found no canonical local requirement and no remote identity for implementation details