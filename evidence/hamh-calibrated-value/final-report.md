# HAMH Calibrated Value Discovery — Final Report

Datum: 2026-08-21 (Run: HAMH_CALIBRATED_VALUE)
Autor: Issue-Orchestrator (evidence-gated, keine Mocks, keine Secrets)

## FINAL_CLASSIFICATION

```
GREEN_HAMH_CALIBRATED_EVAL_FOUNDATION_PROVEN
HAMH_CANDIDATE_REJECTED
AMBER_HAMH_VALUE_NOT_PROVEN
```

Begründung: Kalibrierte Task-Population (23 Tasks), eingefrorene Splits,
67 Baseline-Trajektorien, formales Weakness-Mining, genau EIN Kandidat
(edit-early), A/B/C mit Matched-Compute auf Development. Der Kandidat
überlebt die Matched-Compute-Kontrolle nicht (B = C = 2/3 auf t-008,
paired Ties 3/3) → abgelehnt. Der einzige reproduzierbare Baseline-Fehler
(research_loop_no_edit, 0 % auf t-008) ist compute-sensitiv, nicht
policy-spezifisch behebbar.

## Abschlussreport (order §43)

```
FINAL_CLASSIFICATION=AMBER_HAMH_VALUE_NOT_PROVEN
  (GREEN_HAMH_CALIBRATED_EVAL_FOUNDATION_PROVEN + HAMH_CANDIDATE_REJECTED)

START_HEAD=f7caeedd1447712e3879b8c8973a811de19368f7
END_HEAD=<siehe git log nach Commit>

PRODUCTION_BASELINE=unverändert: AutoDev-Harness v2 Chain + HAMH-Resolver
  (192.168.1.136:8090, ACTIVE hamh/baseline/deepseek-v4-flash/build/thinking/v1,
  Fingerprint a1e6955f…, live verifiziert)

INFRA_PREFLIGHT=PASS mit dokumentierter Abweichung: Workstation GREEN
  (Disk 46 %, Inodes 8 %, RAM 5.0G); pve-root 100 % voll →
  BLOCK_HAMH_EXPERIMENT für Host-SCHREIBoperationen (keine Registry-Writes
  ausgeführt, keine Produktionsdaten gelöscht; Eval-Pfad entkoppelt)
DISK_FREE_START=481G (Workstation /)
DISK_FREE_END=480G (Workstation / — keine Eval-bedingte Veränderung)

BASELINE_MODEL=deepseek-v4-flash
BASELINE_MODEL_REVISION=0731
BASELINE_HARNESS_ID=hamh/baseline/deepseek-v4-flash/build/thinking/v1
BASELINE_FINGERPRINT=a1e6955fa0f1aadf099a331f7c34d6068445fa221ef82827c459d07e15625271
BASELINE_RUNTIME_REVISION=opencode-1.15.13 (Abweichung zu 1.17.9 im Vorgänger-Run,
  als Teil der Baseline eingefroren und dokumentiert)

CALIBRATION_TASK_COUNT=23
EASY_TASKS=22 (beobachtet 100 %: t-001..t-007, t-009..t-020, t-021..t-023)
MEDIUM_TASKS=0 (beobachtet)
HARD_TASKS=0 (beobachtet)
CAPABILITY_BOUNDARY_TASKS=1 (t-008, beobachtet 0 %)

DEVELOPMENT_SIZE=4 (t-008, t-021, t-022, t-023)
VALIDATION_SIZE=8 (t-001, t-002, t-015..t-020)
NEW_HOLDOUT_SIZE=11 (t-003..t-007, t-009..t-014; SEALED, nie geöffnet)
ORIGINAL_HOLDOUT_SIZE=24
ORIGINAL_HOLDOUT_REMAINED_SEALED_UNTIL_GATE=JA (Lock-Proof, 0 Runs auf ho-*)

BASELINE_TRAJECTORY_COUNT=67 (alle harness=a, FROZEN)
VERIFIED_SUCCESS_BASELINE=0.9552 (64/67; 22/23 Tasks bei 100 %)
HARNESS_RECOVERABLE_SUCCESS_BASELINE=n/a — 0 Tasks in der Zielzone 20-90 %;
  einziger Fehlschlag-Task t-008: 0.0

WEAKNESS_PATTERN=research_loop_no_edit (Agent recherchiert endlos, 0 Edits,
  Timeout) + excessive_pytest_loops/excessive_tool_calls/dup-reads (harmlos,
  korrelieren mit Erfolg)
WEAKNESS_RUN_COUNT=3 (t-008, 3/3 Runs reproduzierbar)
WEAKNESS_DISTINCT_TASK_COUNT=1 (t-008; Gegenprobe t-021/022/023 gleiche
  Fehlerklasse bei 100 % gelöst → Capability vorhanden, nicht extrahiert)

CANDIDATE_JUSTIFIED=JA (MIN_EVIDENCE_RUNS=2 übertroffen: 3 Runs; Cross-Task
  nicht erfüllt — dokumentiert)
CANDIDATE_ID=hamh/candidate/build/edit-early/v1
CANDIDATE_COMPONENT=prompt/editing-protocol (edit-early hypothesis testing)
CANDIDATE_FINGERPRINT=f1b34868fccc99cc3d118b570e14782c782e6250abbcee914821137512ff5117

PREVIOUS_REJECTED_CANDIDATE_REUSED=NEIN (precision-edit in Rejected-History
  persistiert; edit-early zielt auf andere kausale Stelle: Edit-Initiierung)
```

