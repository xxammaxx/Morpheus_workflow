# HAMH — Hierarchical Adaptive Model Harness — Formale Spezifikation

Begleitdokument zu ADR-2026-08-20 (Entscheidungen H1–H16). Kanonische
Bauvorgabe für `runtime/hamh/`, die beiden neuen Contracts, die Adapter-Naht,
den Generator-Passthrough und die Tests. Ergänzt den v2-Stack (ADR-2026-08-17,
E1–E16); ersetzt nichts.

```text
LLMs ARE WORKERS. LLMs ARE NOT THE CONTROLLER. n8n = CONTROL PLANE.
```

---

## 1. Zielbild

Ein Shared Kernel (unveränderlich, modellevolvierbar verboten) plus
versionierbare, hot-swappable Harness-Zellen (Model-Adapter, Model-Profile,
Task-Profile) mit deterministischem Resolver, deterministischer Evaluations-
Suite und einer autoritätsgesteuerten Promotionskette (DRAFT → ACTIVE nur über
den autorisierten Pfad). Erster echter Referenzpfad: DeepSeek V4 Flash
(`deepseek-v4-flash`). Provider-/Modell-agnostisch ab Tag 1, kein separater
DeepSeek-Stack.

## 2. Nichtziele (explizit NICHT gebaut)

- Kein zweiter autonomer Orchestrator / Controller.
- Kein neues Workflow-Framework; n8n-Control-Plane bleibt deterministischer Kern.
- Kein zweiter Router, kein zweiter MCP-Stack, kein zweiter Verifier, keine
  zweite Retry-/Queue-/Datenbank-Instanz.
- Keine Evolution des Shared Kernels durch ein Modell.
- Kein Live-DeepSeek-Aufruf in diesem Lauf (Adapter = reine Semantik + Tests).
- Keine LLM-Urteile in Gates/Promotion (deterministisch, konsistent mit E9).
- Kein Wert-Urteil ohne Matched-Compute-Kontrolle + Holdout.

## 3. Schichten A–E (Mapping auf Bestand)

| Schicht | Verantwortung | Evolvierbar? | Umsetzung |
|---|---|---|---|
| **A Shared Kernel** | Controller-Autorität, Routing, Provider-Auswahl, globale Contracts, Security, MCP-Allow/Deny, Budgets, Retry/Eskalation, Verifikation, Audit, Git-Safety, Produktions-Sentinels, Rollback, Promotions-Autorität | **NEIN** (global) | Bestand: n8n-Workflows 00–90, `runtime/contracts/`, deterministische Verifikation/Gates. Neu: nur mechanisches Promotions-Autoritäts-Gate in `runtime/hamh/registry.py` |
| **B Model Adapter** | Provider/API-Semantik: exakte Modell-ID, Thinking, Reasoning-Effort, Tool-Call-Semantik, Multi-Turn-State, Context-Fenster, Max-Output, Cache-Telemetrie, Fehlertypen, Rate/Concurrency | ja, aber **Semantik ≠ Prompt-Profil** | `runtime/hamh/deepseek_adapter.py` (keine Live-Calls) |
| **C Model Profile** | Reasoning-Strategie, Kontext-Präferenzen, Tool-Präferenzen, Editier-Strategie, Stop-Verhalten, Failure-Fingerprints, Interaktion, cache-freundliches Layout, Komplexitätsschwellen | **ja** (versioniert) | `runtime/hamh/profiles.py` `ModelProfile` |
| **D Task Profiles** | research/plan/build/review (verify bleibt deterministisch) | ja, nur bei `SPECIALIZATION_VALUE=PROVEN` | `runtime/hamh/profiles.py` `TaskProfile` (initial identisch = geteiltes Baseline) |
| **E Execution+Evaluation+Evolution+Promotion** | Trajektorien-Telemetrie, Evaluations-Suite, Candidate-Sandbox, Promotion | ja, aber **nur propose/test** | `runtime/hamh/evolution.py`, `telemetry.py`, `evidence/tests/hamh/task_suite.py` |

## 4. Invarianten (vollständige Liste → Enforcement-Punkt)

