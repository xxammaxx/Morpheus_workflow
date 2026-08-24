# Control Tower visual QA

Required browser matrix: 1440x900, 1280x720, 390x844, and 360x800.

Checks: login/token screen, overview, run list, Golden Journey detail, Failure
Recovery detail, provider pool, keyboard focus, mobile layout, no horizontal
overflow, no console errors, no network 500s, and reduced-motion behavior.

```text
VISUAL_QA=PASS
VIEWPORTS=4
CONSOLE_ERRORS=0
HTTP_500=0
NO_HORIZONTAL_OVERFLOW=PASS
GOLDEN_JOURNEY_DETAIL=PASS
FAILURE_RECOVERY_DETAIL=PASS
```