Dann:

```
DEVELOPMENT_A=0/3 (alle Timeout, 0 Edits)
DEVELOPMENT_B=2/3 (1 Edit je Erfolg, 251-404 s)
DEVELOPMENT_C=2/3 (1-3 Edits, matched compute)

VALIDATION_A=N/A  VALIDATION_B=N/A  VALIDATION_C=N/A
  (NOT_RUN — Development-Gate gescheitert, order §29)

NEW_HOLDOUT_A=N/A  NEW_HOLDOUT_B=N/A  NEW_HOLDOUT_C=N/A
  (NOT_OPENED — bleibt versiegelt)

EXTERNAL_HOLDOUT_A=N/A  EXTERNAL_HOLDOUT_B=N/A  EXTERNAL_HOLDOUT_C=N/A
  (NOT_OPENED — 24er-Holdout bleibt versiegelt)

MATCHED_COMPUTE_EXPLAINS_GAIN=JA
  (B 0.667 == C 0.667; paired B-vs-C: 0 Wins, 0 Losses, 3 Ties;
  C editiert nativ mehr ohne Policy: mean 2.0 vs 0.7 Edits)

VERIFIED_SUCCESS_DELTA=+0.667 (B vs A auf t-008) — vollständig durch C erklärt
HARNESS_RECOVERABLE_SUCCESS_DELTA=n/a (Zone leer)

COST_PER_VERIFIED_SUCCESS_DELTA=B $0.013802 vs C $0.016452 vs A n/a
  (B nicht wirtschaftlicher als C bei gleichem Success)
LATENCY_DELTA=A 480s (Timeout) / B 378s / C 449s mean
RETRY_DELTA=kein messbarer Unterschied (pytest-Loops B 1-2, C 2)
TOOL_STEP_DELTA=B 13.7 vs C 17.7 mean (C mehr Tools ohne Policy)

CANDIDATE_DECISION=CANDIDATE_REJECTED (Matched-Compute-Kontrolle nicht
  überlebt; kein Holdout verbraucht)

SHADOW=NOT_RUN
CANARY=NOT_RUN
PROMOTION=NOT_RUN (Registry unverändert, ACTIVE bleibt Baseline)
ROLLBACK_PROOF=erforderlich? NEIN — keine Promotion; Intervention nur
  Prompt-Ebene (--candidate-prompt-file); Registry-Fingerprint vor/nach
  identisch (live verifiziert); de-facto-Rückweg = Datei weglassen

POST_RUN_REGRESSION=PASS (285/285 lokale HAMH-Tests: Registry 22, Resolver 14,
  DeepSeek-Adapter 52, Evolution 31, Telemetry 29, Capability-vs-Harness 11,
  Isolation 14, Adapter-Seam 20, Contracts 34, Validator-Equivalence 34,
  Task-Suite 24; Live-Suiten Control-Plane/Adapter auf Workstation nicht
  ausführbar — Secrets/Infra auf pve, Callback-Sink offline; KEINE
  Komponenten-Änderungen in diesem Run)

TOTAL_PROVIDER_COST=~$0.23 (76 Runs; Budget MAX_EXTERNAL_API_COST=10 USD;
  Deckel deutlich unterschritten)
```

## Weitere Pflichtfelder

