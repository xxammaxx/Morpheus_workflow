# HAMH — Hierarchical Adaptive Model Harness — Betriebsanleitung (Operations)

Kurzreferenz für Betrieb, Deployment und Tests der HAMH-Schicht auf dem
AutoDev-Harness-v2-Control-Plane. Kanonische Bauvorgabe: ADR-2026-08-20
(H1–H16) + `docs/architecture/hamh-spec.md`. Ergänzt die v2-Betriebsanleitung
(`docs/operations/autodev-harness-v2.md`), ersetzt nichts.

```text
LLMs ARE WORKERS. LLMs ARE NOT THE CONTROLLER. n8n = CONTROL PLANE.
```

## Komponenten

| Komponente | Ort | Hinweise |
|---|---|---|
| HAMH-Paket | `runtime/hamh/` | `registry.py`, `resolver.py`, `profiles.py`, `taxonomy.py`, `evolution.py`, `telemetry.py`, `deepseek_adapter.py`, `__init__.py` (Version 1.0.0) |
| Contract `hamh.harness.v1` | `runtime/contracts/schemas/hamh.harness.v1.schema.json` | Registry-Eintrag; ACTIVE nur über autorisierten Promotionspfad |
| Contract `hamh.resolution.v1` | `runtime/contracts/schemas/hamh.resolution.v1.schema.json` | Deterministische Resolver-Ausgabe inkl. `fallback_profile` |
| Contracts-Registry | `runtime/contracts/registry.py` | `CONTRACTS` = 12 autodev.* + 2 hamh.* = 14 Einträge |
| Adapter-Naht | `adapter/harness_adapter_v2.py` | optionale Felder `provider/model/model_revision/task_class`; Resolver beim Dispatch; Harness-Felder in Job-Record + Ledger; Resolution-Artefakt je Run |
| Generator-Passthrough | `workflow/v2/generate_workflows_v2.py` | Prep-Nodes reichen provider/model/model_revision/task_class durch; Backend-Whitelist unverändert (`embedded`/`opencode-builder-8001`) |
| Registry-Datei (Empfehlung) | `<STATE_DIR>/hamh/registry.json` (= `/var/lib/autodev-harness-v2/hamh/registry.json`) | JSON-Store im bestehenden State-Verzeichnis (systemd `ReadWritePaths`); der Adapter lädt die Registry beim Start automatisch, wenn die Datei existiert — ohne Datei bleibt der explizite Baseline-Fallback aktiv. Autoritäts-Token aus Env-Variable `AUTODEV_HAMH_AUTHORITY` (nie im Adapter persistiert) |
| Adapter auf pve | `/opt/autodev-harness-v2/` | systemd `autodev-harness-v2`, Port 8081 |

## Registry-Betrieb

`HarnessRegistry(path, authority_token)` — JSON-Datei-gestützter Store,
deterministische Zustandsmaschine. Ohne `authority_token` ist `promote()`
**immer** abgelehnt (Secure Default: `_authorized()` liefert `False` bei
`authority_token is None`).

Zustände: `DRAFT`, `CANDIDATE`, `SHADOW`, `CANARY`, `ACTIVE`, `RETIRED`,
`REJECTED`. Transitionen (gate-gebunden, `TRANSITIONS`-Tabelle):

| Von | Nach | Gate |
|---|---|---|
| DRAFT | CANDIDATE | gültiger Contract + Ein-Komponenten-Delta |
| CANDIDATE | SHADOW | OFFLINE EVAL + VALIDATION bestanden, kein Leakage |
| SHADOW | CANARY | HOLDOUT bestanden, keine Regression |
| CANARY | ACTIVE | **nur** `promote()` mit Autoritäts-Token |
| * | RETIRED / REJECTED | explizite Stilllegung / Gate-Fehler, Regression, Leakage, NOT_PROVEN |

`add()` akzeptiert neue Einträge nur als `DRAFT` oder `CANDIDATE` —
`INITIAL_STATUS_FORBIDDEN` verhindert Selbst-Promotion an der API-Oberfläche.
Identität: `identity_key = provider|model|model_revision|task_class|runtime_mode`.
Jeder Wechsel auf ACTIVE setzt den bisherigen ACTIVE-Eintrag derselben
Identität auf RETIRED und schiebt ihn auf `active_history` (Snapshot für
Rollback).

