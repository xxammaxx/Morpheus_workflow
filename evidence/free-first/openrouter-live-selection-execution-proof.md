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

## Current quota-isolation run — 2026-08-24

- Fresh read-only checks proved the Free-tier key and the zero-priced
  `openrouter/free` catalog route.
- OpenCode was observed on `opencode/big-pickle`; no active local OpenRouter
  route was proven.
- n8n was healthy, but active executions could not be queried without the
  unavailable n8n API credential. The isolation gate therefore remained
  fail-closed: `QUOTA_ISOLATION=NOT_PROVEN`.
- `OPENROUTER_MODEL_REQUESTS_THIS_RUN=0`; no completion, retry, promotion,
  resolved model, usage, or live zero-cost proof exists for this run.
