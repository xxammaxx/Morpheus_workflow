# OpenRouter live selection/execution proof

Catalog refresh: PASS; `openrouter/free` is present with hard-zero pricing.
The single bounded completion probe returned HTTP 429, so live
selection-to-execution remains NOT_PROVEN. The implementation uses the provider-owned
`openrouter/free` route, captures the provider-supplied resolved model, and
accepts missing response cost only when the exact route is catalog-proven
hard-zero with no paid fallback. A successful live result must record selected
provider/route, actual provider, non-empty resolved model, request id, usage,
and cost proof. No retry or paid fallback was attempted.
