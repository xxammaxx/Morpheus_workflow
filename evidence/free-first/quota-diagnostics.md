# External provider diagnostics — 2026-08-24

All values are sanitized. No key, authorization value, cookie, user/workspace
identifier, key hash, billing detail, or raw provider response is stored.

## OpenRouter

- Current read-only `GET /api/v1/key`: HTTP 200; key valid,
  `is_free_tier=true`; `usage_daily=0`. This is not treated as free-request
  quota evidence because the endpoint exposes no free-request remaining/reset.
- `GET /api/v1/models`: HTTP 200; `openrouter/free` present with prompt and
  completion pricing `0`.
- Exactly one authorized model request was sent to `openrouter/free`, with
  `X-OpenRouter-Metadata: enabled`, a synthetic two-word prompt, and
  `max_tokens=1`. No retry was sent.
- Result: HTTP 429; sanitized error code `429`; message class
  `free-models-per-day`; `X-RateLimit-Limit=50`,
  `X-RateLimit-Remaining=0`, `X-RateLimit-Reset=1787529600000`
  (`2026-08-24T00:00:00Z`). `Retry-After` was absent. No generation ID or
  router metadata was returned.
- Classification: `OPENROUTER_429_CLASS=OPENROUTER_FREE_TIER_LIMIT`.
  The response directly identifies the free-model daily limit.
- `NEXT_OPENROUTER_PROBE_NOT_BEFORE=2026-08-24T00:00:00Z`; no further probe
  was issued.
- `OPENROUTER_BYOK_ACTIVE=not_proven`; no safe account-level BYOK signal was
  available, so no BYOK economics are assumed.
- The stored reset timestamp is in the past at this run's UTC observation:
  `STORED_RESET_TIMESTAMP_STATE=PAST_OR_STALE`. The current key response did
  not prove a new free-request window, so no model request was sent.
- `OPENROUTER_SHARED_CONSUMERS=MULTIPLE`: OpenCode and the deployed
  Morpheus/n8n execution path can use the same account credential.
  `OPENROUTER_QUOTA_SHARED=true`.

## Groq

- Direct same-key `GET https://api.groq.com/openai/v1/models`: HTTP 200,
  including with `Morpheus-AutoDev/1.0`, the deployed application UA.
- A transient execution inside the deployed service context invoked the
  deployed `ProviderAdapter.discover_models()` for Groq only. It performed
  `GET https://api.groq.com/openai/v1/models`, returned HTTP 200, and parsed
  13 models. No completion was sent.
- `GROQ_DEPLOYED_READONLY_TRANSPORT=PASS`; the earlier deployed 403 is retired
  as `INVALID_OR_NON_EQUIVALENT_DIAGNOSTIC_PATH`.
- `GROQ_FAILURE_DOMAIN=NO_DEPLOYED_TRANSPORT_FAILURE_PROVEN`.
- `GROQ_403_IS_CLOUDFLARE_1010=false`: no 1010 marker was present in the
  available sanitized evidence, and the same credential and deployed UA
  succeed directly.
- No authenticated Groq Console/tier session or official tier endpoint was
  available. `GROQ_ACCOUNT_CLASS=UNKNOWN` and
  `GROQ_TIER_UI=BLOCKED_NO_AUTHENTICATED_SESSION`.
- Groq completion attempts: `0`.
- `GROQ_CLOUDFLARE_1010=false`.
