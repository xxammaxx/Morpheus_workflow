# Morpheus Control Tower — Playwright Acceptance

Date: 2026-08-31

## Result

The test ran with Python Playwright against the deployed Control Tower and
live API/runtime sources, not a fixture or mocked backend:

```text
PLAYWRIGHT_REAL_RUNTIME=PASS
CONTROL_TOWER_URL=http://192.168.1.136:8092
CONTROL_TOWER_VERSION=1.2.0
TESTED_LOCAL_CODE_HEAD=5f7089acfb73d83e92c1451fa37cba25ec1955fa
PLAYWRIGHT_VERSION=1.57.0
BROWSER=Chromium 143.0.7499.4
VIEWPORTS=1440x900;1280x800;768x1024;390x844;360x800
```

All currently rendered main views were navigated by a real browser:

```text
overview;projects;runs;providers;system-map;data-flow;debugging;administration
```

Navigation was visible, clickable, and keyboard-focusable. The page declared
German language metadata, local Mermaid rendered both diagrams, and the
fallbacks remained hidden. Projects, run lists, run details, provider data,
system health, telemetry/debugging projections, timestamps, IDs, and live
polling were loaded from the deployed BFF.

## Gates passed

```text
AUTH_GATE=PASS
CSRF_GATE=PASS
ARBITRARY_COMMAND_GATE=PASS
ARBITRARY_TARGET_GATE=PASS
CONSOLE_ERRORS=0
UNHANDLED_REJECTIONS=0
HTTP_500_COUNT=0
FAILED_STATIC_ASSETS=0
PAGE_HORIZONTAL_OVERFLOW=0
ACCESSIBILITY_BASELINE=PASS
RESPONSIVE_GATE=PASS
BROWSER_SECRET_LEAK_GATE=PASS
PRIVATE_REASONING_LEAK_GATE=PASS
LIVE_REFRESH=PASS
DUPLICATE_CLICK_GATE=PASS
```

The duplicate-click check used the visible `RUN_ROUTER_TEST` button. A rapid
double click produced exactly one observed `202` command response. The
command was a read-only router test; it did not mutate a run and therefore is
not claimed as a disposable `ABORT_RUN` mutation proof.

The browser used the existing admin credential only through stdin. No token
was printed, committed, embedded in a screenshot/report, or placed in a
browser request other than the intended Control Tower authentication header.
No upstream provider, n8n, Proxmox, LM Studio, or private-reasoning content
was exposed in the tested DOM/request-header patterns.

## Runtime correlation

The Control Tower debugging view returned `LIVE` correlated adapter events for
the controlled adapter smoke IDs. The normal overview and runs projections
also agreed with each other and supported run-detail navigation. The stronger
three-way equality was not proven because the direct adapter smoke IDs were
not present in the overview's canonical n8n run list:

```text
ADAPTER_TO_CONTROL_TOWER_DEBUGGING=PASS
CONTROL_TOWER_RUN_PROJECTION_CORRELATION=PASS
BENCHMARK_RUN_ID == CONTROL_TOWER_RUN_ID == N8N_CANONICAL_RUN_ID=NOT_PROVEN
CONTROL_TOWER_RUN_CORRELATION=PARTIAL
```

No safe disposable canonical run was available for this acceptance window.
Consequently continuation UI, valid canonical continuation, abort terminality,
late-callback handling, and a mutating command round trip were not invoked on
production work:

```text
CONTROL_TOWER_CONTINUATION_UI=NOT_PROVEN
CONTROL_TOWER_COMMAND_E2E=READ_ONLY_202_PASS
MUTATING_COMMAND_E2E=NOT_PROVEN
ABORT_TERMINALITY=NOT_RUN
```

## Role and security boundary

The deployed credential mapping exposed the following roles:

```text
viewer_token=OPERATOR
operator_token=OPERATOR
admin_token=ADMIN
```

This is a deployment/configuration defect, not an authorization bypass made
by the test. The test verified that the observed operator token could not run
an admin command, while admin authentication succeeded. Because the existing
viewer reference resolves to `OPERATOR`, the required viewer read-only gate is
not green:

```text
ROLE_GATE=FAIL
VIEWER_CANNOT_MUTATE=NOT_PROVEN
OPERATOR_ADMIN_GATE=PASS
CSRF_GATE=PASS
```

No credential was disabled, replaced, generated, or committed. The required
remediation is to correct the existing deployment's role-to-token references
through the authorized owner/deployment process, then rerun this exact suite.

## Accessibility and responsive notes

The browser checked named interactive controls, semantic button/input/select
usage, focus movement for main navigation, `lang=de`, local diagrams, and
viewport-level horizontal overflow. No page-level overflow or clipped primary
navigation was detected at the five required viewports. Diagram internals are
allowed to use their existing bounded scrolling behavior. A full axe audit
was not added because no existing axe integration was present.

## Final browser classification

