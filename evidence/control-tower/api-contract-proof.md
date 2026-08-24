# API contract proof

Implemented contracts:

- `autodev.control-tower-overview.v1`
- `autodev.run-view.v1`
- `autodev.timeline-event.v1`
- `autodev.runtime-health.v1`

Contract JSON files are validated by the dashboard test suite. Timeline events
are derived only from observed `started_at` and `ended_at` attempt fields.
