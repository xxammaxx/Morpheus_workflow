# Groq live selection/execution proof

- Direct authenticated `/openai/v1/models`: HTTP 200 with the deployed
  `Morpheus-AutoDev/1.0` User-Agent.
- The deployed Morpheus adapter has no provider-models endpoint; its
  provider-like paths are protected by the adapter auth boundary. The prior
  403 therefore remains a deployed-path differential, not a proven Groq
  account denial.
- `GROQ_FAILURE_DOMAIN=DEPLOYED_TRANSPORT_OR_REQUEST_DIFFERENCE`.
- `GROQ_403_IS_CLOUDFLARE_1010=false`.
- Account/tier evidence is unavailable: `GROQ_ACCOUNT_CLASS=UNKNOWN`.
- Completion: `0`; selection-to-execution, zero-cost, and free eligibility are
  not proven. Groq is not promoted.
