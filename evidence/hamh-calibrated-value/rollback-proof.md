# HAMH Calibrated Value — Rollback-Proof

Datum: 2026-08-21 (Run: HAMH_CALIBRATED_VALUE)

## Status

KEIN Rollback erforderlich — es wurde KEINE Promotion durchgeführt und KEINE
Registry-/Resolver-/Runtime-Änderung vorgenommen.

## Interventions-Ebene

Die Candidate-Intervention (edit-early-Policy) wurde AUSSCHLIESSLICH als
Zusatz-Prompt-Datei appliziert:

```
evidence/hamh-calibrated-value/candidate-prompt-edit-early.txt
```

Sie wurde per `--candidate-prompt-file` an opencode-Runs übergeben und
wirkt NUR innerhalb der Bedingungs-Runs (B). Kein Eingriff in:
- runtime/hamh/** (Registry, Resolver, Adapter, Evolution, Profile)
- /opt/dev-fabric/hamh/state/registry.json (Produktionshost)
- opencode-Konfiguration
- n8n-/Job-Server-Pfade

## Verifikation

| Prüfung | Ergebnis |
|---|---|
| ACTIVE-Fingerprint Registry | a1e6955f… (unverändert, live per /v1/resolve verifiziert) |
| Resolver healthz | OK (192.168.1.136:8090) |
| Registry-Datei mtime | vor Run-Zeitraum (kein Schreibzugriff ausgeführt) |
| Bedingungs-Runs B | nur mit --candidate-prompt-file; ohne Datei = Baseline-Verhalten (bewiesen durch A-Runs) |
| restored_fingerprint == previous_active_fingerprint | nicht anwendbar (keine Promotion) — Registry-Zustand identisch vor/nach Run |

## Fazit

Rückweg zur reinen Baseline ist strukturell garantiert: Datei entfernen bzw.
--candidate-prompt-file weglassen. De-facto-Rollback unnötig, da nie aktiviert.
