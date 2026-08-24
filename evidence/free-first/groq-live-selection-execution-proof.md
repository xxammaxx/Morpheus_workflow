# Groq live selection/execution proof

- Direct authenticated `/openai/v1/models`: HTTP 200 with the deployed
  `Morpheus-AutoDev/1.0` User-Agent.
- A transient deployed-runtime execution invoked the existing
  `ProviderAdapter.discover_models()` for Groq only. It returned HTTP 200 and
  parsed `MODEL_COUNT=13` using the canonical `Morpheus-AutoDev/1.0` adapter
  User-Agent. No HTTP endpoint was added and no completion was sent.
- `GROQ_DEPLOYED_READONLY_TRANSPORT=PASS`.
- `GROQ_FAILURE_DOMAIN=NO_DEPLOYED_TRANSPORT_FAILURE_PROVEN`.
- `GROQ_CLOUDFLARE_1010=false`.
- Account/tier evidence is unavailable: `GROQ_ACCOUNT_CLASS=UNKNOWN`.
- Completion: `0`; selection-to-execution, zero-cost, and free eligibility are
  not proven. Groq is not promoted because account class is unknown.
