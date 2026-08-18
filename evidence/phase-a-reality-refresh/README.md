# Phase A — Reality Refresh (2026-08-16)

Alle Befehle read-only. Keine Mutationen.

## Proxmox
- Hostname: pve
- Version: pve-manager/8.4.19/a68fb383814bb1e6, Kernel 6.8.12-32-pve

## CT 101
- ID: 101, Name: lxc-n8n-local, Status: running
- arch amd64, 2 cores, 1536 MB RAM, rootfs local-lvm 16G, onboot=1, unprivileged=1
- net0: eth0/vmbr0, hwaddr BC:24:11:96:3D:9A, ip=dhcp

## IP-Beweis CT101 -> 192.168.1.52
- `pct exec 101 -- hostname -I` => 192.168.1.52 (einzige v4-Adresse)
- IPv6 EUI-64: be24:11ff:fe96:3d9a == EUI-64 aus MAC BC:24:11:96:3D:9A
- n8n-Prozess läuft IN CT 101 (PID 3875, node /usr/bin/n8n start, User n8n),
  N8N_HOST=0.0.0.0, N8N_PORT=5678, WEBHOOK_URL=http://192.168.1.52:5678/
- http://192.168.1.52:5678/healthz => {"status":"ok"} (von Workstation aus)
=> CT101_IP_MAPPING = PASS

## n8n Runtime
- n8n 2.26.8, node v22.23.0, systemd-Service "n8n" active (PID 3875)
- HOME=/opt/dev-fabric/n8n, N8N_USER_FOLDER=/opt/dev-fabric/n8n/data
- GENERIC_TIMEZONE=Europe/Berlin
- N8N_ENCRYPTION_KEY in Prozess-Env LEER (Wert nicht abgreifbar/ausgegeben)
- DB-Pfad (fd-Beweis): /opt/dev-fabric/n8n/data/.n8n/database.sqlite (+wal/shm)
- Task-Runner-Prozess vorhanden (n8n task-runner, PID 3889)
- Public API: /api/v1/ (JWT-Key), /rest/ => 401. settingsMode=public.

## Workflow-Baseline (vor Änderung)
- Total workflows: 40 (via GET /api/v1/workflows)
- Relevant:
  - GHIW-10 — Issue Intake Firewall (AUTHORITATIVE) + v3 Builder Lifecycle
    id=ghiw-10-issue-intake-firewall-auth, active=true, 36 nodes,
    Webhook: ghiw-e7-runtime-canary (POST), tags source-of-truth,dispatcher,github
  - GHIW Blueprint Intake (DRY RUN): id=ghiw-blueprint-intake-dryrun, active=false, 9 nodes,
    Webhook: blueprint-intake (POST)
  - GHIW-70 — Release / Canary Orchestrator: id=ghiw-70-release-canary-orchestrator, active=false, 4 nodes
  - N8N-OPS-03 — Release Notes & Documentation Sync: id=n8n-ops-03-release-notes-docs, active=false, 4 nodes
- Weitere aktive Workflows (7): My workflow 2, blueprint-speckit-bootstrap-v2,
  blueprint-speckit-opencode-bootstrap, ghiw-60-orphan-watcher, n8n-ops-01-gitops-guardian,
  n8n-ops-02-dead-man-sentinel, n8n-ops-04-dr-restore-drill
- Bestehende Webhook-Pfade (Kollisions-Check): ghiw-e7-runtime-canary, blueprint-intake,
  blueprint-speckit-opencode-project-builder => "autodev-harness" ist FREI

## Execution-Stats (DB, read-only)
- mode: trigger=1148, webhook=50, cli=3 => total 1201
- status: success=1141, error=60
- avg runtime (success): 3.68 s
(Screenshot-Baseline 1165/55/4.7 % war älter; Live-Werte hier dokumentiert)

## Builder 8001 (Execution Backend Kandidat)
- Status: running, hostname ghiw-bld-e3r6-canary-001-8001
- OpenCode v1.17.9: /opt/dev-fabric/opencode/opencode (166 MB) — vorhanden
- /usr/local/sbin/ghiw-builder-wrapper — vorhanden (ghiw-builder-v1: health/run-task/status/cleanup,
  Task-Allowlist: ghiw_source_manifest_v1; Repo-Allowlist: xxammaxx/Positron, xxammaxx/n8n-blueprint-workflow)
- Workspaces: /var/lib/ghiw/workspaces (e3r6-canary-001, E5R1-PILOT-34, GHIW-E4-..., GHIW-PROD-E4-R7-...)
- Secrets-Contract vorhanden; opencode-provider.env NICHT provisioniert (per Design)

## Registry (Host, read-only)
- 11 Builder registriert: bld-8001..8011, alle current_state=BUILDER_READY

## OpenCode-Runtime-REUSE-Pfad (E7-Canary)
- /opt/ghiw-provisioner/harness/run_builder_e7_canary.sh — vollständiger bestehender
  OpenCode-Invocations-Pfad: Workspace-Clone + OCAE-Governance-Overlay (Pinned Agent
  issue-orchestrator, ScopeGate, Secret-Scan) + lokale LLM-Anbindung
  (GHIW_LMSTUDIO_BASE_URL=http://192.168.1.195:1234, Modell qwen/qwen3.5-9b,
  Timeouts 240s/900s) + deterministischer Verifier (verification.json)
- LM Studio erreichbar: http://192.168.1.195:1234/v1/models => ok (u.a. qwen/qwen3.5-9b)
- Registry-Schema: builders.current_state (nicht "state")
