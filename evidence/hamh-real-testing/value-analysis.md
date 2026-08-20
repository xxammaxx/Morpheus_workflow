# HAMH Real Testing — Value Analysis

Datum: 2026-08-21 (Run: HAMH_REAL_TESTING)

## Fragestellung (zentrales Testprinzip)

> Arbeitet derselbe DeepSeek V4 Flash mit einem empirisch angepassten
> HAMH-Harness nachweisbar zuverlässiger oder wirtschaftlicher als mit der
> bisherigen Baseline — und bleibt dieser Vorteil bestehen, wenn
> zusätzliches Compute kontrolliert wird?

## Design

- Backbone konstant: deepseek-v4-flash (0731), thinking=enabled,
  reasoning_effort=high (A/B), max (C — Matched-Compute-Kontrolle)
- Trainings-Set: task_fixture_v2 (Slugify-Transliterations-Bug), FROZEN
- Baseline-Trajektorien: 10 Runs (e001–e010), HARNESS=FROZEN
- Weakness-Mining auf den 10 Baseline-Trajektorien (MIN_EVIDENCE_RUNS=2)
- Candidate: editing_strategy direct_edit -> precision_edit (Edit-Protokoll
  im Prompt) — einzige Variable
- Pilot: 3x(A,B,C) -> erweitert auf 5x(A,B,C)
- Holdout: 24 versiegelte Tasks generiert (eval-split-manifest.json), NICHT
  verwendet (kein Holdout nach Pilot-Ablehnung — order §27)

## Baseline (A, n=10)

verified 10/10 (100%), mean latency 35.2s, mean cost $0.002543,
mean input 36.6k / output 2.3k / reasoning 724 Tokens, mean tool calls 9.3.

## Weakness-Mining (order §23)

Patterns in >= 2 Runs (MIN_EVIDENCE_RUNS=2):

| Pattern | Runs | Erklärung |
|---|---|---|
| frequent_malformed_edits | 3 (e001,e004,e005) | Edit-Tool status=error (ungenauer oldString) |
| late_editing | 3 (e001,e004,e005) | Fehler-Edit -> erneuter Edit derselben Datei |
| same_file_repeatedly_reopened | 3 (e001,e004,e005) | Re-Read nach Edit-Fehler |
| excessive_tool_loops | 4 | >=3 pytest-Läufe oder >=14 Tool-Calls |

Kohärente Harness-Hypothese: unpräzise Edit-Strategie (oldString-Anker).
Candidate gerechtfertigt (>=2 Runs + plausible Harness-Ursache).

## Pilot A/B/C (n=5 je Bedingung, Trainings-Task)

| Bedingung | verified | mean cost | mean lat | edits | tools |
|---|---|---|---|---|---|
| A baseline (high) | 5/5 | $0.002545 | 36s | 2.4 | 9.6 |
| B candidate precision-edit (high) | 5/5 | $0.003383 | 46s | 3.2 | 12.4 |
| C matched compute (baseline + max) | 5/5 | $0.002693 | 37s | 2.4 | 9.4 |

Delta B vs A: cost +33.0%, latency +28.3%, edits +33.3%, tool calls +29.2%.
Delta C vs A: cost +5.8%, latency +3.9% (kein Compute-Effekt auf Success).

## Matched-Compute-Erklärung (order §28/33)

Der B-Effekt ist NICHT durch zusätzliches Compute erklärbar (C ≈ A). B ist
einfach schlechter: Die Edit-Protokoll-Anweisung veranlasst den Agenten zu
mehr Vorsichts-Reads und Edit-Nachbesserungen ohne messbaren Nutzen.
VERIFIED_SUCCESS ist in allen Bedingungen identisch (Decke 100%).

## Entscheidung (order §27/33/45)

```
HAMH_CANDIDATE=REJECTED  (PILOT_REJECTED)
VALUE_PROOF=AMBER_HAMH_VALUE_NOT_PROVEN
```

Begründung: B > A nicht erfüllt (Success gleich, Wirtschaftlichkeit
schlechter). B > C nicht erfüllt. Kein Holdout ausgeführt (order §27:
"Wenn B eindeutig schlechter ist: Candidate verwerfen. Keinen unnötigen
größeren Test durchführen."). Der Candidate wurde NICHT gerettet.

Negativer wissenschaftlicher Befund = erfolgreiches Experiment
(korrekt gemessen, ehrlich klassifiziert). Holdout bleibt versiegelt und
unbenutzt (keine Leakage; HOLDOUT_LEAKAGE_CHECK=clean).

## SAMPLE-SIZE-Limits

Pilot n=5/Bedingung, Trainings-Task n=1 (frozen). Kein Holdout (n=0).
Statistische Aussagekraft für den Value-Test begrenzt, aber die
Entscheidungsrichtung (B wirtschaftlich schlechter, C≈A) ist konsistent
über alle Runs; kein Pseudogenauigkeits-Claim.
