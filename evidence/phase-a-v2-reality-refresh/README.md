# Phase A — Reality Refresh v2 (2026-08-17)

Read-only Zustandserfassung vor dem AutoDev-Harness-v2-Bau. Keine Secrets
enthalten. Credential-Werte wurden zu keinem Zeitpunkt gelesen.

## Erhoben

| Bereich | Befund |
|---|---|
| n8n Version | 2.26.8 (CT 101, lxc-n8n-local, 192.168.1.52) |
| Node.js | v22.23.0 (im CT) |
| Deployment | single `n8n start` Prozess, systemd `n8n.service`, Main-Mode (kein Queue) |
| Database | SQLite `/opt/dev-fabric/n8n/data/.n8n/database.sqlite` |
| Execution Mode | main (keine `EXECUTIONS_MODE`/`QUEUE_MODE`-Env) |
| n8n data dir | `/opt/dev-fabric/n8n/data/.n8n/` |
| WEBHOOK_URL | http://192.168.1.52:5678/ |
| OpenTelemetry | NICHT konfiguriert (keine N8N_OTEL_*-Env) — wird nicht aktiviert |
| SSRF | kein globaler Allow-/Blocklist konfiguriert; v1 nutzte 192.168.1.136:8080 erfolgreich |
| Public API | aktiv; Key auf pve: /var/lib/n8n-spec-kit/secrets/ghiw-n8n-api-key (nicht im Repo) |
| Workflows | 41 total (Backup: evidence/backup/v2-backup-20260817/), 9 active |
| Aktiv (Bestand) | My workflow 2; AutoDev Harness v1 (NdM7vcGvA4wkYswp); blueprint-speckit-bootstrap-v2; blueprint-speckit-opencode-bootstrap; ghiw-10-auth; ghiw-60; n8n-ops-01; n8n-ops-02; n8n-ops-04 |
| Credentials | 10 (nur Metadaten erfasst; Werte unberührt) |
| Projects | 1 personal project: `fLfBCnB9rifW9Cu2` |
| Data Tables | Public API vorhanden (`/api/v1/data-tables`, rows/columns/upsert); Tabellen `data_table`/`data_table_column` leer; **Feature-Lizenz empirisch zu testen** |
| Webhooks | 17 registriert; `autodev-harness` belegt (v1); `/autodev/start` + `/autodev/status` frei |
| execution_metadata | Tabelle vorhanden (optional für run_id-Korrelation) |
| Core Nodes | n8n-nodes-base + @n8n/n8n-nodes-langchain (keine Community-Packages) |
| v1 Adapter | pve 192.168.1.136:8080, systemd `autodev-harness.service` (active), Token 0600 unter /var/lib/autodev-harness/token |
| Builder CT 8001 | ghiw-bld-e3r6-canary-001-8001 (running); OpenCode 1.17.9 (/opt/dev-fabric/opencode/opencode); Agent `build` built-in; custom Agents via .opencode/agents; local_llm-Overlay unter /var/lib/ghiw/workspaces/provider-smoke-v3/local_llm |
| LM Studio | http://192.168.1.195:1234 (von pve: 200); Modelle: qwen/qwen3.5-9b, huihui-qwen3.5-9b-abliterated, deepseek/deepseek-r1-0528-qwen3-8b |
| pve Host | Python 3.11.2 (kein jsonschema → stdlib-Validator), git 2.47.3 |
| Backup | 41 Workflows JSON + Manifest in evidence/backup/v2-backup-20260817/ |

## Konsequenzen für den Bau

1. `QUEUE_MODE_MIGRATION = OUT_OF_SCOPE` (SQLite, Main-Mode) → echte Jobparallelität über Harness Adapter (Threads) + pct-exec-Worker.
2. Data Tables = bevorzugter State Store (§12) via Public API; Fallback = Adapter-Side State Store (SQLite/JSONL) auf pve, falls Lizenz-Gate greift. Empirischer Test in Phase C.
3. OTel nicht konfigurieren; Telemetrie metadata-first im Adapter (JSONL-Ledger) + execution_metadata-Korrelation.
4. v1 (Workflow NdM7vcGvA4wkYswp + Adapter 8080) bleibt unangetastet; v2 nutzt eigene Webhook-Pfade und einen separaten Adapter (Port 8081, eigener Token, eigener systemd-Service).
5. OpenCode native `plan` existiert nicht als built-in Agent → eigener read-only `plan`-Agent über natives Agenten-Mechanismus (wie v1 harness-worker); `build` built-in.
6. Real Parallelität: Adapter-Batch-Dispatch (Threads) + Barrier; n8n wartet an einem einzelnen Wait-Punkt (Callback-Resume via `$execution.resumeUrl`, Fallback Polling).
