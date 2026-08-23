# Rollback Proof

The feature is disabled by default with `AUTODEV_FREE_FIRST_ENABLED=false`.
When disabled, `_dispatch()` skips provider selection and preserves the
existing backend/provider/model defaults, HAMH resolution, retry semantics, and
ledger behavior. The existing adapter and DeepSeek/LM Studio behavior are the
rollback baseline. No destructive migration was performed.
