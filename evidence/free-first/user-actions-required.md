# USER_ACTION_REQUIRED

PROVIDER=Groq, Cohere, OpenRouter, Mistral, Gemini, Cloudflare, NVIDIA Build,
Cerebras, Hugging Face, Fireworks

ACTION_REQUIRED=Create/authorize the provider account as desired and place the
API credential in the approved secret store. Do not put credentials in Git or
workflow JSON.

WHY=The current shell inventory has no provider credentials, so external live
requests and selection-to-execution proof are auth-blocked. Gemini and other
privacy-gated providers additionally need explicit private-code policy approval.

WHAT_IS_ALREADY_COMPLETE=Adapters, dynamic discovery, normalized contracts,
cost/privacy/quota/health filters, free-first routing, failover, zero-cost
sentinel, quarantine, observability, offline tests, and rollback-safe default.

WHAT_WILL_THIS_UNLOCK=Provider-specific discovery, staged capability probes,
real request/response/usage proof, and external provider failover canary.

BLOCKS_ONLY=Activation of the named provider; it does not block the runtime
foundation or other providers.

PROVIDER=LM Studio

ACTION_REQUIRED=Restore/re-enable the configured endpoint at
`192.168.1.195:1234` or provide an approved reachable local endpoint.

WHY=The current endpoint is unreachable from this workstation.

WHAT_IS_ALREADY_COMPLETE=Local adapter path and historical builder capability
evidence remain intact.

WHAT_WILL_THIS_UNLOCK=Fresh local health/capability and execution proof.

BLOCKS_ONLY=Current LM Studio activation.

PROVIDER=Production

ACTION_REQUIRED=Approve shadow/canary activation after reviewing cost/privacy
policy.

WHY=No unrequested production cutover is permitted.

WHAT_IS_ALREADY_COMPLETE=Shadow-ready implementation and rollback baseline.

WHAT_WILL_THIS_UNLOCK=Production free-first routing.

BLOCKS_ONLY=Production cutover.
