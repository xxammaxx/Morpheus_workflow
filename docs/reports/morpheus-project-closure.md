# Morpheus project closure and release gate

Audit date: 2026-08-30
Scope: PR #56 closure correction after `MORPHEUS_RUN_LMSTUDIO_GPU_CORRELATION`
Classification: `AMBER_MORPHEUS_RELEASE_BLOCKED`

The correlation workstream is closed. This report is the current closure
record; older files under `evidence/` remain historical evidence and are not
rewritten.

## 1. Reality refresh and release history

```text
AUDIT_BASELINE_COMMIT= db0f9d000cf096e4d02e6ed2e915f03e612e1a81
ORIGIN_MAIN= db0f9d000cf096e4d02e6ed2e915f03e612e1a81
START_MAIN= db0f9d000cf096e4d02e6ed2e915f03e612e1a81
CLOSURE_PR= 56
CLOSURE_PR_HEAD= see PR #56 exact head at report publication
CLOSURE_PR_STATUS= OPEN
FINAL_MAIN= NOT_YET_MERGED
OPEN_PRS_AT_INITIAL_AUDIT= 0
OPEN_PRS= 1 (#56)
OPEN_ISSUES= 1 (#10)
LATEST_TAG= v1.1.2
LATEST_TAG_COMMIT= 16977b47683ff7d6db5a8e51be19752a34b909e0
GITHUB_RELEASES= none
COMMITS_SINCE_LATEST_TAG= 72
```

The checked-out branch initially pointed to the pre-merge PR #55 commit
`d175399…`; its tree was identical to `origin/main`. The closure branch was
then based directly on `origin/main`. No tag was moved and no release was
published.

The repository convention is the `vMAJOR.MINOR.PATCH` tag sequence
`v1.0.0 → v1.1.0 → v1.1.1 → v1.1.2`. The next candidate is `v1.2.0`: changes
since `v1.1.2` add project-centric Control Center behavior, runtime telemetry,
allow-listed operator command contracts, and the completed correlation
capability. This is a semantic minor release, not an arbitrary increment.

Current version references are intentional after closure alignment:

- Control Tower service build: `1.2.0`.
- Latest published Morpheus tag: `v1.1.2`.
- Proposed candidate: `v1.2.0`.
- Core V1 release: `v1.0.0`.
- Historical evidence mentioning V1.1.2 remains labelled historical.

## 2. Current architecture and production topology

The control-plane ownership is unchanged:

```mermaid
flowchart LR
  U[User / Operator] --> CT[Control Tower / API\nOBSERVABILITY + COMMAND FRONTEND]
  CT --> N8N[n8n\nSOLE CONTROL PLANE]
  N8N --> W[Canonical workflows\nData Tables: runs + attempts]
  W --> A[Harness Adapter\nEXECUTION PLANE]
  A --> OC[CT8001 / OpenCode\nCODING + TOOL HARNESS]
  OC --> R[Dynamic provider router]
  R --> M[Replaceable model worker]
  A --> N8N
  N8N --> CT
```

There is no browser-to-provider, browser-to-Proxmox, arbitrary-SSH, or
Dashboard-owned retry/state path. `autodev_runs` and `autodev_attempts` in
n8n Data Tables remain canonical. The Adapter ledger is execution telemetry,
not a second run-state authority.

The deployed topology observed by read-only probes is:

| Component | Location | Current evidence |
|---|---|---|
| Control Tower | `192.168.1.136:8092` | `/healthz` HTTP 200, version `1.2.0` |
| Harness Adapter v2 | `192.168.1.136:8081` | `/healthz` HTTP 200, version `2.0.0`, 0 running jobs |
| Harness Adapter v1 | `192.168.1.136:8080` | `/healthz` HTTP 200 |
| n8n | `192.168.1.52:5678` | `/healthz` HTTP 200 |
| OpenCode | CT8001 | proven by supplied acceptance run; no new model request issued |
| Proxmox / GPU telemetry | private LAN | proven by supplied acceptance run; read-only paths |
| LM Studio | optional local provider | proven by supplied acceptance run; not required for canonical health |