| Invariante | Enforcement-Punkt |
|---|---|
| CONTROLLER_AUTHORITY (n8n entscheidet Jobs/Backend) | Workflow-Generator (nur Passthrough, kein Controller-Umbau) |
| ROUTING_AUTHORITY (Backend-Allowlist unverändert) | Adapter `VALID_BACKENDS` (unverändert) |
| RETRY_ESCALATION_SEPARATION (FIX→SPLIT deterministisch) | WF 01 „Retry Policy" (unverändert) |
| MCP_SECURITY_BOUNDARY | Shared Kernel (kein MCP-Eingriff) |
| PRODUCTION_SENTINELS (Plan-Canary, write_attempts) | Adapter `job_plan` + Contract `const:true` (unverändert) |
| VERIFIER_AUTHORITY (pytest/compileall/git-scope deterministisch) | Adapter `job_verify` (unverändert) |
| AUDITABILITY (Ledger metadata-first, kein Prompt/Secret) | Adapter-Ledger + `telemetry.py` |
| ROLLBACK (exakt vorherige ACTIVE-Konfiguration) | `registry.py` `rollback()` |
| MODEL_SELF_PROMOTION = DENIED | `registry.py` `promote()` nur mit Autoritäts-Token/Gate |
| SECURITY_CHANGE = DENIED | Tool-Profil ⊆ Controller-Allowlist |
| ROUTING_CHANGE = DENIED | Resolver ändert nie `backend` |
| EVOLVER_CAN_PROPOSE=YES / TEST=YES / PROMOTE=NO / CHANGE_GATES=NO / CHANGE_HOLDOUT=NO | `evolution.py` (harte Konstanten) |
| SPECIALIZATION_VALUE=PROVEN sonst geteiltes Profil (kein Varianten-Explosion) | `profiles.py` + `evolution.py` |
| effective_tools ⊆ controller_allowed_tools | `profiles.py` Schnittmenge bei Auflösung |
| Unbekanntes Modell → deterministischer Baseline-Fallback | `resolver.py` |
| CAPABILITY_FAILURE → bestehendes Routing (kein Endlos-Loop) | `taxonomy.py` → WF 01 Retry-Policy |

## 5. Datenmodelle

### 5.1 Harness-Registry-Eintrag (`hamh.harness.v1`)

Felder: `harness_id`, `provider`, `model`, `model_revision`, `task_class`,
`runtime_mode`, `version`, `status`, `fingerprint`, `parent_version`,
`created_at`, `promotion_state`, `prompt_profile`, `context_profile`,
`tool_profile`, `editing_profile`, `stop_profile`, `evaluation_reference`.

`fingerprint` = SHA-256 über die kanonische Serialisierung der
semantischen Profil-Felder (bestehende `fingerprint.py`-Strategie;
`x-metadata` exkludiert).

### 5.2 Resolver-Ausgabe (`hamh.resolution.v1`)

Felder: `resolved_harness_id`, `version`, `fingerprint`,
`effective_tool_profile`, `effective_context_profile`,
`effective_reasoning_profile`, `fallback_profile` (gesetzt bei Baseline-Fallback).

### 5.3 Trajektorien-Felder

`run_id`, `model`, `provider`, `model_revision`, `harness_id`,
`harness_version`, `harness_fingerprint`, `task_class`, `runtime_mode`,
`context_volume`, `tool_calls`, `tool_failures`, `retry_count`, `escalation`,
`token_usage`, `cache_hit_tokens`, `cache_miss_tokens`, `latency`,
`verification_result`, `failure_class`, `final_result`.
**Kein** `reasoning_content`, keine Prompts/Blobs/Secrets (Privacy by Default).

## 6. Registry-Semantik (Zustände, Transitionen, Autorität)

Zustände: `DRAFT`, `CANDIDATE`, `SHADOW`, `CANARY`, `ACTIVE`, `RETIRED`, `REJECTED`.

Transitionen (deterministisch, gate-gebunden):

```text
DRAFT → CANDIDATE   (minimale, ein-Komponenten-Modifikation + gültiger Contract)
CANDIDATE → SHADOW  (OFFLINE EVAL + VALIDATION bestanden, kein Leakage)
SHADOW → CANARY     (HOLDOUT bestanden, kein Regression-Bruch)
CANARY → ACTIVE     (autorisiertes promote() NUR durch autorisierten Aufrufer)
* → RETIRED         (explizite Stilllegung)
* → REJECTED        (Gate-Fehler, Regression, Leakage, NOT_PROVEN)
ACTIVE → (Rollback) (rollback() stellt exakt die vorherige ACTIVE-Konfiguration wieder her)
```

