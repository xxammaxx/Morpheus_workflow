# HAMH Real Testing — Rollback Proof

Datum: 2026-08-21 (Run: HAMH_REAL_TESTING)

## §35 — Rollback LIVE (Kopie der Produktions-Registry, echte Fingerprints)

Ausgeführt auf dem Produktions-Host (192.168.1.136) gegen eine Kopie der
PRODUKTIONS-Registry (state/registry.json), damit die Fingerprints exakt
die Produktions-Fingerprints sind. Der kontrollierte Pfad:
ACTIVE A -> authorized candidate activation -> ROLLBACK -> ACTIVE A.

```
ACTIVE_BEFORE:              [hamh/baseline/deepseek-v4-flash/build/thinking/v1]
FINGERPRINT_BEFORE:         ea502fbbc38488680cb020be...
PROMOTE (authorized):       True
ACTIVE_AFTER_ACTIVATION:    [hamh/candidate/build/precision-edit/v1]
ROLLBACK:                   True -> restored hamh/baseline/deepseek-v4-flash/build/thinking/v1
ACTIVE_AFTER_ROLLBACK:      [hamh/baseline/deepseek-v4-flash/build/thinking/v1]
FINGERPRINT_MATCH:          True (ea502fbbc38488680cb020be == ea502fbbc38488680cb020be)
```

ROLLBACK_PROOF = PASS

## §10 — Rollback-Pfad-Verifikation (Sandbox, vor Deployment)

Bereits vor dem Deployment verifiziert (Sandbox-Registry): PROMOTE ->
ROLLBACK -> exakter Zustand + Fingerprint-Match.

## Governance-Status

- Baseline: ACTIVE (unverändert)
- Candidate hamh/candidate/build/precision-edit/v1: REJECTED
  (PILOT_REJECTED — kein Holdout, kein Shadow, kein Canary; Self-Promotion
  war zu keinem Zeitpunkt möglich: EVOLVER_CAN_PROMOTE=NO, Promotion nur
  mit Operator-Authority aus /var/lib/autodev-harness-v2/api-token)
- Rollback-Skript: /opt/dev-fabric/hamh/rollback_hamh.sh (Service-Stop +
  Layer-Entfernung, reversibel)