### promote() mit Autoritäts-Token

```python
from hamh import registry

reg = registry.HarnessRegistry(
    path="/var/lib/autodev-harness-v2/hamh-registry.json",
    authority_token=os.environ["HAMH_AUTHORITY_TOKEN"],
)
r = reg.promote("deepseek/v4-flash/build/v2", authority_token)
# {"ok": True, "harness_id": ..., "status": "ACTIVE"}
```

Fehlercodes: `PROMOTE_DENIED` (falsches/fehlendes Token), `PROMOTE_FROM_CANARY_ONLY`
(nur CANARY → ACTIVE), `NOT_FOUND`. `transition()` mit `new_state="ACTIVE"`
und `cur != "CANARY"` liefert `PROMOTE_FROM_CANARY_ONLY`; ohne Token
`PROMOTE_DENIED`.

**Autoritäts-Token konfigurieren:** Konstruktorparameter `authority_token`
(zweites Argument). Empfehlung für Produktion — analog zu den Adapter-Tokens:

- separates Secret, Datei mit Mode 0600 unter `/var/lib/autodev-harness-v2/`
  (z. B. `hamh-authority-token`), beim Prozessstart gelesen, nie im Repo,
  nie in Logs/Prozesslisten.
- Vergleich erfolgt konstantzeit-sicher via `hmac.compare_digest`.
- Kein Token setzen, solange keine autorisierte Promotion gewollt ist
  (Secure Default = deny).

### JSON-Datei-Layout

```json
{
  "entries": { "<harness_id>": { ...hamh.harness.v1... } },
  "active_history": { "<identity_key>": [ ...ACTIVE-Snapshots... ] },
  "saved_at": "2026-08-20T00:00:00Z"
}
```

Schreiben ist atomar: `.tmp` + `fsync` + `os.replace`. Lesen/Schreiben
erfolgen als Deep-Copy (Isolation A/B: keine Mutation zwischen Zellen).

- **Thread-Safety:** `HarnessRegistry` nutzt ein `RLock` — `add()`/`save()`
  sind thread-sicher (parallele Adds korrumpieren den Store nie).
- **Korrupte Datei:** Eine defekte Registry-Datei wird beim Laden gesichert
  (`<pfad>.corrupt-<timestamp>`) und mit leerer Registry gestartet — ein
  defektes Registry-JSON darf den Dispatch nie brechen.
- Das `_opencode_sem`-Fix-Detail gehört zu Troubleshooting (siehe dort).

### rollback()

```python
r = reg.rollback("deepseek/v4-flash/build/v2", authority_token)
# {"ok": True, "restored_harness_id": "..."}  # exakt vorherige ACTIVE-Konfiguration
```

Rollback ist eine Promotionsklassen-Operation und verlangt das
Autoritäts-Token (`ROLLBACK_DENIED` sonst). Stellt **exakt** den vorherigen
ACTIVE-Eintrag derselben Identität wieder her (AC-8): aktueller Halter wird
RETIRED (`ROLLED_BACK`), Snapshot wird ACTIVE (`RESTORED_BY_ROLLBACK`).
`NO_PREVIOUS_ACTIVE` wenn keine Historie existiert.

## Resolver-Betrieb

`resolve(...)` ist eine reine Funktion der Inputs (AC-9). Signatur:

```python
from hamh import resolver

out = resolver.resolve(
    provider="deepseek",
    model="deepseek-v4-flash",
    task_class="build",
    runtime_mode="thinking",
    model_revision="0731",
    registry=reg,                 # optional; ohne Registry -> Baseline
    controller_allowlist=None,    # optional; Default aus profiles.CONTROLLER_ALLOWED_TOOLS
)
# out["resolved_harness_id"], out["fingerprint"], out["effective_tool_profile"], ...
```

Aufrufbeispiel im Adapter (Dispatch, `harness_adapter_v2.py`): `resolve(
eff_provider, eff_model, eff_task_class, "auto", model_revision=model_revision,
registry=_hamh_registry)` — die Registry wird aus
`<STATE_DIR>/hamh/registry.json` geladen; ein ACTIVE-Eintrag für die Identität
wird also tatsächlich aufgelöst. Ohne Registry-Datei oder ohne passenden
ACTIVE-Eintrag greift der explizite Baseline-Fallback (unbekanntes Modell →
kein Crash, kein Zufall, AC-5).

