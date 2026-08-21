# HAMH Calibrated Value — Weakness Analysis

Datum: 2026-08-21 (Run: HAMH_CALIBRATED_VALUE)
Basis: 67 Baseline-Trajektorien (harness=a, FROZEN), 23 Tasks, opencode 1.15.13 + deepseek-v4-flash, reasoning high, Timeout 480s

## Aggregierte Muster (MIN_EVIDENCE_RUNS=2, order §19)

| Muster | Runs | Tasks | Verhältnis zu Success |
|---|---|---|---|
| excessive_pytest_loops | 9 | t-001, t-002, t-004, t-008, t-012, t-020 | meist ERFOLGREICHE Selbst-Korrektur-Schleifen (kein Harness-Defekt) |
| excessive_tool_calls | 6 | t-001, t-002, t-008, t-020 | meist erfolgreich; nur t-008-Fail |
| same_file_repeatedly_reopened | 2 | t-007, t-020 | beide Runs erfolgreich (Vorsichts-Reads) — kein negativer Effekt |
| **research_loop_no_edit** | **3** | **t-008 (nur)** | **0/3 verified, alle TIMEOUT, 0 Edits — einziger negativer Befund** |

## Kernbefund: research_loop_no_edit auf t-008

Beobachtung (3/3 Runs, reproduzierbar):
- 0 Edits in allen Runs (480s Timeout erreicht)
- Agent forscht endlos: durchsucht /tmp-Artefakte, inspiziert Bytecode (dis/marshal),
  pytest-Caches, alte Run-JSONs — statt eine Hypothese im Code zu testen
- Der Bug (zwei strikte `>`-Vergleiche statt `>=` an Intervallgrenzen) bleibt unentdeckt

Kausal-Hypothesen (§21 — Ursache vs Symptom):

| Hypothese | Bewertung |
|---|---|
| H1: Modell-Capability fehlt (Grenz-Semantik) | WIDERLEGT: t-021 (halb-offene Intervalle), t-022 (inklusive Fenstergrenzen), t-023 (inklusive Index-Grenzen) wurden mit DERSELBEN Baseline bei 100% in <30s gelöst. Die Capability ist im Modell vorhanden. |
| H2: Harness extrahiert Capability nicht (Zugänglichkeit) | GESTÜTZT: Der Agent verlässt nie die Recherche-Phase; kein Mechanismus zwingt zu einem Hypothesen-Test (Edit+pytest). Der Harness erlaubt unbefristete Recherche (einziges Stoppkriterium: Timeout). |
| H3: Task-Spezifikation irreführend (README) | TEILWEISE MÖGLICH: "darf busy NICHT berühren" könnte mehrdeutig gelesen werden; aber die Tests spezifizieren die Semantik exakt (exact-fit cases). Der Agent hätte die Tests als Spezifikation nutzen können. |
| H4: Stop-/Transition-Policy fehlt | GESTÜTZT: Kein Research→Edit-Übergang existiert (kein "genug recherchiert"-Kriterium). Deckungsgleich mit H2. |

Schlussfolgerung: `research_loop_no_edit` ist ein Harness-Zugänglichkeits-Muster
(CAPABILITY AVAILABLE im Modell, aber nicht EXTRAHIERT durch den Harness),
reproduzierbar in 3/3 Runs auf t-008. Schwäche: nur 1 Task betroffen; die
Fehlerklasse (Grenz-Semantik) ist auf 3 anderen Tasks unkritisch — die
Intervention darf dort keine Regression erzeugen.

## Fehlerklassen der 3 t-008-Fehlschläge (order §18)

Alle 3: STRATEGY_FAILURE (Research-Loop ohne Edit trotz ausreichender Tools).
Keine EXECUTION_FAILURE, keine HARNESS_FAILURE (Resolver/Provider fehlerfrei,
Resolution in allen Runs is_fallback=false), keine CAPABILITY_FAILURE (H1 widerlegt).

## Implikation fürs Candidate-Gate

- Weakness erfüllt MIN_EVIDENCE_RUNS=2 (3 Runs) ✓
- Weakness ist NICHT über mehrere Tasks reproduziert (nur t-008) ✗ (bevorzugt, nicht Pflicht)
- Kausale Hypothese belastbar: fehlende Edit-Initiierung / Research-Loop-Terminierung
- Die Intervention muss als EINE Hauptvariable testbar sein (Edit-Früh-Policy)
- A/B/C mit Matched-Compute (C = baseline + reasoning max) als Compute-Kontrolle
- Regressions-Schutz: B zusätzlich auf t-021/022/023 (100%-Baseline-Tasks) testen

## Vorheriger verworfener Candidate (order §20 — Rejected-History)

precision-edit (HAMH_REAL_TESTING): verworfen wegen 0 Success-Delta, +33% Kosten,
+28% Latenz. Diese Intervention wird NICHT erneut vorgeschlagen. Die neue
Intervention (edit-early) zielt auf eine ANDERE kausale Stelle (Edit-Initiierung,
nicht Edit-Präzision) und stützt sich auf NEUE Evidenz (3 Runs, 0 Edits).
