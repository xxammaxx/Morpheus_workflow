# AutoDev Harness v2 — Betriebsanleitung (Operations)

Kurzreferenz für Betrieb und Test des AutoDev-Harness-v2-Control-Plane.

## Komponenten

| Komponente | Ort | Hinweise |
|---|---|---|
| n8n Control Plane | http://192.168.1.52:5678 | 12 Workflows `00`–`90` (alle aktiv) |
| Harness Adapter v2 | http://192.168.1.136:8081 | systemd `autodev-harness-v2` auf pve |
| Adapter State | `/var/lib/autodev-harness-v2/` | Token (0600), Ledger `logs/runs.jsonl`, Workspaces |
| Builder CT 8001 | ghiw-bld-e3r6-canary-001-8001 | OpenCode 1.18.22, local Ollama formatter (LM-Studio remains an available worker route) |
| LM Studio | deployment-configured via `LMSTUDIO_BASE_URL` | Modell via `AUTODEV_LMSTUDIO_MODEL` (Context 32768) |
| Run-State | n8n Data Tables `autodev_runs`, `autodev_attempts` | Public-API-Tabellen |
| Credentials | n8n: `autodev-n8n-api`, `autodev-harness-token`, `autodev-api-auth` | httpHeaderAuth, Werte nur im Credential Store |

### OpenCode-Fleet (Produktionsstand 2026-08-24)

| Container | Rolle | Binary-Pfad | Installations-/Upgrade-Methode | Rollback |
|---|---|---|---|---|
| CT 8001 (`ghiw-bld-e3r6-canary-001-8001`) | aktiver Builder / OpenCode-Worker | `/opt/dev-fabric/opencode/opencode` (PATH-Symlink `/usr/local/bin/opencode` → `/opt/opencode/1.18.22/opencode`) | offizielles Release-Asset `v1.18.22`, funktional via lokalem Ollama-OpenAI-kompatiblem Endpoint geprüft | containerinterner Backup-Satz `/root/morpheus-opencode-backup-20260824/`; Binary und Symlink atomar auf den vorherigen Stand zurücksetzen |

Nur aktive Produktionsinstanzen werden aktualisiert. Gestoppte Golden Templates und historische Canary-CTs bleiben unverändert. Vor jedem Upgrade sind laufende OpenCode-Prozesse, Binär-Hashes, Symlink-Ziel sowie Konfigurations-/Plugin-Metadaten zu sichern; Auth-Inhalte werden weder ausgegeben noch versioniert. Nach dem Upgrade müssen beide Pfade `1.18.22` melden, `opencode --help`, Konfigurationsauflösung, Plugin-/Agent-Laden, lokale Ollama-Ausführung und die JSONL-Eventtypen (`step_start`, `text`, `step_finish`) erfolgreich sein.

## API

```
POST /webhook/autodev/start          # Header X-AutoDev-Token
  {"task": {..., "task_description": "..."},
   "fixture": null | "invalid_plan"|"verify_fail_delta"|...,
   "backend": "opencode-builder-8001"|"embedded"}
  -> 200 {"run_id": "...", "status": "ACCEPTED", "status_url": "..."}

GET  /webhook/autodev/status?run_id=...   # Header X-AutoDev-Token
  -> {"run_id", "state", "current_job", "attempt", "decision",
      "reason_code", "result_ref", "updated_at"}
```

Terminale Zustände: `DONE` / `BLOCKED` / `SPLIT_REQUIRED` / `FAILED`.
Entscheidungen: `DONE` / `FIX` / `SPLIT` / `BLOCKED` (deterministische Policy).

## Adapter-Endpunkte (X-Harness-Token)

```
GET  /healthz
POST /v1/jobs          # run_id, job_id, job_type, attempt_id, input_contract, input, backend
GET  /v1/jobs/{job_id}
POST /v1/batches       # run_id, batch_id, jobs[], barrier
GET  /v1/batches/{batch_id}
POST /v1/artifacts/{run_id}/{name}
GET  /v1/artifacts/{run_id}/{name}
```

Jobtypen: baseline, research.code|docs|tests, plan, build, verify, fix,
review.correctness|security|quality. Backends: embedded, opencode-builder-8001.

## Wartung

- **Adapter neu starten**: `ssh pve 'systemctl restart autodev-harness-v2'`
  In-flight-Jobs werden als `interrupted`/`INFRA_FAILURE` markiert (Recovery).
- **Builder CT**: `pct reboot 8001` (bei hängendem pct exec; Canary-CT).
- **LM Studio**: `~/.lmstudio/bin/lms server start --bind 0.0.0.0`,
  `lms load "<configured-model>" --context-length 32768`.
  Set `LMSTUDIO_BASE_URL` and `AUTODEV_LMSTUDIO_MODEL` in the root-only
  `provider.env`; do not put a moving LAN address in source code.
- **Workflows aktualisieren** (nach Generator-Änderungen):
  `python3 workflow/v2/create_workflows_v2.py <repo> <exportdir>` auf pve.
- **Secrets**: `/var/lib/autodev-harness-v2/token`,
  `/var/lib/autodev-harness-v2/api-token`, n8n-Credential-Store.
  Nie in Logs oder Repo.

## Tests

- Contracts: `python3 runtime/tests/test_contracts.py`
- Validator-Äquivalenz (Py/JS): `python3 runtime/tests/test_validator_equivalence.py`
- Adapter-Suite: `python3 evidence/tests/v2/adapter_suite.py`
- Control-Plane-Matrix: `python3 evidence/tests/v2/control_plane_e2e.py`

## Fehlerklassen

TEST_FAILURE, BUILD_FAILURE, LINT_FAILURE, CONTRACT_FAILURE, CONTEXT_FAILURE,
PROVIDER_FAILURE, INFRA_FAILURE, TIMEOUT, SECURITY_BLOCK, UNKNOWN.
Provider-/Infra-Fehler werden nie als Modell-Unfähigkeit klassifiziert.
