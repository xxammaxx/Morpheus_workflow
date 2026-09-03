# Deployment provenance

`autodev.deployment-provenance.v1` is the single operational attestation for
the deployed Morpheus runtime. `scripts/deployment_provenance.py attest`
reads source files from an immutable Git commit, compares their hashes with
the declared host paths, compares all canonical n8n workflow exports using a
deterministic semantic normalization, checks required services, validates the
candidate, and atomically writes the root-owned record at
`/var/lib/autodev-harness-v2/deployment-provenance.json`. Reconciliation uses
the same complete verification and does not redeploy or trust a requested SHA.

The canonical reader is `scripts/deployment_provenance.py read`. The legacy
`deployed-integration-head` files are deprecated and non-authoritative. This
record is operational evidence only; it is not run/task state, provider
routing, benchmark state, or a second source of truth. n8n remains the sole
control plane and `autodev_runs`/`autodev_attempts` remain the canonical run
state.
