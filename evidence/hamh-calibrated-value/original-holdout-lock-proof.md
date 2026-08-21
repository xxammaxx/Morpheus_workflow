# HAMH Calibrated Value — Original-Holdout-Lock-Proof

Datum: 2026-08-21 (Run: HAMH_CALIBRATED_VALUE)

## Status

Der Original-Holdout (24 versiegelte Tasks aus HAMH_REAL_TESTING) blieb
während des GESAMTEN Runs versiegelt:

- NICHT geöffnet
- NICHT inspiziert (keine Task-Inhalte in diesem Run gelesen oder ausgewertet)
- NICHT zur Kalibrierung verwendet
- NICHT zur Candidate-Erzeugung oder -Bewertung verwendet
- KEINE A/B/C-Runs auf diesen Tasks

## Nachweis

| Prüfung | Wert |
|---|---|
| Manifest vorhanden | evidence/hamh-real-testing/holdout/eval-split-manifest.json |
| sealed-Flag im Manifest | true |
| Task-Anzahl | 24 (ho-001 .. ho-024) |
| SHA256-Hashes der Tasks | im Manifest (nicht verändert — git status zeigt keine Modifikation) |
| Git-Status Holdout-Verzeichnis | unverändert (siehe git diff --stat) |
| Runs auf ho-* | 0 (keine Run-JSON mit ho-* Präfix in results/runs/) |
| Gate-Ergebnis | Development-Gate FAILED → Holdout bleibt gesperrt (order §29/§33) |

## Konsequenz

Der Original-Holdout bleibt für die ZUKUNFT als externe
Generalisierungsprüfung verfügbar. Ein künftiger Kandidat muss ihn als
letzte Prüfstufe (order §33-§34) verwenden.
