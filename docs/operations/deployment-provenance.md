# Deployment provenance

`autodev.deployment-provenance.v1` is the single operational attestation for
the deployed Morpheus runtime. `scripts/deployment_provenance.py attest`
reads source files and the declared workflow set from immutable Git objects,
compares their hashes with the declared host paths, fetches complete live n8n
workflow definitions, applies one deterministic semantic normalization to
source and live objects, checks required services and workflow activation,
validates the candidate, and atomically writes the root-owned record at
`/var/lib/autodev-harness-v2/deployment-provenance.json`. Reconciliation uses
the same complete verification and does not redeploy or trust a requested SHA.

Workflow `active` is intentionally excluded from semantic content because the
repository exports do not contain instance activation state. It is verified as
an explicit separate operational gate: every declared workflow must be active.
Nested ids remain semantic, including node, credential, and workflow-reference
identities; only known top-level n8n instance metadata is excluded.

The canonical reader is `scripts/deployment_provenance.py read`. The legacy
`deployed-integration-head` files are deprecated and non-authoritative. This
record is operational evidence only; it is not run/task state, provider
routing, benchmark state, or a second source of truth. n8n remains the sole
control plane and `autodev_runs`/`autodev_attempts` remain the canonical run
state.