Baseline-Fallback-Semantik: `is_fallback=true`,
`resolved_harness_id = baseline/shared/default/<runtime_mode>/<task_class>`,
`fallback_profile = {name: "baseline", reason: "no ACTIVE harness for
identity (explicit fallback)"}`. Nur ACTIVE-Einträge werden aufgelöst;
RETIRED/REJECTED/DRAFT/CANDIDATE/SHADOW/CANARY nie — Ausnahme: explizites
Replay/Audit via `resolve_replay(registry, harness_id)`. Der Resolver ändert
nie `backend` (ROUTING_AUTHORITY).

### Debug: Resolution-Artefakt

Je Run aggregiert der Adapter die Auflösungen nach Job:

```
GET /v1/artifacts/<run_id>/hamh_resolution      # http://192.168.1.136:8081
```

Datei: `/var/lib/autodev-harness-v2/artifacts/<run_id>/hamh_resolution.json`,
je `job_id` die Felder `resolved_harness_id`, `harness_version`, `fingerprint`,
`provider`, `model`, `model_revision`, `task_class`, `runtime_mode`,
`is_fallback`. Wenn dort `is_fallback=true` steht, war zum Dispatch kein
ACTIVE-Harness für die Identität vorhanden (erwartetes Verhalten im
Baseline-Deploy).

## Adapter-Deployment (pve)

Der Import sucht das `hamh/`-Paket an drei Stellen: `<adapter_dir>/hamh`
(Deploy-Layout), `<adapter_dir>/../runtime` und `<adapter_dir>/../runtime/hamh`
(Repo-Layout). Ebenso liegt `contracts/` neben dem Adapter für
`from contracts import registry`.

**Registry-Datei:** Nach dem Deploy die Registry-Datei unter
`/var/lib/autodev-harness-v2/hamh/registry.json` ablegen. Eine korrupte
Registry-Datei wird beim Laden gesichert (`<pfad>.corrupt-<timestamp>`) und
mit leerer Registry gestartet — ein defektes Registry-JSON darf den Dispatch
**nie** brechen.

Ziel auf pve: `/opt/autodev-harness-v2/` (systemd-Unit
`autodev-harness-v2`, `ExecStart=/usr/bin/python3
/opt/autodev-harness-v2/harness_adapter_v2.py`).

### Deploy-Schritte

1. Artefakte in das Adapter-Verzeichnis übertragen (Workstation → pve,
   192.168.1.136), z. B. via `scp`/`rsync`:
   - `runtime/hamh/` → `/opt/autodev-harness-v2/hamh/`
   - `runtime/contracts/` → `/opt/autodev-harness-v2/contracts/`
   - `adapter/harness_adapter_v2.py` → `/opt/autodev-harness-v2/`
2. Vorher: aktuelle Dateien sichern (Rollback-Basis, z. B. Tarball im
   State-Verzeichnis).
3. Service neu starten:
   `ssh pve 'systemctl restart autodev-harness-v2'`
   (In-flight-Jobs werden als `interrupted`/`INFRA_FAILURE` markiert —
   Restart-Recovery, identisch zu v2.)
4. Healthcheck: `GET http://192.168.1.136:8081/healthz` muss 200 liefern.

### Rollback-Schritte

1. Gesicherte Vorversionen (Adapter, `hamh/`, `contracts/`) zurückkopieren.
2. `ssh pve 'systemctl restart autodev-harness-v2'`.
3. Healthcheck + Adapter-Suite-Regression (siehe Tests).

### Freigabe (Pflicht)

**KEIN Redeploy ohne Freigabe.** Der Adapter-Deploy ist eine
Produktionsänderung auf pve; er erfolgt erst nach dokumentierter Freigabe
(Schritt im Runbook, kein automatischer Schritt im Build-Lauf). Ohne Freigabe
bleibt der Adapter im v2-Baseline-Verhalten (Resolver nicht deployed →
Resolution übersprungen, `hamh_resolver = None`).

## Workflow-Generator