The public static dashboard assets (`index.html`, `app.js`, `styles.css`, and
the pinned Mermaid runtime) were exercised against the deployed service. The
closure PR also adds explicit Projekte/Datenfluss browser coverage and a
target allowlist in the BFF and canonical workflow generator. Deployment was
intentionally not performed; production therefore remains on the pre-PR
target-validation code until PR #56 is merged and separately deployed.

## 3. Data flow, project model, routing, and telemetry

```mermaid
flowchart TD
  P[Project] --> R1[Canonical run row\nautodev_runs]
  R1 --> A1[Attempt rows\nautodev_attempts]
  A1 --> E[Adapter / n8n evidence\ncontracts + provenance + telemetry]
  E --> PRJ[Control Tower read projection]
  PRJ --> UI[Overview / Projects / Runs / Debugging / Maps]
  R1 --> AB[ABORT_RUN]
  AB --> T[ABORTED terminal state]
  T -->|late callback rejected| R1
```

The project-to-run-to-attempt relationship is represented by canonical n8n
rows. Terminal `ABORTED` is authoritative; late callbacks cannot resurrect
the run, as covered by the workflow tests and the supplied acceptance run.

```mermaid
flowchart LR
  J[Canonical job] --> C[Refreshed OpenCode catalog]
  C --> F[Free-first eligibility]
  F --> K[Proven capabilities + health + auth + zero-cost evidence]
  K -->|eligible| L[OpenRouter / Groq free route]
  K -->|optional eligible local| O[Ollama / LM Studio]
  K -->|unknown / paid / DeepSeek| X[Fail closed]
  L --> Q[No automatic paid escalation]
  O --> Q
```

Unknown models fail closed. API providers need authentication and pricing
evidence; trusted local endpoints receive explicit local zero-cost evidence.
DeepSeek is ineligible, and paid fallback is disabled. The proven local model
classification remains:

```text
MODEL=llama-3.2-1b-instruct@q4_k_m
RESEARCH=true PLAN=false BUILD=false TOOL=false
```

The UI’s Mermaid topology and data-flow definitions are version-controlled in
`dashboard/static/app.js`; runtime values only select known static nodes and
are inserted as text. Mermaid is local, pinned, and hash-recorded in
`dashboard/static/vendor/mermaid/README.md`.

## 4. Closed correlation baseline

```text
AUDIT_BASELINE_COMMIT=db0f9d000cf096e4d02e6ed2e915f03e612e1a81
BASELINE_COMMIT=db0f9d000cf096e4d02e6ed2e915f03e612e1a81
BASELINE_CLASSIFICATION=GREEN_MORPHEUS_RUN_LMSTUDIO_GPU_CORRELATION_PROVEN
ROUTING=GREEN
OPENCODE_LMSTUDIO_PATH=GREEN
LOCAL_ZERO_COST_EVIDENCE=GREEN
GPU_OFFLOAD=GREEN
CONTROL_CENTER_LIVE_CORRELATION=GREEN
ACTIVE_TO_IDLE_TRANSITION=GREEN
BROWSER_QA=PASS fresh authenticated run, 5 viewports, all 8 views
SECURITY_GATES=GREEN
```

Acceptance evidence supplied for `run-mte031d2-tiioi7` records terminal
`ABORTED`, nonempty abort response, no late resurrection, no direct Data Table
edit, zero paid requests, and zero DeepSeek requests. The following are
frozen unless a new reproducible regression appears: model validation,
OpenCode/LM Studio seam, local auth separation, trusted zero-cost evidence,
catalog reconciliation, local health, Adapter lifecycle, Control Tower
execution-context projection, research correlation, GPU process recognition,
LM Studio ACTIVE→IDLE telemetry, and terminal abort behavior.

## 5. Gate results

