# Morpheus Control Tower V1.1

Current state at V1 boundary: `NO_DASHBOARD`.

Target: `READ_ONLY_CONTROL_TOWER`.

The BFF exposes GET `/healthz`, `/api/v1/overview`, `/api/v1/runs`,
`/api/v1/runs/{run_id}`, `/api/v1/runs/{run_id}/timeline`,
`/api/v1/providers`, and `/api/v1/runtime`. All dashboard API routes require
`X-Control-Tower-Token`; mutation methods return 405. Upstream credentials and
the viewer token never enter browser storage except the viewer token in
sessionStorage for the current tab.

Contracts are `autodev.control-tower-overview.v1`, `autodev.run-view.v1`,
`autodev.timeline-event.v1`, and `autodev.runtime-health.v1`. Sources are the
n8n Public API, authenticated Adapter GETs, and static release metadata. No
direct database reads, content bodies, prompts, cookies, authorization
headers, provider calls, or control operations are allowed.

Acceptance gates: live n8n and adapter sources, 12 workflows, OpenRouter and
Ollama free pool, both canonical runs findable, truthful degraded mode,
viewer-auth tests, GET-only inspection, desktop/mobile responsive and keyboard
QA, no console errors/overflow, V1 regression PASS, and private-LAN systemd
service active.
