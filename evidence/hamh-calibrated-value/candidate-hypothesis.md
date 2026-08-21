# HAMH Calibrated Value — Candidate Hypothesis

Datum: 2026-08-21 (Run: HAMH_CALIBRATED_VALUE)
Kandidat: hamh/candidate/build/edit-early/v1

## Candidate-Gate (order §22)

| Feld | Wert |
|---|---|
| candidate_id | hamh/candidate/build/edit-early/v1 |
| parent_fingerprint | a1e6955fa0f1aadf099a331f7c34d6068445fa221ef82827c459d07e15625271 (Baseline) |
| observed_weakness | research_loop_no_edit: Agent recherchiert endlos, macht 0 Edits, erreicht Timeout |
| evidence | 3/3 Runs auf t-008 (cal-t008-r1/r2/r3), alle TIMEOUT@480s, 0 Edits, STRATEGY_FAILURE; reproduzierbar |
| causal_hypothesis | Der Harness (Prompt+Policy) terminiert die Recherche-Phase nicht und erzwingt keinen Hypothesen-Test. Bei Aufgaben, deren Fehler nicht direkt im Code sichtbar ist, bleibt DeepSeek V4 Flash in der Recherche, obwohl die Capability (Grenz-Semantik) vorhanden ist (Gegenprobe t-021/022/023: 100% gelöst). CAPABILITY AVAILABLE, NICHT EXTRAHIERT. |
| changed_component | prompt / editing protocol (Edit-Früh-Policy) — EINE Hauptvariable (order §23) |
| minimal_delta | Zusätzliche Anweisung an den Agenten: Nach höchstens 3 Recherche-Tool-Schritten muss eine konkrete Hypothese über die Fehlerursache durch einen Edit + pytest-Lauf geprüft werden (Teste-Hypothese-Edit-Zyklus). Kein Precision-Edit-Protokoll (Rejected-History §20). |
| expected_effect | B bricht die Research-Loop auf: früher erster Edit, frühes Feedback, höhere Chance auf Entdeckung der Randbedingungs-Bugs; kein Schaden bei bereits gelösten Tasks (t-021/022/023) |
| risk | (a) Überstürzte Edits mit falschen Hypothesen (mehr Tool-Aktivität, wie precision-edit); (b) Regression bei 100%-Tasks; (c) Timeout-Verhalten bleibt |
| rejected_alternative_hypotheses | H1 Modell-Capability fehlt → widerlegt durch t-021/022/023 (100%); H3 README-Mehrdeutigkeit → Tests spezifizieren exakt; H4 Stop-Policy → identisch mit H2, dort adressiert |
| rollback | Reine Prompt-Ebene: Candidate wird als Zusatz-Prompt-Datei appliziert (--candidate-prompt-file); Rollback = ohne Datei laufen. Kein Registry-/Resolver-Eingriff. |
| evaluation_plan | A/B/C auf t-008 (Development): A=Baseline (3 historische Runs), B=Candidate (3 neue Runs), C=Matched-Compute baseline+max (3 neue Runs). Zusätzlich B-Regressions-Check auf t-021/022/023 (je 1 Run). Weiter nur bei B>A mit plausibler Nutzen-Bilanz. |

## Interventionstext (minimal_delta, nur für Bedingung B)

```
Work protocol: after at most 3 research/exploration tool calls, form a
concrete hypothesis about the root cause and TEST it: make a small code
edit that implements your hypothesis, then run the test suite. Use the
test feedback to refine. Do not continue researching without having
tested at least one hypothesis in code.
```

## Abgrenzung zum verworfenen precision-edit

- precision-edit (REJECTED): zielte auf Edit-PrÄZISION (oldString-Anker, Vorsichts-Reads) → +33% Kosten, 0 Nutzen
- edit-early (dieser Kandidat): zielt auf Edit-INITIIERUNG (Research-Terminierung) → neue kausale Evidenz: 3 Runs mit 0 Edits
- Kein Bestandteil von precision-edit wird wiederverwendet
