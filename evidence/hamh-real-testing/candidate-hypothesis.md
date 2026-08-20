# HAMH Candidate Hypothesis — Editing Strategy Precision

Datum: 2026-08-21 (Run: HAMH_REAL_TESTING)

## Candidate Contract (§25)

```
candidate_id=hamh/candidate/build/precision-edit/v1
parent_fingerprint=a1e6955fa0f1aadf099a331f7c34d6068445fa221ef82827c459d07e15625271
              (hamh/baseline/deepseek-v4-flash/build/thinking/v1, ACTIVE)

hypothesis:      Ein praeziseres Edit-Protokoll im Build-Harness reduziert
                 fehlgeschlagene Edit-Versuche (ungenauer oldString),
                 vermeidet Re-Reads und Edit-Wiederholungen und senkt damit
                 Tool-Calls, Latenz und Kosten bei gleicher Success-Rate.

evidence:        Baseline 10 Runs (e001-e010, v2-Fixture, DeepSeek V4 Flash):
                 verified 10/10 (100%). Weakness-Mining (MIN_EVIDENCE_RUNS=2):
                 frequent_malformed_edits in 3 Runs, late_editing in 3 Runs,
                 same_file_repeatedly_reopened in 3 Runs (e001/e004/e005).
                 Korrelation: fehlgeschlagener Edit (status=error) -> Re-Read
                 derselben Datei -> Edit-Wiederholung.

observed_pattern: frequent_malformed_edits + late_editing +
                  same_file_repeatedly_reopened (identische Run-Menge)

changed_component: editing_strategy  (VALID_COMPONENTS: editing_strategy)

minimal_delta:   editing_profile.strategy: "direct_edit" -> "precision_edit"
                 Effektive Wirkung: Der Build-Prompt erhaelt eine
                 Edit-Protokoll-Anweisung (einzige Aenderung):
                   - kleine, eindeutige oldString-Anker verwenden
                   - vor jedem Edit die exakte Stelle lesen
                   - minimale Diffs, ein logischer Schritt pro Edit

expected_effect: weniger fehlgeschlagene Edits (failed_edits sinkt), weniger
                 Re-Reads (reads sinkt), weniger Tool-Calls, niedrigere
                 Latenz/Kosten pro Run; verified_success_rate bleibt >= A.

risk:            niedrig: nur Prompt-Anweisung, keine Tool-/Modellaenderung;
                 Rollback = Registry-Rollback auf Parent (AC-8) + Prompt-
                 Anweisung entfernen.

rollback:        registry.rollback(candidate_id) -> Parent-Fingerprint exakt
                 wiederhergestellt; Run-Skript ohne precision-edit-Anweisung.

evaluation_plan: Pilot 3x(A,B,C) auf Trainings-Task (v2) -> bei B>=A weiter;
                 Holdout 20 Tasks x (A,B,C) mit versiegeltem Split-Manifest;
                 Matched-Compute C = A + reasoning_effort=max (gleiches
                 zusaetzliches Inference-Budget wie B effektiv verbraucht).
```

## Variable: genau eine Hauptvariable (§25)

editing_strategy (nur diese). Kein gleichzeitiges Aendern von
tool exposure / context / stop rule / thinking effort.
reasoning_effort bleibt in A und B identisch (high); nur C erhoeht auf max
(Matched-Compute-Kontrolle).

## Baseline-Fingerprint (FROZEN, §22)

```
HARNESS_FINGERPRINT=a1e6955fa0f1aadf099a331f7c34d6068445fa221ef82827c459d07e15625271
MODEL=deepseek-v4-flash (0731) FROZEN
TASK_SUITE=v2-Fixture FROZEN (Trainings-Set; Holdout separat)
```

## Statistische Ehrlichkeit (§32)

n je Bedingung klein (Pilot 3, Holdout 20). Paired-Design: jede Holdout-
Aufgabe laeuft unter A, B UND C (gepaarte Daten). Kein Pseudogenauigkeit:
kleine n werden als SAMPLE_SIZE_LIMITED gekennzeichnet; Bootstrap-CI wo
sinnvoll.