Autorität: `promote()` verlangt ein explizites Autoritäts-Token/Gate
(deterministisch, im Shared Kernel verankert). Ein Kandidat kann sich nie
selbst auf ACTIVE setzen; RETIRED-Harness sind nur für explizites
Replay/Audit auflösbar.

## 7. Resolver-Semantik (Inputs, Outputs, Fallback, Determinismus)

Inputs: `provider`, `model`, `task_class`, `runtime_mode`,
`requested_capabilities`, `runtime_constraints`.
Outputs: siehe §5.2.

Auflösungsregel (deterministisch, testbar):
1. Normalisiere Identität (exakte Modell-ID, kein Alias-Raten).
2. Suche ACTIVE-Eintrag passend zu Identität + task_class + runtime_mode.
3. Schneide `effective_tool_profile` gegen Controller-Allowlist (⊆).
4. Unbekanntes Modell / kein ACTIVE → expliziter Baseline-Fallback
   (`fallback_profile` gesetzt), **kein Crash, kein Zufall**.
5. Ergebnis ist eine reine Funktion der Inputs (gleiche Inputs → gleiche
   Ausgabe, inkl. Fingerprint).

## 8. Tool-/Kontext-/Thinking-Profil-Semantik

- **Tool-Profil:** Fähigkeit (erlaubt/verboten) getrennt von Präsentation
  (strukturiert vs. Fließtext). `effective_tools` = Profil ∩ Allowlist.
  Strukturierte Schnittstellen nur evidenzgetrieben (Devil-in-the-Interface).
- **Kontext-Profil:** stabiler Präfix (System/Anweisung) vs. variabler Teil;
  cache-freundliche Anordnung ist Provider-Level-Semantik; Hit/Miss-Telemetrie
  in Trajektorie.
- **Thinking-Profil:** `thinking` (enabled/disabled) + `reasoning_effort`
  (low/high/max) als Profilvariable; Matrix `einfach/komplex × thinking/
  non-thinking` wird gemessen (Erfolg, First-Pass, Latenz, Tokens, Tool-Calls,
  Retries, Eskalation).

## 9. Failure-Taxonomie (Mapping alt → neu)

Neue Meta-Klassen **erweitern** die bestehenden Adapter-Fehlerklassen (kein
Duplikat). Mapping:

| Neue Klasse | Bestehende Adapter-Klassen | Aktion |
|---|---|---|
| HARNESS_FAILURE | CONTRACT_FAILURE (durch fehlerhaftes Harness-Output), malformed_response, CONTRACT_INVALID | Harness-Kandidat reparieren/verwerfen (kein Modell-Retry) |
| EXECUTION_FAILURE | TIMEOUT, INFRA_FAILURE, PROVIDER_FAILURE, UNKNOWN | bestehende Eskalation (kein Modell-Unfähigkeits-Urteil) |
| STRATEGY_FAILURE | TEST_FAILURE, BUILD_FAILURE, LINT_FAILURE, CONTEXT_FAILURE (mit new_evidence/strategy_delta) | bestehendes FIX/SPLIT-Leiter |
| CAPABILITY_FAILURE | TEST_FAILURE/BUILD_FAILURE nach retry mit gerechtfertigtem Delta → identischer Fundamentalfehler | bestehendes Routing/Eskalation (RETRY_DENIED_* → SPLIT); **kein Endlos-Evolutions-Loop** |

Capability-vs-Harness-Beweis: Fehler → Retry mit gerechtfertigtem Delta →
gleicher Fundamentalfehler → Taxonomie → CAPABILITY_FAILURE → Routing/Eskalation.

## 10. Evolutions-Governance (Pipelines, Gates, Holdout, Matched-Compute)

Pipeline: Produktions-Trajektorien → Schwächen-Mining → Hypothese → minimale
Kandidaten-Modifikation (eine Komponente pro Experiment) → Kandidat →
Evaluation (EVOLUTION/TRAIN) → Regression → HOLDOUT → SHADOW → CANARY →
autorisierte Promotion.

Gates:
```text
EVOLVER_CAN_PROPOSE=YES  EVOLVER_CAN_TEST=YES  EVOLVER_CAN_PROMOTE=NO
EVOLVER_CAN_CHANGE_GATES=NO  EVOLVER_CAN_CHANGE_HOLDOUT=NO
```

