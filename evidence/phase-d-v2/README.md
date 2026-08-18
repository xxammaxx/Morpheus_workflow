# AutoDev Harness v2 — Phase-D-Evidenz

Stand: 2026-08-18 (Sitzung 2026-08-17/18)

## Ergebnis-Übersicht

| Suite | Ergebnis | Artefakt |
|---|---|---|
| Contract-Validierung + Fingerprints | 26/26 PASS | runtime/tests/test_contracts.py |
| Validator-Äquivalenz (Python ↔ JS) | 27/27 PASS | runtime/tests/test_validator_equivalence.py |
| Adapter-Suite (Smoke, Idempotenz, Fixtures, Timeout, Recovery, Callbacks, Parallelität) | 30/30 PASS | evidence/tests/v2/adapter_suite.py → adapter-suite-result.txt |
| Control-Plane-E2E-Matrix (alle Pfade, embedded Backend) | 9/9 PASS | evidence/tests/v2/control_plane_e2e.py → control-plane-e2e-result.txt |
| Reale LLM-Job-Kette (Adapter→Builder→OpenCode→LM Studio) | PASS (Job-Ebene) | debug-research-Job: 140 s, 3 306 Tokens, echte Research-Notiz |
| Realer Vertical Slice (E2E) | BLOCKED (Infrastruktur) | pve-SSHD-Ausfall + Builder-CT nicht erreichbar |

## Control-Plane-Matrix (9/9)

```
PASS E2E_INVALID_PLAN_GATE_REJECT      PLAN_BLOCKED / PLAN_RUN_ID_MISMATCH
PASS E2E_VERIFY_FAIL_NO_DELTA_SPLIT    SPLIT_REQUIRED / RETRY_DENIED_NO_STRATEGY_DELTA
PASS E2E_VERIFY_NO_SIGNATURE_SPLIT     SPLIT_REQUIRED / RETRY_DENIED_NO_FAILURE_SIGNATURE
PASS E2E_ATTEMPT_LIMIT_SPLIT           SPLIT_REQUIRED / RETRY_DENIED_ATTEMPT_LIMIT
PASS E2E_SECURITY_HARD_BLOCK           BLOCKED / BLOCKING_HIGH_OR_CRITICAL_FINDING
PASS E2E_REVIEW_SPLIT                  SPLIT_REQUIRED / REVIEW_REQUESTED_SPLIT
PASS E2E_HAPPY_PATH                    DONE / ALL_HARD_GATES_GREEN
PASS E2E_FIX_PATH                      DONE / ALL_HARD_GATES_GREEN  (Fix-Loop)
PASS E2E_REVIEW_FIX_PATH               DONE / ALL_HARD_GATES_GREEN  (Decision-Fix-Loop)
```

## Parallelitäts-Nachweise

- BATCH_PARALLELISM_OVERLAP: 3 embedded-Jobs (4 s) → 3/3 paarweise Überlappungen
  (Adapter-Suite).
- Reale Research-Batch (opencode): research.code 208 s, research.docs 208 s,
  research.tests 80 s bei parallelem Batch-Start — überlappende Laufzeiten in
  der Adapter-Ledger-Evidenz (run-msxow2cs, run-msxq3569).
- REVIEW-Batch: 3 parallele Review-Jobs (embedded, Fixture-Matrix) → Join mit
  `parallelism.overlap_proven` im Contract.

## Realer LLM-Beweis (Job-Ebene)

- Adapter-Job `debug-rs-001:research.code:1` (opencode-builder-8001):
  completed, 140 000 ms, Ergebnis enthält echte Research-Notiz des Modells
  (JSON mit `note`-Feld, 3 306 Tokens inkl. Reasoning).
- LM Studio: `huihui-qwen3.5-9b-abliterated`, Context 32 768, Server
  `--bind 0.0.0.0` (Port 1234).

## Infrastruktur-Blocker (Real-Slice)

- pve (192.168.1.136): sshd seit ~23:20 MESZ unerreichbar („Exceeded
  MaxStartups“ durch hängende pct-exec-Sitzungen), Web-UI 8006 down;
  Adapter v1/v2 (8080/8081) und n8n-CT (192.168.1.52) weiterhin erreichbar.
- Builder-CT 8001: pct exec hängt (CT nicht responsiv) → Adapter-Worker-Pool
  (6 Slots) durch hängende Jobs erschöpft; neue Jobs bleiben „queued“.
- Root-Cause-Kette: 3 parallele OpenCode-Runs (Node-Prozesse) überlasten den
  2-CPU-Canary-CT → CT hängt → pct exec/sshd-Pfade auf pve blockieren.
- Mitigation (implementiert, Deployment offen): Opencode-Jobs pro Backend
  serialisiert (`_opencode_sem`), Plan-JSON-Extraktion fence-aware,
  Modell huihui mit 32k Context, Context-Limit 32 768.
- Wiederanlauf-Rezept (wenn pve erreichbar): `pct reboot 8001`,
  `systemctl restart autodev-harness-v2`, dann Real-Slice erneut starten.