Workflow-Änderungen ausschließlich über den Generator (ADR H14), nie durch
Handeditieren exportierter JSONs.

### Lokale Regeneration (kein Redeploy)

```text
python3 workflow/v2/generate_workflows_v2.py workflow/v2/config.json <outdir>
```

Config: `workflow/v2/config.json` (n8n/adapter/webhook-Basen, Tabellen-IDs,
Credential-IDs). Exporte nach `<outdir>` (Produktions-Exporte:
`n8n/workflows/autodev/*.json`). Diff prüfen: nur additive Felder
(provider/model/model_revision/task_class in Prep-Nodes).

### Deploy auf pve (Freigabeschritt)

```text
python3 workflow/v2/create_workflows_v2.py <repo> <exportdir>
```

läuft auf pve, liest Secrets aus Dateien (nie argv), legt Tabellen/
Credentials an, generiert, erstellt/aktualisiert die 12 Workflows per Public
API, aktiviert 00/01/02 und exportiert die finalen JSONs zurück.

**Hinweis:** Der n8n-Deploy ist eine Produktionsänderung (Workflow-
Aktualisierung auf dem Live-n8n 192.168.1.52) und erfordert dieselbe
Freigabe wie der Adapter-Deploy. Lokale Regeneration allein ist kein Deploy.

## DeepSeek-Betrieb

**Kein Credential vorhanden** (`.secrets/` enthält nur autodev_api_token,
harness_token, harness_token_v2) → `DEEPSEEK_LIVE_PROOF=NOT_RUN`; der
DeepSeek-Model-Adapter ist reine Semantik + Contract-Tests, keine
Live-Netzwerkaufrufe (`deepseek_adapter.py`).

### Bereitstellung, FALLS ein Credential je kommt

```text
export DEEPSEEK_API_KEY='sk-...'
python3 evidence/scripts/deepseek_live_smoke.py
```

Der Smoke-Script verifiziert den vom Adapter kodierten Contract (Thinking,
Tool-Call-Round-Trip, 400-Regel-Echo-Back, Folge-Tool-Turn, Audit-Trail als
JSONL unter `evidence/phase-d-hamh/results/deepseek-live-smoke.jsonl`).
Ohne `DEEPSEEK_API_KEY` bricht das Skript mit Exit-Code 2 ab und meldet
`DEEPSEEK_LIVE_PROOF=NOT_RUN`. Ausgabe-Verdikte: `GREEN_DEEPSEEK_LIVE_SMOKE_PASS`
bzw. `RED_DEEPSEEK_LIVE_SMOKE_*`. Erst nach grünem Smoke darf über ein
Registry-Harness für `deepseek-v4-flash` nachgedacht werden; eine Promotion
bleibt gate-gebunden (DRAFT → … → ACTIVE).

### Concurrency-Limits (Account-Level, hart in `MODEL_IDS`)

| Modell | Concurrency-Limit | Context | Max-Output |
|---|---|---|---|
| deepseek-v4-flash | 2500 | 1M | 384K |
| deepseek-v4-pro | 500 | 1M | 384K |

### Fehlertabelle (nur HTTP-Status; `map_http_error`)

| Status | Name | Retry | Aktion |
|---|---|---|---|
| 400 | INVALID_FORMAT | nein | FIX_REQUEST |
| 401 | AUTHENTICATION_FAILS | nein | HALT |
| 402 | INSUFFICIENT_BALANCE | nein | HALT_ESCALATE |
| 422 | INVALID_PARAMETERS | nein | FIX_REQUEST |
| 429 | RATE_LIMIT_REACHED | ja | BACKOFF_RETRY |
| 500 | SERVER_ERROR | ja | BACKOFF_RETRY |
| 503 | SERVER_OVERLOADED | ja | BACKOFF_RETRY |
| sonst | UNKNOWN_HTTP_<code> | nein | HALT |

Tool-Turn-Regel: bei gesetzten `tools` muss `reasoning_content` in allen
Folge-Requests zurückgegeben werden, sonst HTTP 400 (offline prüfbar via
`validate_tool_turn_chain`).

### Namenskollision

„DeepSeek Harness" ist ein offizielles, separates DeepSeek-Produkt
(Developer Preview). Den nackten Namen nie verwenden; immer „HAMH" bzw.
„DeepSeek-Model-Adapter" (H6).

