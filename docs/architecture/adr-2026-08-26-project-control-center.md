# ADR-2026-08-26: Project-centric Control Center boundary

## Decision

## Reality Refresh

`CURRENT_ARCHITECTURE=n8n Data Tables are canonical run/attempt state; the
Python stdlib BFF projects n8n and Adapter reads; Adapter ledger is the
execution telemetry source; GitHub is the collaborative issue backlog.`

`CURRENT_CONTROL_TOWER=German read-only V1.1 views for overview, runs,
providers, system map, and data flow; viewer-token authentication; no writes.`

`AVAILABLE_COMMAND_PATHS=POST /webhook/autodev/start is deployed; the new
allow-listed BFF /api/v1/commands path is implemented but requires the
authenticated n8n command gateway deployment.`

`AVAILABLE_EVENT_SOURCES=n8n run/attempt tables, Adapter canonical ledger
projection, optional canonical project/issue/event tables, provider runtime
metadata.`

`MISSING_PRIMITIVES=deployed n8n command gateway and canonical project/issue
continuation workflows; production operator/admin credentials; live
post-deploy command and continuation evidence.`

The Control Tower is a role-aware operator BFF and projection UI. It has no
database, event ledger, retry policy, provider selection, or browser state
machine. `POST /api/v1/commands` accepts only the versioned allow-list and
forwards the validated envelope to an authenticated n8n webhook. n8n remains
the sole control plane; the Adapter remains the execution plane.

Project and issue projections are read from the existing n8n Data Tables and
run/attempt rows. When project tables are unavailable, the UI marks the
projection as `DERIVED`; it never creates a local fallback store. Blueprint
Markdown is parsed into an intent projection for validation and is forwarded
to the canonical workflow for durable repository persistence (`docs/blueprint.md`).

Operator and Admin are separate token roles. Operators may start/continue work,
control their run, approve gates, and exclude a model/provider for that run.
Only Admin may request diagnostics, catalog/credential operations, global
disablement, service controls, or release actions. Every accepted mutating
command gets a correlation ID and audit record without credentials.

Debugging reads correlated run/attempt and adapter events. Payloads are
redacted server-side: authorization material, credentials, cookies, private
keys, and reasoning content are never returned. `Anzeige pausieren` is a
frontend refresh preference and cannot send `PAUSE_RUN`.

## Required deployment configuration

Set `CONTROL_TOWER_OPERATOR_TOKEN`, `CONTROL_TOWER_ADMIN_TOKEN`, and
`MORPHEUS_COMMAND_TOKEN` as systemd credentials. Set the optional project,
issue, and event table IDs when those canonical Data Tables exist. The n8n
command webhook must validate `autodev.control-command.v1` and route each
allow-listed command into the canonical workflow; it must not execute shell
input or accept an arbitrary workflow ID.

The existing `MORPHEUS_RUNTIME_DASHBOARD_ACCESS=false` boundary remains
unchanged. Runtime builders continue to reject `dashboard/**` scope.

## Drift checklist

`DID_DASHBOARD_BECOME_CONTROL_PLANE=false`

`DID_DASHBOARD_GAIN_SECOND_SOR=false`

`DID_RUNTIME_GAIN_DASHBOARD_WRITE_ACCESS=false`

`DID_MODEL_ROUTER_BECOME_STATIC=false`

`DID_PAID_FALLBACK_APPEAR=false`

`DID_DEEPSEEK_RETURN=false`

`DID_DEBUGGING_STORE_REASONING_CONTENT=false`
