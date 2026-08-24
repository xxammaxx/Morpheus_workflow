# OpenRouter live selection/execution proof

- Fresh catalog: `openrouter/free` present with prompt/completion price `0`.
- Exactly one instrumented live request was sent to the selected route.
- Selection: `openrouter/free`; execution: HTTP 429.
- The provider returned `free-models-per-day`, limit `50`, remaining `0`,
  and a reset timestamp. No generation ID or router metadata was returned.
- `OPENROUTER_SELECTION_TO_EXECUTION=FAIL_FREE_TIER_LIMIT`.
- The route remains unpromoted. `OPENROUTER_COST_PROOF=NOT_APPLICABLE` and
  `OPENROUTER_ZERO_COST=NOT_PROVEN_LIVE` because no completion succeeded.
- This continuation sent `OPENROUTER_COMPLETION_ATTEMPTS=0`: the stored reset
  was stale and the current read-only key response did not prove a new
  free-request window.