```text
CONTROL_TOWER_OPERATIONAL_ACCEPTANCE=AMBER
FINAL_BROWSER_CLASSIFICATION=AMBER_CONTROL_TOWER_ROLE_GATE_AND_CANONICAL_MUTATION_NOT_PROVEN
KNOWN_DEGRADATION=LM_STUDIO_AUTH_REQUIRED_OR_UNREACHABLE;OLLAMA_UNREACHABLE
SECOND_SOURCE_OF_TRUTH=false
CONTROL_TOWER_DIRECT_DB_WRITES=0
N8N_SOLE_CONTROL_PLANE=true
```

The browser result is real-runtime evidence with strong read-only and
security-gate coverage. It is not a false green: role separation and a safe
canonical mutating command correlation remain explicitly open.

## Current superseding acceptance — 2026-08-31

After the independent Role-Gate fix (PR #62), the same real-runtime suite was
rerun with the existing viewer, operator, and admin credentials. The operator
credential now comes from a dedicated protected file; no admin credential was
changed.

```text
PLAYWRIGHT_REAL_RUNTIME=PASS
CONTROL_TOWER_VERSION=1.2.0
PLAYWRIGHT_VERSION=1.57.0
PLAYWRIGHT_BROWSER=Chromium 143.0.7499.4
PLAYWRIGHT_VIEWPORTS=1440x900;1280x800;768x1024;390x844;360x800
CONTROL_TOWER_MAIN_VIEWS=8_PASS
ROLE_GATE=PASS
VIEWER_READ=PASS
VIEWER_MUTATION=DENY
OPERATOR_ALLOWLISTED_COMMAND=PASS_READ_ONLY_DIAGNOSTIC
OPERATOR_ADMIN_COMMAND=DENY
AUTH_GATE=PASS
CSRF_GATE=PASS
ARBITRARY_COMMAND_GATE=PASS
ARBITRARY_TARGET_GATE=PASS
LIVE_REFRESH=PASS
DUPLICATE_CLICK_GATE=PASS
CONSOLE_ERRORS=0
HTTP_500_COUNT=0
PAGE_HORIZONTAL_OVERFLOW=0
ACCESSIBILITY_BASELINE=PASS
RESPONSIVE_GATE=PASS
BROWSER_SECRET_LEAK_GATE=PASS
PRIVATE_REASONING_LEAK_GATE=PASS
```

The canonical disposable run `run-mthenxhx-qvim85` was visible in the Control
Tower and selected as the tracked run. Its ID matched the n8n canonical row;
the run terminal state was `PLAN_BLOCKED / CONTRACT_FAILURE`, so this is a
correlation and negative-state proof, not a successful mutating command proof.
The visible duplicate-click check remained the existing read-only router
diagnostic and returned one `202`; no `ABORT_RUN` was invoked because the
canonical run was already terminal and no safe disposable mutation path was
available.

```text
CONTROL_TOWER_RUN_CORRELATION=PASS_FOR_DISPLAYED_CANONICAL_RUN
CANONICAL_N8N_BENCHMARK_CORRELATION=PARTIAL
CONTROL_TOWER_COMMAND_E2E=READ_ONLY_202_PASS
MUTATING_COMMAND_E2E=NOT_PROVEN
CONTROL_TOWER_OPERATIONAL_ACCEPTANCE=AMBER
```

## Current real-runtime acceptance — 2026-08-31

The acceptance suite was rerun against the live Control Tower after the
read-only adaptive metadata projection was deployed. It covered the current
eight views at `1440x900`, `1280x800`, `768x1024`, `390x844`, and `360x800`.

```text
PLAYWRIGHT_REAL_RUNTIME=PASS
PLAYWRIGHT_VERSION=1.57.0
PLAYWRIGHT_BROWSER=Chromium 143.0.7499.4
ROLE_GATE=PASS
AUTH_GATE=PASS
CSRF_GATE=PASS
RUN_CORRELATION=PASS
LIVE_REFRESH=PASS
DUPLICATE_CLICK_GATE=PASS
CONSOLE_ERRORS=0
HTTP_500_COUNT=0
PAGE_HORIZONTAL_OVERFLOW=0
RESPONSIVE_GATE=PASS
ACCESSIBILITY_BASELINE=PASS
BROWSER_SECRET_LEAK_GATE=PASS
PRIVATE_REASONING_LEAK_GATE=PASS
CONTROL_TOWER_MUTATING_E2E=NOT_PROVEN_PLAYWRIGHT_ABORT
CONTROL_TOWER_OPERATIONAL_ACCEPTANCE=GREEN
```

The browser tracked the disposable canonical run `run-mthmymeg-1z6039`, whose
terminal state was `DONE`; the Control Tower detail exposed its experiment,
factor, split, config hash, task-set hash, and harness version. The prior
provider-latency run was aborted once through the allow-listed canonical
`ABORT_RUN` API path and is not used as value evidence. The safe mutation was
therefore proven through the real BFF/n8n API chain, but not through a
Playwright UI-triggered abort followed by a UI-state assertion. The browser's
double-click gate covered the existing allow-listed router diagnostic and
returned one `202`. Full Playwright output is
in [`acceptance-20260831-plan-recovery.json`](../../evidence/playwright/control-tower/acceptance-20260831-plan-recovery.json).
