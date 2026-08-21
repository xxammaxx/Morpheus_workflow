# HAMH Calibrated Value — Matched-Compute-Analyse

Datum: 2026-08-21 (Run: HAMH_CALIBRATED_VALUE)
Kandidat: hamh/candidate/build/edit-early/v1 — Development A/B/C auf t-008

## Fragestellung (order §26/§29)

Erklärt zusätzliches Compute (C = Baseline + reasoning_effort=max) den
beobachteten B-Effekt? Wenn ja: kein Harness-Policy-Nutzen über Compute hinaus.

## Daten (n=3 je Bedingung, t-008)

| Bedingung | verified | Timeouts | mean Latenz | mean Kosten | mean Edits | mean Tools | Cost/Verified |
|---|---|---|---|---|---|---|---|
| A Baseline (high) | 0/3 | 3 | 480s (alle Timeout) | $0.007054 | 0.0 | 13.7 | — |
| B edit-early (high) | 2/3 | 1 | 378s | $0.009202 | 0.7 | 13.7 | $0.013802 |
| C Baseline + max | 2/3 | 2 | 449s | $0.010968 | 2.0 | 17.7 | $0.016452 |

## Analyse

1. **Success**: B (0.667) == C (0.667), beide > A (0.0). Der Success-Zuwachs
   gegenüber A ist in beiden Bedingungen identisch (+0.667).
2. **Edits**: C editiert OHNE Policy-Anweisung mehr (2.0 vs 0.7) — mehr
   Reasoning-Budget führt von selbst zu mehr Hypothesen-Tests im Code.
   Die kausale Stelle der edit-early-Policy (Edit-Initiierung) wird durch
   das höhere Reasoning-Budget NATIV bedient.
3. **Cost/Latency**: B ist günstiger als C (Cost/Verified $0.0138 vs $0.0165),
   aber der Success-Gewinn ist identisch; beide sind deutlich teurer als A
   (das auf t-008 allerdings 0 % Erfolg hat).
4. **Paired**: B vs C = 0 Wins, 0 Losses, 3 Ties (identische Outcomes je Run-
   Paar: B1/C1 success, B2/C2 success, B3/C3 fail). Bietet B irgendeinen
   Vorteil über C? Keinen messbaren auf Success; einen kleinen auf Kosten.

## Urteil (order §29)

Der B-Vorteil gegenüber A wird durch C (matched compute) VOLLSTÄNDIG erklärt:
Beide erreichen 2/3; die Policy-Anweisung erzielt keinen Success-Vorteil
gegenüber schlicht mehr Reasoning-Budget. Die Weakness research_loop_no_edit
ist compute-sensitiv (mehr Denken → mehr Edit-Versuche → Erfolg), aber nicht
policy-spezifisch behandelbar im Sinne eines überlegenen Harness-Deltas.

## Nebenbefund (kein Promotions-Kandidat)

reasoning_effort=max (kanonische Evolutionsdimension high|max) löst t-008 in
2/3 Runs. Eine globale Profil-Umstellung high→max für alle Build-Tasks wäre
jedoch unverhältnismäßig: Auf den 22 Tasks mit 100 % Baseline-Success brächte
sie 0 Success-Nutzen bei signifikant höheren Kosten/Latenz (C mean $0.011 vs
A mean ~$0.002). Prävalenz der t-008-Fehlerklasse ist mit 1/23 Tasks zu gering
für eine globale Effort-Anhebung. Kein registrierter Kandidat, dokumentierter
Nebenbefund.

## Rejected-Alternative-Hypothesen (Kurzfassung)

- H1 Capability fehlt: widerlegt (t-021/022/023 bei 100 %)
- H3 README-Mehrdeutigkeit: Tests spezifizieren exakt; C löst ohne README-Änderung
- H4 Stop-Policy: compute-sensitiv, nicht policy-spezifisch (siehe oben)

## Schlussfolgerung

CANDIDATE_REJECTED — der edit-early-Kandidat überlebt die
Matched-Compute-Kontrolle nicht. Kein Holdout-Verbrauch (order §29).