```
FILES_CHANGED=evidence/hamh-calibrated-value/** (reality-refresh, infra-preflight,
  calibration-task-pool.json, calibration-results.json, development/validation/
  new-holdout/external-holdout-Manifeste, original-holdout-lock-proof,
  baseline-fingerprint, baseline-trajectory-summary, weakness-analysis,
  rejected-candidates, candidate-hypothesis, candidate-fingerprint,
  candidate-prompt-edit-early, development-abc-results, matched-compute-analysis,
  promotion-or-rejection, rollback-proof, final-report, fixtures/pool/t-001..t-023,
  live/run_task.py, results/runs/*.json)
TESTS_ADDED=0 Produktionstests; 23 Task-Fixtures mit 200+ Testfällen (Eval-Fixtures)
TESTS_EXECUTED=285 HAMH-Regressions-Tests + 76 Live-Agent-Runs (Eval) +
  70 Fixture-RED-Verifikationen
LIVE_RUNS=76 (1 Smoke + 67 Baseline-Kalibrierung + 3 B + 3 C + 2 B-Regressions-Check...
  = 76, inkl. s000-Smoke und cal-t001-r1)
COMMITS=1 (dieser Run; siehe git log)

KNOWN_LIMITATIONS=
  - Harness-Recoverable-Zone (60-85 %) konnte mit 23 Tasks nicht befüllt werden:
    22 Tasks 100 %, 1 Task 0 % — das Modell ist auf dieser Task-Familie bipolar
    (Ceiling vs. Capability-Grenze); die Zielzone ist für diese Familie leer
  - Weakness nur auf 1 Task reproduziert (Cross-Task nicht erfüllt)
  - n=3 je A/B/C-Bedingung (kleine Stichprobe; Run Card §32: keine
    Pseudogenauigkeit — Paired-Befund ist eindeutig: 3 Ties B-vs-C)
  - Kosten sind Schätzungen auf Token-Basis (Pricing-Snapshot 2026-08-20),
    kein Provider-Usage-Report
  - t-001: 1 Kalibrierungs-Run statt 3 (Testkorrektur nach 1. Run; dokumentiert)
  - Control-Plane-/Adapter-Live-Suiten auf pve nicht ausgeführt (Infra/Secrets;
    keine Komponenten-Änderung → kein Regressionsrisiko aus diesem Run)
  - /tmp/opencode enthielt Alt-Artefakte (archiviert nach archive-20260821/,
    Datenleck-Risiko minimiert; ein t-008-Run durchsuchte /tmp — Effekt
    dokumentiert, Ergebnis (0 Edits) davon unabhängig)

REMAINING_RISKS=
  - pve-root-FS weiterhin 100 % (struktureller Zustand, bekannt; betrifft
    Registry-SCHREIBoperationen zukünftiger Runs — vor Promotion lösen)
  - t-008-Fehlerklasse: Prävalenz in realer Produktion unbekannt; wenn solche
    Randbedingungs-Aufgaben häufig sind, ist reasoning_effort=max auf
    Teil-Populationen zu prüfen (Nebenbefund, kein Kandidat)
  - opencode 1.15.13-Runtime: Session-Parsing funktioniert, aber Schema-
    Abhängigkeit bleibt ein Wartungspunkt

NEXT_EVIDENCE_DRIVEN_STEP=
  - Optional: Task-Familien mit höherer inhärenter Schwierigkeit suchen
    (Multi-Repo-Integrationen, Legacy-Refactoring mit versteckten Contracts),
    um die 60-85 %-Zone für künftige Runs zu befüllen
  - Optional: t-008-Klasse als targeted profiling-Kandidat für
    reasoning_effort=max auf Teilpopulationen (erst wenn Prävalenz belegt)
  - Original-24er-Holdout bleibt versiegelt für künftige Kandidaten
```

## Definition of Done (order §44)

| Kriterium | Status |
|---|---|
| Calibrated task population exists | PASS (23 Tasks, 69 Kalibrierungs-Runs) |
| Evaluation splits frozen | PASS (Development 4, Validation 8, New-Holdout 11 — Manifeste mit Fingerprints) |
| Original 24-task holdout remained sealed | PASS (Lock-Proof, 0 Zugriffe) |
| Baseline trajectories gathered | PASS (67, > 30 gefordert) |
| Weakness mining performed | PASS (4 Muster, 1 qualifiziert negativ) |
| No justified candidate OR exactly one tested | PASS (genau 1: edit-early, getestet) |
| A/B/C matched-compute methodology used | PASS (n=3 je Bedingung, C = baseline+max) |
| Candidate promoted or rejected by evidence | PASS (REJECTED — Matched-Compute erklärt Gewinn) |
| All critical runtime regressions green | PASS (285/285 lokal; keine Komponenten-Änderung) |

## Zentrale wissenschaftliche Regel (order §45)

Kein Ergebnis wurde erzwungen. Der Run liefert einen negativen Befund: Die
einzige reproduzierbare Baseline-Schwäche von DeepSeek V4 Flash in dieser
Task-Familie ist eine Research-Loop ohne Edit-Initiierung; sie ist durch
zusätzliches Reasoning-Budget (C) behebbar, nicht durch eine Prompt-Policy
(B). Der Kandidat wurde verworfen, weil die Matched-Compute-Kontrolle den
gesamten Gewinn erklärt. Die Messumgebung (kalibrierter Pool, Splits,
Baseline, Trajektorien-Pipeline, A/B/C-Maschinerie) ist etabliert und für
künftige Kandidaten wiederverwendbar.