Leakage-Sentinel: EVOLUTION/TRAIN, VALIDATION und HOLDOUT sind getrennte
Mengen; ein Sentinel markiert jede Überschneidung → Experiment REJECTED.

Matched-Compute-Kontrolle:
- A = aktuelles Harness, B = Kandidat, C = aktuelles + äquivalentes Zusatzbudget.
- B muss A schlagen UND der Effekt darf nicht durch C erklärbar sein, sonst
  `HARNESS_VALUE=NOT_PROVEN`.

## 11. Metriken

Primär: **VERIFIED_SUCCESS_RATE** (deterministischer Verifier, kein LLM-Urteil).
Sekundär: First-Pass-Rate, Kosten/Latenz/Tool-Calls pro verifiziertem Erfolg,
Retry-Rate, Eskalations-Rate, Token-Verbrauch, Cache-Hit-Rate, Regressions-Rate.

## 12. Promotionslebenszyklus + Rollback

CANDIDATE → OFFLINE EVAL → HOLDOUT → SHADOW → CANARY → ACTIVE mit
dokumentierten Akzeptanzkriterien pro Transition; deterministischer
Rollback auf die vorherige ACTIVE-Konfiguration bei Regression.

## 13. DeepSeek-Adapter-Spezifika (exakte API-Semantik)

Siehe ADR H6. Operative Tabelle (reine Semantik, keine Live-Calls):

| Aspekt | Wert |
|---|---|
| Modell-IDs | `deepseek-v4-flash`, `deepseek-v4-pro` (andere RETIRED) |
| Reasoning | Modus, kein Modell: `thinking.type` enabled/disabled |
| Reasoning-Effort | low/high/max; medium/xhigh → high |
| temperature/top_p | stille No-Ops im Thinking-Modus |
| Tool-Turn-Regel | `reasoning_content` in ALLEN Folge-Requests zurückgeben wenn `tools` gesetzt, sonst 400 |
| Tools | nur `type: function`, max 128; tool_choice none/auto/required/named |
| Strict-Mode | Beta, `/beta`-Base-URL, alle `strict:true`, Props required+additionalProperties:false; kein String min/maxLength |
| Prefix Completion | Beta `/beta`, letzte Message assistant+prefix:true, reasoning_content als CoT-Input |
| Context / Max-Output | 1M / 384K (beide Modelle); kein dokumentierter max_tokens-Default |
| Cache | automatisches Prefix-Caching; `prompt_cache_hit_tokens`/`miss_tokens` |
| Fehler | nur HTTP-Status: 400/401/402/422/429/500/503; `finish_reason` inkl. insufficient_system_resource |
| Concurrency | flash 2500, pro 500; optional `user_id`; 10-min keep-alive |
| Endpunkte | `https://api.deepseek.com`, `/anthropic`, `/beta`; Bearer-Auth |
| Namenskollision | „DeepSeek Harness" = separates offizielles Produkt; nie nackt verwenden |

## 14. Operational-Runbook-Umriss (später in `docs/operations/hamh.md`)

Was dorthin gehört (nur Umriss hier): Registry-Pfad/Datei-Layout im
State-Verzeichnis; `promote()`-Aufruf + Autoritäts-Token; Rollback-Prozedur;
Resolver-Debug (Auflösungs-Artefakt je Run lesen); Generator-Regeneration
(`python3 workflow/v2/generate_workflows_v2.py <config.json> <outdir>`) +
Redeploy-Freigabeschritt; DeepSeek-Credential-Bereitstellung (falls je
vorhanden) + Concurrency/Budget-Einstellung; Trajektorien-Auswertung.

---

## 15. ACCEPTANCE CRITERIA (Gate für Implementierung)

Alle deterministisch prüfbar; nur AC-1..AC-9, AC-11, AC-13, AC-14 sind in
diesem Lauf GREEN-fähig; AC-10 und AC-12 sind ehrlich AMBER/offen (siehe Plan).

1. **AC-1 Isolation A:** build-Profil kann research-Profil nicht mutieren
   (getrennte Versionierungsräume).
2. **AC-2 Isolation B:** deepseek-Profile können Profile anderer Modelle nicht mutieren.
3. **AC-3 Isolation C:** Kandidat kann sich nicht selbst auf ACTIVE setzen
   (`promote()` schlägt ohne Autorität fehl).
