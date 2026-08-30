# Control Center command surface

The browser submits commands only to the Control Tower BFF. The BFF validates
the allow-list and forwards the envelope to the canonical n8n control gateway.

| UI action | Command | BFF | n8n canonical action | Status |
| --- | --- | --- | --- | --- |
| New issue | `START_ISSUE` | `/api/v1/commands` | Issue fetch → canonical start | IMPLEMENTED |
| Repository analysis | `START_REPO_ANALYSIS` | `/api/v1/commands` | GitHub issue read → analysis webhook | IMPLEMENTED |
| Blueprint/project | `START_BLUEPRINT_PROJECT`, `START_PROJECT` | `/api/v1/commands` | Blueprint bootstrap webhook | IMPLEMENTED |
| Continue project across runs | `RESUME_RUN` | `/api/v1/commands` | Read project/run/issue history → reassessment → new canonical start | IMPLEMENTED |
| Pause/abort/retry/gate | `PAUSE_RUN`, `ABORT_RUN`, `RETRY_STAGE`, `RETRY_RUN`, `APPROVE_HUMAN_GATE` | `/api/v1/commands` | Run state/action upsert | IMPLEMENTED |
| Exclude route | `EXCLUDE_MODEL_FOR_RUN`, `EXCLUDE_PROVIDER_FOR_RUN` | `/api/v1/commands` | Run exclusion state/action upsert | IMPLEMENTED |
| Router diagnostic | `RUN_ROUTER_TEST` | `/api/v1/commands` | Named adapter-backed diagnostic | IMPLEMENTED |
| MCP diagnostic | `RUN_MCP_TEST` | `/api/v1/commands` | Named configured-server discovery/test | IMPLEMENTED |
| System diagnostic | `RUN_SYSTEM_TEST` | `/api/v1/commands` | Required/optional aggregation | IMPLEMENTED |
| Refresh catalog | `REFRESH_CATALOG` | `/api/v1/commands` | n8n → authenticated adapter refresh | IMPLEMENTED |
| Credential sync | `SYNC_CREDENTIALS` | `/api/v1/commands` | n8n → authenticated adapter sync | IMPLEMENTED |
| Restart/global enable-disable/deploy | — | rejected and not rendered | — | NOT_EXPOSED |

There is no enabled UI action whose canonical path returns
`COMMAND_NOT_IMPLEMENTED`. Deferred infrastructure mutations are deliberately
not in the command contract or UI.

`RESUME_RUN` is the versioned continuation contract, not an in-place terminal
run restart. It requires an existing `project_id`, terminal `source_run_id`,
bounded `continuation_reason` and `requested_action`, and may carry one
existing `issue_number`. n8n rejects an active project run, unknown project or
issue, and replayed continuation correlation before creating a new run. The
new run ID is derived in n8n from the bounded tuple `(project_id,
source_run_id, correlation_id)`, rather than correlation alone. `00 AutoDev
API Start` preflights an existing requested run ID: only an exact continuation
replay may reuse it; a project/source/correlation ownership mismatch fails
closed as `RUN_ID_OWNERSHIP_CONFLICT` before Data Table upsert.
