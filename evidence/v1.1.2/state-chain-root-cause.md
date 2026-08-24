# Root Cause

The pre-hotfix generated orchestrator restored Build directly into Verify
dispatch without writing `VERIFYING`, and the review-to-decision route lacked
`DECIDING`. The retry path also lacked a terminal attempt-limit guard.

The canonical generator now emits Verify and Decision state prep/update/restore
nodes and an idempotent retry guard. Generated JSON was regenerated and the
affected workflow was deployed with its existing ID and activation state.