4. **AC-4 Isolation D:** Task-Profil kann kein Tool außerhalb der Controller-Allowlist aktivieren.
5. **AC-5 Isolation E:** unbekanntes Profil → deterministischer Baseline-Fallback (kein Crash).
6. **AC-6 Isolation F:** RETIRED-Harness ist nicht auflösbar außer explizitem Replay/Audit.
7. **AC-7 Isolation G:** jede semantisch relevante Profiländerung ändert den Fingerprint.
8. **AC-8 Isolation H:** Rollback stellt exakt die vorherige ACTIVE-Konfiguration wieder her.
9. **AC-9 Resolver-Determinismus:** gleiche Inputs → identische Ausgabe
   (inkl. Fingerprint) über N Wiederholungen.
10. **AC-10 Registry-Autorität:** `promote()` akzeptiert nur autorisierten Aufrufer; abgelehnt → REJECTED/kein Zustandswechsel.
11. **AC-11 Capability-Klassifikation:** failure→retry(delta)→gleicher Fundamentalfehler → CAPABILITY_FAILURE → Routing/Eskalation, kein Endlos-Loop.
12. **AC-12 Leakage-Sentinel:** Überschneidung EVOLUTION/VALIDATION/HOLDOUT → Experiment REJECTED.
13. **AC-13 Matched-Compute:** B schlägt A UND Effekt nicht durch C erklärbar, sonst NOT_PROVEN (deterministische Stub-Metriken).
14. **AC-14 Contracts + Fingerprint:** beide neuen Contracts validieren;
    Fingerprint stabil; `test_contracts.py` + Äquivalenz-Suite bleiben grün.
15. **AC-15 Regression:** bestehende 26+27+30+9 Tests bleiben grün; HAMH ergänzt nur.
16. **AC-16 Adapter-Naht:** optionale Felder rückwärtskompatibel; `_opencode_sem`
    definiert; Harness-Felder in Record + Ledger + Resolution-Artefakt.
17. **AC-17 Generator-Passthrough:** Prep-Nodes reichen provider/model/task_class
    durch; Validate-Intake-Backend-Whitelist unverändert; JSON-Exporte regeneriert (lokal, kein Redeploy).

---

## 16. IMPLEMENTATION PLAN (geordnet, atomar, testbar)

Reihenfolge = Abhängigkeitsordnung. Legende: **[GREEN]** = in diesem Lauf
beweisbar; **[AMBER]** = ehrlich offen/not-proven (Infrastruktur fehlt);
**[RUNBOOK]** = benötigt Freigabe/Produktionsänderung, hier nur lokal.

### T1. Contracts [GREEN]
- **Was:** `runtime/contracts/schemas/hamh.harness.v1.schema.json` +
  `hamh.resolution.v1.schema.json`; Registrierung in `registry.py` CONTRACTS;
  Fixtures in `test_contracts.py` ERWEITERN (keine bestehenden Assertions ändern).
- **Dateien:** `runtime/contracts/schemas/hamh.*.v1.schema.json`,
  `runtime/contracts/registry.py`, `runtime/tests/test_contracts.py`.
- **Test:** `python3 runtime/tests/test_contracts.py`
- **Done:** beide Contracts validieren; negative Fixtures abgelehnt; FP-Stabilität.

### T2. runtime/hamh/ Kernmodul [GREEN]
- **Was:** `taxonomy.py` (4-Klassen-Mapping), `profiles.py` (ModelProfile/TaskProfile,
  initial identisch), `registry.py` (JSON-Store, Zustandsmaschine, promote/rollback,
  Autorität), `resolver.py` (deterministisch + Baseline-Fallback), `evolution.py`
  (Candidate, Sandbox, Holdout-Sentinel, Leakage, Matched-Compute-Komparator,
  eine-Komponente-Regel), `telemetry.py` (Trajektorien-Builder).
- **Dateien:** `runtime/hamh/{__init__,taxonomy,profiles,registry,resolver,
  evolution,telemetry}.py`.
- **Test:** `python3 -m unittest runtime/hamh/tests/*` bzw. `python3
  evidence/tests/hamh/test_isolation.py` (folgt Repo-Stil: stdlib-Runner).
- **Done:** AC-1..AC-8, AC-9, AC-10, AC-12, AC-13 grün (deterministisch).

