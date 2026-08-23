# External provider diagnostics — 2026-08-24

All values are sanitized. No key, authorization value, cookie, user/workspace
identifier, key hash, billing detail, or raw provider response is stored.

## OpenRouter

- `GET /api/v1/key`: HTTP 200; key valid, `is_free_tier=true`; daily, weekly,
  and monthly usage were all `0`.
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

## Groq

- Direct same-key `GET https://api.groq.com/openai/v1/models`: HTTP 200,
  including with `Morpheus-AutoDev/1.0`, the deployed application UA.
- The deployed adapter exposes no provider `/models` handler. Read-only
  provider-like paths returned 401 from the adapter auth boundary; the
  checked-in handler has only health, jobs, batches, and artifacts routes.
- The differential is
  `GROQ_FAILURE_DOMAIN=DEPLOYED_TRANSPORT_OR_REQUEST_DIFFERENCE`; the earlier
  deployed 403 is not reproducible as a Groq provider response from the current
  exposed path.
- `GROQ_403_IS_CLOUDFLARE_1010=false`: no 1010 marker was present in the
  available sanitized evidence, and the same credential and deployed UA
  succeed directly.
- No authenticated Groq Console/tier session or official tier endpoint was
  available. `GROQ_ACCOUNT_CLASS=UNKNOWN` and
  `GROQ_TIER_UI=BLOCKED_NO_AUTHENTICATED_SESSION`.
- Groq completion attempts: `0`.
