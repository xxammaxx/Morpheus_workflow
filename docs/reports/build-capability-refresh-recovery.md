# Build capability refresh recovery — 2026-09-01

The refresh-loss regression was reproduced with `opencode/big-pickle`: a
passing build probe made the persisted capability true and the router eligible;
the next live catalog refresh normalized the live `false` values and
`add_entry()` overwrote the empirical values. No router workaround is used.

The fix keeps three layers distinct:

* live catalog normalization supplies static/discovered capabilities;
* the existing provider evidence store supplies only capabilities backed by a
  matching provider, model, probe version, and tool-contract identity;
* effective routing still applies availability, health, cost, privacy, free
  evidence, and DeepSeek policy gates.

Evidence expires after `604800` seconds (7 days). The repository has no
separate periodic refresh schedule; the runtime refreshes once per canonical
run and exposes an explicit maintenance refresh command. Seven days is a
conservative bound for a stable model identity while ensuring an old probe
cannot remain authoritative indefinitely.

Expired, malformed, partial, or identity-mismatched evidence becomes
`NEEDS_REPROBE` and clears the empirical hard-gate fields. A successful live
refresh also marks a previously known OpenCode model unavailable when that
model is absent from the authoritative refreshed catalog.

```text
REFRESH_LOSS_REPRODUCED=PASS
REFRESH_ROOT_CAUSE=LIVE_NORMALIZATION_OVERWROTE_EMPIRICAL_CAPABILITIES
FIRST_BROKEN_FUNCTION=ProviderCatalog.add_entry
CAPABILITY_TTL_SECONDS=604800
CAPABILITY_INVALIDATION_POLICY=provider/model/probe-version/tool-contract mismatch or expiry
STRUCTURED_OUTPUT=covered by the same evidence-aware merge policy
STORE_WRITE=locked temporary-file fsync atomic rename
DEEPSEEK_GATE=unchanged
PAID_REQUESTS=0
DEEPSEEK_REQUESTS=0
```

The capability change is intentionally separate from PR #61 (adaptive harness
foundation) and must be integrated there only as a dependency/update once the
fix is reviewed.
