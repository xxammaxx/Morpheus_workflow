# HAMH Calibrated Value — Promotion or Rejection

Datum: 2026-08-21 (Run: HAMH_CALIBRATED_VALUE)

## Entscheidung: CANDIDATE_REJECTED

Kandidat: hamh/candidate/build/edit-early/v1 (edit-early hypothesis-testing policy)

## Begründung (evidence-gated)

| Gate | Ergebnis | Evidenz |
|---|---|---|
| Weakness beobachtet (>=2 Runs) | PASS | research_loop_no_edit, 3/3 Runs auf t-008, 0 Edits, STRATEGY_FAILURE |
| Cross-Task-Reproduktion | NICHT ERFÜLLT | nur t-008; Gegenprobe t-021/022/023 (Fehlerklasse) bei 100 % gelöst |
| Kausale Hypothese | plausibel | Capability vorhanden, nicht extrahiert (Edit-Initiierung) |
| Development B vs A | BESSER | B 2/3 vs A 0/3 |
| Matched-Compute C vs A | GLEICH GUT WIE B | C 2/3, paired B vs C = 3 Ties |
| Vorteil durch C erklärt (order §29) | JA | Success-Delta identisch; C editiert nativ mehr (2.0 vs 0.7 Edits) |
| Regression auf 100 %-Tasks | KEINE | t-021/022/023 mit B weiterhin 100 % |
| Validation / New Holdout | NICHT ERREICHT | order §29: nur wenn Vorteil NICHT durch C erklärt |
| Externer 24er-Holdout | NICHT GEÖFFNET | bleibt versiegelt |

## Kernbefund

Die einzige reproduzierbare Baseline-Schwäche (research_loop_no_edit auf
t-008, 0 % Success) ist COMPUTE-SENSITIV: Erhöhtes Reasoning-Budget
(reasoning_effort=max, kanonische Evolutionsdimension) behebt sie in 2/3
Runs — ohne jede Policy-Änderung. Eine Prompt-Intervention (edit-early)
erzielt keinen über Matched-Compute hinausgehenden Nutzen. Der Kandidat
überlebt die Matched-Compute-Kontrolle nicht → Ablehnung.

## Nebenbefund (dokumentiert, KEIN Kandidat)

reasoning_effort=max löst t-008 in 2/3 Runs. Eine globale Profil-Anhebung
high→max wäre unverhältnismäßig (22/23 Tasks bereits bei 100 %, Kosten +
~5x). Prävalenz 1/23 → kein belastbarer Value-Beweis für eine Umstellung.

## Konsequenzen

- Kein Shadow, kein Canary, keine Promotion (order §36/§37)
- Registry unverändert: ACTIVE bleibt hamh/baseline/deepseek-v4-flash/build/thinking/v1
- Original-Holdout bleibt versiegelt
- Klassifikation: GREEN_HAMH_CALIBRATED_EVAL_FOUNDATION_PROVEN +
  HAMH_CANDIDATE_REJECTED + AMBER_HAMH_VALUE_NOT_PROVEN
