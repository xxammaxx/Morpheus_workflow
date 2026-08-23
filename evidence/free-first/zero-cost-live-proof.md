# Zero-cost live proof

## Groq

`GROQ_ZERO_COST=NOT_PROVEN_FAIL_CLOSED`: catalog/auth metadata did not establish the account class, so no completion was attempted.

## OpenRouter

The current provider catalog reported prompt and completion price `0` for explicit `:free` routes, and the route contract has `automatic_paid_fallback=false`. However, both bounded completion attempts failed before a successful correlated response (`429`, then `404`). Therefore:

`OPENROUTER_ZERO_COST=CATALOG_ZERO_PRICE_PROVEN_BUT_LIVE_ROUTE_NOT_PROVEN`.

Global invariants observed in this run:

- `PAID_REQUESTS=0`.
- `DEEPSEEK_REQUESTS=0`.
- No automatic paid fallback was enabled or invoked.