| Gate | Result | Evidence |
|---|---|---|
| Repository clean | OK | clean at refresh; closure changes are scoped |
| Root tests | OK | `pytest -q`: 126 passed, 0 failed, 0 skipped |
| Dashboard / Control Tower tests | OK | 69 passed |
| Runtime / Adapter / Router tests | OK | 53 passed; targeted router/security subsets also pass |
| Script tests | OK | included in root suite; no separate script test target is defined |
| Contract tests | OK | `python3 runtime/tests/test_contracts.py`: 34/34 |
| Validator equivalence | OK | `python3 runtime/tests/test_validator_equivalence.py`: 34/34 |
| Workflow tests | OK | 6 passed; generated canonical workflows validate |
| Python compile check | OK | `python3 -m compileall -q adapter dashboard runtime scripts workflow evidence/tests` |
| Node check | OK | all repository JavaScript excluding pinned vendor bundle |
| Diff check | OK | `git diff --check` |
| Architecture sentinel | OK | builder dashboard boundary, read-only telemetry, and workflow ownership tests |
| Documentation / Mermaid gate | OK after closure alignment | current spec, operations docs, and report mirror implementation |
| Security tests / secret scan | OK in PR; deployed target guard pending | targeted security tests pass; tracked-file scan found no secret values |
| Governance gate | AMBER | PR #56 is open and requires exact-head authorization; Issue #10 is implemented but still open |

Fresh authenticated browser QA used the deployment's existing protected
viewer credential in-process. It covered Übersicht, Projekte, Läufe, Anbieter,
Systemkarte, Datenfluss, Debugging, and Administration at five configured
viewports. Result: `AUTHENTICATED_BROWSER_QA=PASS`,
`CONSOLE_ERRORS=0`, `HTTP_500_COUNT=0`, and
`HORIZONTAL_OVERFLOW=false`.

The live command path created a disposable canonical run through n8n and sent
one authenticated `ABORT_RUN` through the Control Tower BFF. The response was
nonempty, carried correlation ID `ct-280e9a5d71ba6a9f1187`, the canonical row
became `ABORTED`, and remained `ABORTED` after the late-callback window. The
deployed validator rejected unknown commands, unauthenticated requests,
missing CSRF, and operator use of admin commands. A valid command with an
arbitrary target key was accepted by the deployed pre-fix validator and then
rejected only as `RUN_NOT_FOUND`; this is the proven defect corrected by this
PR. Therefore target-denial is PASS in PR code but not yet a production claim.

## 6. Security closure

```text
N8N_SOLE_CONTROL_PLANE=true
SECOND_SOR=false
RUNTIME_DASHBOARD_WRITES=0
DEEPSEEK_ALLOWED=false
AUTOMATIC_PAID_ESCALATION=false
BROWSER_HAS_INFRA_SECRETS=false
PRIVATE_COT_STORAGE=false
REASONING_CONTENT_REDACTION=PASS
STRICT_HOST_KEY_CHECKING=PASS
GPU_READ_ONLY=true
PROXMOX_READ_ONLY=true
SECRET_SCAN=PASS
COMMAND_GATEWAY_AUTH=PASS
COMMAND_ALLOWLIST=PASS
ROLE_ENFORCEMENT=PASS
CSRF_PROTECTION=PASS
ARBITRARY_COMMAND_DENIED=PASS
ARBITRARY_TARGET_DENIED=PASS in PR code; NOT_YET_DEPLOYED in production
COMMAND_GATEWAY_LIVE_MUTATION=PASS
COMMAND_RESPONSE_NONEMPTY=PASS
COMMAND_CORRELATION_ID=PASS
N8N_STATE_MUTATION=PASS
FINAL_TEST_RUN_STATE=ABORTED
LATE_CALLBACK_RESURRECTION=false
```

The repository contains only credential-handling code and sanitized evidence
references under names that mention credentials; no key, token, bearer value,
private key, or password value is committed. Values were not printed.

## 7. Open work and debt

### Release blockers

- PR #56 must be merged and the corrected Control Tower/n8n command validators
  must be deployed before production can claim arbitrary-target denial.
- Exact-head authorization for PR #56 is required before merge. No merge,
  deployment, tag, or release was performed in this run.

### Important, non-blocking

- Re-run the authenticated browser and command-gateway gates after the PR is
  deployed; the current fresh evidence is pre-deployment for the target fix.
- Close or update GitHub Issue #10 under normal project policy. Its map
  acceptance criteria are implemented by PR #11 and the later correlation
  work in PR #55; the original five-item navigation wording was superseded by
  the current eight-view Control Center navigation.