## Tests

Alle Kommandos aus dem Repo (Lauf aus dem Repo-Root). Referenz-Evidenz:
`evidence/phase-d-hamh/results/`.

| Suite | Kommando | Stand (2026-08-20) |
|---|---|---|
| Contracts (inkl. 2 HAMH-Contracts) | `python3 runtime/tests/test_contracts.py` | 34/34 PASS |
| Validator-Äquivalenz Py/JS | `python3 runtime/tests/test_validator_equivalence.py` | 34/34 PASS (requires node; inkl. 7 HAMH-Fixtures) |
| Adapter-Suite (Regression) | `python3 evidence/tests/v2/adapter_suite.py` | 23/23 LIVE, 7 NOT_RUN |
| Control-Plane-Matrix (Regression) | `python3 evidence/tests/v2/control_plane_e2e.py` | 9/9 PASS |
| Isolation A–H | `python3 evidence/tests/hamh/test_isolation.py` | 14/14 PASS |
| Registry (AC-3/8/10) | `python3 evidence/tests/hamh/test_registry.py` | 22/22 PASS (inkl. corrupt-file + thread-safety) |
| Resolver (AC-4/5/6/9) | `python3 evidence/tests/hamh/test_resolver.py` | 14/14 PASS |
| Evolution-Sandbox | `python3 evidence/tests/hamh/test_evolution.py` | 21/21 PASS |
| Capability vs. Harness | `python3 evidence/tests/hamh/test_capability_vs_harness.py` | 11/11 PASS |
| DeepSeek-Adapter (offline) | `python3 evidence/tests/hamh/test_deepseek_adapter.py` | 33/33 PASS |
| Adapter-Naht (in-process, tmp State) | `python3 evidence/tests/hamh/test_adapter_hamh_seam.py` | 20/20 PASS (inkl. Registry-Verdrahtung Ende-zu-Ende: vorbefüllter ACTIVE-Eintrag wird am Dispatch aufgelöst, `is_fallback=false`; plus opencode-Backend-Default-Identität `lmstudio/<modell>`) |
| Telemetry (Privacy-Sentinel) | `python3 evidence/tests/hamh/test_telemetry.py` | 29/29 PASS (Top-Level-`ValueError` + nested `sanitize`) |
| Task-Suite (Governance ohne LLM) | `python3 evidence/tests/hamh/task_suite.py` | 24/24 PASS |

Hinweise:

- **Callback-Sink (192.168.1.195):** Die Adapter-Suite bindet für den
  Duplicate-Callback-Test einen Sink auf `192.168.1.195:18091`. Die
  Maschine ist offline → `OSError: Cannot assign requested address`, 7 Tests
  NOT_RUN (dokumentiert, kein Harness-Defekt).
- `test_adapter_hamh_seam.py` startet den Adapter in-process mit tmp State
  (kein Live-pve) — Backend-Routing bleibt unverändert.
- `task_suite.py` beweist die komplette Promotionskette deterministisch mit
  Stub-Modell + Hidden-Tests-Verifier, schreibt `task-suite-result.txt`.

## Betriebs-Sentinels (Invarianten — was HAMH niemals darf)

