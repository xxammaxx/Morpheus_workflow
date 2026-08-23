# Quota diagnostics — 2026-08-24

All provider values below are sanitized. No key material, key prefix, user ID,
workspace ID, label, hash, billing detail, or raw provider response is stored.

## OpenRouter

- Read-only `GET /api/v1/key`: HTTP 200.
- `OPENROUTER_KEY_VALID=true`; `OPENROUTER_IS_FREE_TIER=true`.
- `OPENROUTER_KEY_LIMIT=NOT_EXPOSED`; `OPENROUTER_KEY_LIMIT_REMAINING=NOT_EXPOSED`;
  `OPENROUTER_KEY_LIMIT_RESET=NOT_EXPOSED`.
- Daily, weekly, and monthly usage were all `0`.
- Disabled status was not exposed; expiry was `null`.
- The stored prior completion evidence contains only HTTP 429, without body or
  response headers. Therefore `OPENROUTER_429_CLASS=UNKNOWN_429` and
  `OPENROUTER_RETRY_AFTER=NOT_CAPTURED`.
- No completion was sent to recreate the 429. `OPENROUTER_REPROBE_ALLOWED=false`
  for this run; no reset timestamp can be derived.

OpenRouter documents generic free-model limits of 50 requests/day, or 1000
requests/day after at least 10 credits have been purchased. This is provider
documentation only and is not used as the concrete 429 classification:
https://openrouter.ai/docs/faq

## Groq

- Read-only authenticated `GET /openai/v1/models`: HTTP 403 in this run.
- No authenticated Groq Console, Settings, Billing, Plan, or Tier UI evidence
  was available locally.
- `GROQ_ACCOUNT_CLASS=UNKNOWN` and
  `GROQ_ACCOUNT_CLASS_EVIDENCE=BLOCKED_NO_AUTHENTICATED_ACCOUNT_VIEW`.
- No Groq completion was sent.

Groq documents spend limits as paid-plan-only, and Developer-tier upgrades
require a payment method. These are supporting rules, not account-class proof:
https://console.groq.com/docs/spend-limits