- Keep the many merged remote feature branches as provenance until the
  repository owner chooses a branch-retention policy; none was deleted.

### Optional enhancements

- Adapter production hardening (stronger HTTP serving, TLS/IP policy, token
  rotation) already listed as a V1 limitation.
- Repeatable authenticated browser-QA tooling in release automation.
- LLM-backed reviews after a separate capability and governance decision.

### Historical / stale material

Older V1/V2 closure reports, DeepSeek HAMH research, backups, screenshots, and
early release-lineage notes remain historical artifacts. They are not current
runtime policy and should not be used to reopen the closed LM Studio workstream.

## 8. Open PR / issue triage

```text
OPEN_PRS_AT_INITIAL_AUDIT=0
OPEN_ISSUES=1
ISSUE_10=DONE (implemented; left open for owner-controlled closure)
PR_56=OPEN; current closure branch contains the correction and awaits exact-head authorization
```

The historical `OPEN_PRS=0` value above is not current; it is retained only as
the initial-audit snapshot and is superseded by `OPEN_PRS=1 (#56)` in the
reality-refresh block. PR #56 is the focused closure correction and remains
open. The implementation provenance is issue #10 → PR #11 (maps) → PR #42 (project
Control Center) → PRs #54/#55 (live correlation) → current tests and supplied
acceptance run.

## 9. Release decision and publication boundary

```text
RELEASE_DECISION=AMBER_RELEASE_BLOCKED
CURRENT_RELEASE=v1.1.2
PROPOSED_NEXT_RELEASE=v1.2.0
RELEASE_PUBLICATION_READY=false
RELEASE_TAG_PROPOSED=v1.2.0
RELEASE_COMMIT=NOT_CREATED
PR_MERGED=false
RELEASE_CREATED=false
```

No Git tag, GitHub Release, or release artifact was created. The candidate
has fresh browser and live abort evidence, but production publication also
requires the PR #56 target-boundary correction to be merged and deployed.
Owner authorization remains a separate publication requirement.

## 10. Next milestone

### 1. Canonical project continuation and command-gateway operational proof

`WHY_NOW=` The Control Center’s project model and allow-listed command
contract are implemented, while the deployed command path and continuation
evidence remain the clearest operational gap.
`USER_VALUE=` Complete project-to-issue-to-run operation from the Morpheus
Control Center with durable n8n ownership.
`DEPENDENCIES=` Authenticated n8n command gateway, project/issue Data Tables,
operator/admin credentials, and read-only then controlled mutation acceptance
tests.
`RISKS=` Accidental second control plane or unbounded command surface if the
n8n contract is not kept strict.
`ESTIMATED_SCOPE=MEDIUM`
`RECOMMENDED=YES`

### 2. Adapter operational hardening and recovery runbook

`WHY_NOW=` The execution boundary is proven but documented V1 limitations
remain around serving hardening, rotation, and operator recovery.
`USER_VALUE=` More predictable service recovery and lower operational risk.
`DEPENDENCIES=` Deployment owner decision on TLS/IP policy, rotation process,
and recovery drill environment.
`RISKS=` Infrastructure changes can affect the frozen execution path.
`ESTIMATED_SCOPE=MEDIUM`
`RECOMMENDED=NO`

### 3. Deterministic release-evidence automation

`WHY_NOW=` Release confidence currently depends on manually supplied browser
credentials and historical visual evidence.
`USER_VALUE=` Repeatable closure reports with fresh browser, health, and
provenance evidence.
`DEPENDENCIES=` Safe secret injection for viewer QA, repository CI policy, and
an explicit release publication workflow.
`RISKS=` Automation must remain read-only until owner-authorized publication;
it must not create a second source of truth.
`ESTIMATED_SCOPE=SMALL`
`RECOMMENDED=NO`

```text
NEXT_RECOMMENDED_MILESTONE=Canonical project continuation and command-gateway operational proof
KNOWN_BLOCKERS=PR #56 target-boundary correction is not yet merged/deployed; no LM Studio or correlation blocker
USER_ACTION_REQUIRED=EXACT_HEAD_AUTHORIZATION_FOR_PR_56
```