| Sentinel | Verletzung erkennen an |
|---|---|
| MODEL_SELF_PROMOTION = DENIED | `promote()` ohne/mit falschem Token → `PROMOTE_DENIED`; kein Zustandswechsel; `add()` mit status ACTIVE → `INITIAL_STATUS_FORBIDDEN` |
| EVOLVER_CAN_PROMOTE / CHANGE_GATES / CHANGE_HOLDOUT = NO | `EvolutionSandbox`-Konstanten (`evolution.py`); `change_holdout()` → `HOLDOUT_LOCKED` |
| effective_tools ⊆ controller_allowed_tools | `effective_tools()`-Schnittmenge; `restricted_by_controller=true` bei Verengung; unbekannte Profil-Tools werden verworfen |
| ROUTING_CHANGE = DENIED | Resolver-/Adapter-Code ändert nie `backend`; `VALID_BACKENDS` unverändert `{"embedded","opencode-builder-8001"}` |
| CONTROLLER_AUTHORITY / VERIFIER_AUTHORITY / RETRY_ESCALATION_SEPARATION / MCP_SECURITY_BOUNDARY / PRODUCTION_SENTINELS | Generator-Exporte: nur additive HAMH-Felder; Plan-Canary + write_attempts unverändert; keine neuen Gate-LLM-Urteile |
| AUDITABILITY / Privacy by Default | `telemetry.build_trajectory()` lehnt `DENIED_KEYS` top-level per `ValueError` ab **und** wendet `sanitize()` rekursiv auf den finalen Record an (nested bypass geschlossen); `test_telemetry.py` beweist beides; Ledger metadata-first |
| Artifact-GET-Pfadvalidierung | `GET /v1/artifacts/<run_id>/<name>` validiert `run_id` + `name` per Regex (wie POST) — Defense-in-Depth gegen Pfad-Traversal |
| Leakage-Sentinel | `propose()` mit Holdout-Bezug im Kandidatenmaterial → `LEAKAGE_REJECTED` |
| Ein-Komponenten-Regel | `propose()` mit mehr als einer Komponente → `ONE_COMPONENT_RULE` |
| Matched-Compute | `matched_compute_verdict()` → `NOT_PROVEN`, wenn B nicht A schlägt oder C den Effekt erklärt |
| CAPABILITY_FAILURE → Routing | `taxonomy.classify()` → `escalate=True` nur für CAPABILITY_FAILURE; kein Endlos-Evolutions-Loop |
| ROLLBACK | `rollback()` stellt exakt die vorherige ACTIVE-Konfiguration wieder her (AC-8) |

Regelmäßige Prüfung: Registry-JSON (Mode 0600, keine fremden ACTIVE-Einträge
ohne `AUTHORIZED_PROMOTION`-Herkunft), Resolution-Artefakte (`is_fallback`),
Ledger/Trajektorien-Scan auf `DENIED_KEYS`, Test-Suiten grün.

## Troubleshooting

- **pve-Disk voll:** Ursache des Adapter-Crash-Loops nach Suite-Neustart
  (2026-08-20). Dokumentierte Minimalintervention (nur Log-Rotation, keine
  Produktionsdaten):
  `ssh pve 'journalctl --vacuum-size=200M'`
  Danach `ssh pve 'systemctl restart autodev-harness-v2'` und Healthcheck.
- **`_opencode_sem`-Historie:** In der v2-Basis war `_opencode_sem`
  referenziert (Z. ~425/436/449), aber nie definiert — jeder echte
  opencode-Dispatch hätte `NameError` geworfen. Im HAMH-Seam nachgezogen:
  `_opencode_sem = threading.BoundedSemaphore(1)` (Serialisierung pro
  Backend, H15). Beim Deploy sicherstellen, dass die Adapter-Datei diese
  Definition enthält (Zeile ~144). Zusätzlich wurde der unbalancierte
  `_opencode_sem.release()` im KeyError-Pfad (Job-Typ ohne Executor)
  **entfernt** — er hätte `ValueError` ausgelöst und Jobs in "running"
  hängen lassen; der Pfad finalisiert jetzt sauber auf
  `failed`/`UNKNOWN_JOB_TYPE`.
- **Unbekanntes Modell / kein ACTIVE:** kein Fehler, sondern expliziter
  Baseline-Fallback (`is_fallback=true`) — Debug über
  `GET /v1/artifacts/<run_id>/hamh_resolution`.
- **Bekannte Limitationen (ehrlich, H13):**
  - `HARNESS_VALUE=NOT_PROVEN`: ohne Live-Modelle kein Value-Beweis;
    Klassifikation `AMBER_HAMH_VALUE_NOT_PROVEN`.
  - `DEEPSEEK_LIVE_PROOF=NOT_RUN`: kein Credential, LM Studio offline,
    Builder-CT 8001 gestoppt.
  - `GREEN_HAMH_DEEPSEEK_V4_FLASH_RUNTIME_PROVEN` und
    `GREEN_HAMH_VALUE_PROVEN` sind in diesem Lauf **nicht** erreichbar und
    werden nicht behauptet.
  - Adapter-Suite: 7 Callback-Tests NOT_RUN (Sink 192.168.1.195 offline).
