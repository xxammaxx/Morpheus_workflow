# OpenRouter live selection-to-execution proof

- `OPENROUTER_AUTH=PASS`.
- `OPENROUTER_CATALOG=PASS`.
- Dynamic catalog contained 22 free candidates.
- First explicit route candidate: `cohere/north-mini-code:free`.
- A committed local provider-runtime probe selected that explicit `:free` route, then the real provider returned HTTP `429` (rate limit); no paid fallback occurred.
- A bounded second explicit `:free` candidate, `liquid/lfm-2.5-2.6b:free`, returned HTTP `404` (model availability).
- `OPENROUTER_COMPLETION=FAIL_RATE_LIMIT_AND_MODEL_AVAILABILITY`.
- `OPENROUTER_SELECTED_PROVIDER=NOT_PROVEN_SUCCESS`.
- `OPENROUTER_ACTUAL_PROVIDER=NOT_PROVEN_SUCCESS`.
- `OPENROUTER_SELECTED_MODEL=cohere/north-mini-code:free (attempted)`.
- `OPENROUTER_RESOLVED_MODEL=NOT_AVAILABLE`.
- `OPENROUTER_SELECTION_TO_EXECUTION=NOT_PROVEN`.
- `OPENROUTER_ZERO_COST=CATALOG_ZERO_PRICE_PROVEN_BUT_LIVE_ROUTE_NOT_PROVEN`.

The route was explicit and catalog-priced at zero, but no successful correlated completion exists. No further model probing was performed after the bounded attempts.