### T3. DeepSeek-Model-Adapter [GREEN]
- **Was:** `deepseek_adapter.py` — Message-Assembly, Thinking-Toggle,
  reasoning_effort-Mapping, reasoning_content-Echo-Back über Tool-Turns
  (400-Regel), Fehler-Mapping nach HTTP-Status, Cache-Telemetrie-Parsing,
  Beta-URL für Strict-Mode. **Keine Live-Netzwerkaufrufe.**
- **Dateien:** `runtime/hamh/deepseek_adapter.py`, `evidence/tests/hamh/
  test_deepseek_adapter.py`.
- **Test:** `python3 evidence/tests/hamh/test_deepseek_adapter.py`
- **Done:** Contract-Tests der API-Semantik grün (Thinking/Effort/400-Regel/
  Fehler-Mapping/Cache/Strict-Beta).

### T4. Adapter-Naht (rückwärtskompatibel) [GREEN]
- **Was:** `_dispatch`/`do_POST` akzeptieren optionale provider/model/
  model_revision/task_class; Resolver-Aufruf beim Dispatch; Harness-Felder in
  `new_job`/`finalize_job`/Ledger-Subset; Resolution-Artefakt je Run;
  Bugfix `_opencode_sem = threading.BoundedSemaphore(1)`.
- **Dateien:** `adapter/harness_adapter_v2.py`.
- **Test:** `python3 evidence/tests/v2/adapter_suite.py` (Regression) +
  `python3 evidence/tests/hamh/test_adapter_hamh_seam.py` (neu).
- **Done:** AC-16; bestehende 30 Adapter-Tests grün; Backend-Routing unverändert.

### T5. Generator-Passthrough [GREEN lokal / RUNBOOK deploy]
- **Was:** Prep-Nodes reichen provider/model (whitelisted, Default = aktuelles
  Verhalten) + task_class durch; Validate-Intake-Backend-Whitelist UNVERÄNDERT;
  JSON-Exporte lokal regenerieren. **Kein Live-Redeploy in diesem Lauf.**
- **Dateien:** `workflow/v2/generate_workflows_v2.py`, `n8n/workflows/autodev/*.json`.
- **Test:** Generator-Ausführung + Diff der Exporte (nur additive Felder).
- **Done:** AC-17; Exporte konsistent; Runbook-Schritt für Redeploy dokumentiert.

### T6. Tests A–H + Capability + DeepSeek [GREEN]
- **Was:** `evidence/tests/hamh/test_isolation.py` (A–H),
  `test_capability_vs_harness.py`, `test_deepseek_adapter.py`,
  `evidence/tests/hamh/task_suite.py` (deterministische Mikro-Tasks mit
  Hidden-Tests-Verifier + Stub-„Modell"-Executor — beweist Governance OHNE LLM).
- **Test:** jeweils `python3 evidence/tests/hamh/<file>`.
- **Done:** AC-1..AC-13 über die deterministische Suite; Governance-Mechanik
  (candidate/validation/holdout/leakage/promotion/rollback) nachgewiesen.

### T7. Docs [GREEN]
- **Was:** diese ADR + Spec; später `docs/operations/hamh.md` (Runbook-Umriss §14).
- **Dateien:** `docs/architecture/adr-2026-08-20-hamh.md`,
  `docs/architecture/hamh-spec.md`.

### T8. Evidenz + Abschlussklassifikation [GREEN / AMBER]
- **Was:** `evidence/phase-*-hamh/README.md` mit korrelierter Evidenz
  (Testausgaben, Artefakte). Klassifikation:
  - `GREEN_HAMH_FOUNDATION_OPERATIONAL` (T1–T6 deterministisch grün),
  - `GREEN_HAMH_EVOLUTION_GOVERNANCE_PROVEN` (AC-1..AC-13 deterministisch),
  - `AMBER_HAMH_VALUE_NOT_PROVEN` (AC-14/15 ohne Live-Modelle nicht beweisbar;
    DEEPSEEK_LIVE_PROOF=NOT_RUN), ehrlich dokumentiert.
- **Done:** Abschlussbericht mit Klassifikation, kein erfundener Value-Beweis.

### Hinweis zu GREEN/AMBER-Gating
`GREEN_HAMH_DEEPSEEK_V4_FLASH_RUNTIME_PROVEN` und `GREEN_HAMH_VALUE_PROVEN`
sind **nicht** in diesem Lauf erreichbar (kein Credential, LM Studio offline,
CT 8001 gestoppt, kein Remote). Sie bleiben als zukünftige Stufen dokumentiert,
werden aber nicht behauptet.
