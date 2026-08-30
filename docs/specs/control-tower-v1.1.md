# Morpheus Control Tower V1.1 contract (implemented)

Current state at the 2026-08-30 closure audit: the Control Tower is a
read-only observability projection plus an allow-listed operator command
frontend. It is not a second control plane. n8n remains the sole control
plane, Data Tables remain the canonical run/attempt state, and the Adapter
remains the execution plane.

The BFF exposes GET `/healthz`, `/api/v1/overview`, `/api/v1/runs`,
`/api/v1/runs/{run_id}`, `/api/v1/runs/{run_id}/timeline`,
`/api/v1/providers`, `/api/v1/runtime`, `/api/v1/projects`,
`/api/v1/debugging`, `/api/v1/telemetry/runtime`, and `/api/v1/session`.
`POST /api/v1/commands` is the only browser mutation surface; it accepts only
the versioned allow-list and forwards to the canonical n8n webhook. All
dashboard API routes require `X-Control-Tower-Token`; unsupported mutation
paths return 405. Upstream credentials never enter browser storage; the
viewer token is retained only in sessionStorage for the current tab.

Contracts are `autodev.control-tower-overview.v1`, `autodev.run-view.v1`,
`autodev.timeline-event.v1`, `autodev.runtime-health.v1`,
`autodev.runtime-telemetry.v1`, and the project/debugging/command contracts.
Sources are the n8n Public API, authenticated Adapter GETs, and static
release metadata. The browser never reads a database, receives content
bodies, prompts, cookies, authorization headers, or infrastructure secrets.
Operator commands are forwarded only after BFF allow-list and role checks;
the BFF does not select providers or own run state.

Acceptance gates: live n8n and Adapter sources, canonical workflows,
dynamic free-first routing with optional local providers, truthful degraded
mode, viewer-auth tests, read-only telemetry, desktop/mobile responsive and
keyboard QA, no console errors/overflow, V1 regression PASS, and a private-
LAN systemd service. The authoritative current navigation is
`Übersicht → Projekte → Läufe → Anbieter → Systemkarte → Datenfluss →
Debugging → Administration`.
