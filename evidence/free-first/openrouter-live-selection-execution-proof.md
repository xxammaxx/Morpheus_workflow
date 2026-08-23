# OpenRouter live selection/execution proof

Catalog refresh: PASS; `openrouter/free` is present with hard-zero pricing.
The retained single bounded completion probe returned HTTP 429, with no saved
body or response headers. `OPENROUTER_429_CLASS=UNKNOWN_429`; no retry was
authorized and no completion was sent in this run. Live selection-to-execution
remains NOT_PROVEN.

The read-only `/api/v1/key` check returned HTTP 200 and explicitly reported a
free-tier key with daily, weekly, and monthly usage equal to zero. Limit and
reset fields were not exposed. This account evidence does not explain the
previous 429 and does not prove live model success.

The implementation uses the provider-owned `openrouter/free` route, captures
the provider-supplied resolved model, and accepts missing response cost only
when the exact route is catalog-proven hard-zero with no paid fallback. A
successful live result must record selected provider/route, actual provider,
non-empty resolved model, request id, usage, and cost proof.
