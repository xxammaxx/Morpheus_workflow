# Free provider pool live proof

Required closure condition was not met.

- `GROQ_SELECTION_TO_EXECUTION=NOT_PROVEN_FAIL_CLOSED`.
- `OPENROUTER_SELECTION_TO_EXECUTION=NOT_PROVEN`.
- `GROQ_ZERO_COST=NOT_PROVEN_FAIL_CLOSED`.
- `OPENROUTER_ZERO_COST=CATALOG_ZERO_PRICE_PROVEN_BUT_LIVE_ROUTE_NOT_PROVEN`.
- `FREE_POOL_SIZE=0_PROVEN_LIVE`; the intended pool size 2 was not claimed.
- `FREE_POOL_PROVIDERS=NOT_CLOSED`.
- `PROVIDER_REDUNDANCY=0_PROVEN_LIVE`.
- `MODEL_REDUNDANCY=22_CATALOG_CANDIDATES_NOT_PROMOTED`.

The implementation remains fail-closed and does not promote a route without selection-to-execution and route-specific cost evidence.
