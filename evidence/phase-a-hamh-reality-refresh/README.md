# HAMH Phase A — Reality Refresh (2026-08-20)

Kanoniche Bestandsaufnahme VOR jeder HAMH-Änderung. Quelle der Fakten:
frische git/ssh/curl-Erhebung am 2026-08-20, kein Gedächtnis.

## Repository

| Feld | Wert |
|---|---|
| Repository | /media/xxammaxx/projekte/N8N/Morpheus_workflow |
| Branch | master |
| START_HEAD | 7a65ad8 "AutoDev Harness v2: durable n8n control plane (contracts, adapter v2, 12 workflows, state machine, tests)" |
| Worktree | clean; UNTRACKED fremde Arbeit: `evidence/backup/v3-backup-20260819/` (GHIW-Workflow-Backups vom 19.08.) — wird NICHT angefasst, NICHT committed |
| Git-Remote | keiner (GitHub-Issue-Kommentarzyklus physisch nicht möglich; Abweichung dokumentiert: Evidence-READMEs sind Source of Truth) |
| Spec-System | kein Speckit; kanonisch: `docs/architecture/` ADRs + `evidence/phase-*` |

## Umgebung (live geprüft)

| Komponente | Status |
|---|---|
| pve 192.168.1.136 (ssh) | ERREICHBAR (v2-Infrablocker von 2026-08-17 aufgelöst) |
| n8n CT101 192.168.1.52 | HTTP 200 |
| Adapter v2 192.168.1.136:8081 | HTTP 200, systemd aktiv, Version 2.0.0 |
| LM Studio 192.168.1.195:1234 | OFFLINE (separate Maschine, ping fail) |
| Builder CT 8001 | stopped |
| .secrets/ | autodev_api_token, harness_token, harness_token_v2 — KEIN DeepSeek-Credential |

## CURRENT_RUNTIME

n8n Control Plane (12 codegenerierte Workflows 00–90, Generator
`workflow/v2/generate_workflows_v2.py` BUILDERS-Map) + Harness Adapter v2
(`adapter/harness_adapter_v2.py`, Python3-stdlib, pve :8081, Token-Auth,
append-only JSONL-Ledger mit fsync, Restart-Recovery, Idempotenzkey
`run_id:job_id:attempt_id`, Batch-Dispatch, Artifacts-Endpunkt) + Contracts
(`runtime/contracts/`: 12 autodev.*.v1-Schemas, Python/JS-Zwillingsvalidator,
kanonische SHA-256-Fingerprints). Kanonisches Prinzip:
`LLMs ARE WORKERS. LLMs ARE NOT THE CONTROLLER. n8n = CONTROL PLANE.`

## CURRENT_CONTROL_AUTHORITY

n8n Orchestrator (WF 01, 106 Nodes) treibt die Zustandsmaschine
deterministisch; Decision (WF 70) ist reine Policy DONE/FIX/SPLIT/BLOCKED.
Kein LLM-Urteil in Gates.

## CURRENT_MULTI_MODEL_ROUTER

KEINER. Backend-Allowlist `VALID_BACKENDS={"embedded","opencode-builder-8001"}`
(harness_adapter_v2.py:84); Provider/Modell hart kodiert
(`embedded` bzw. `lmstudio/huihui-qwen3.5-9b-abliterated`); `provider`/`model`
werden NICHT als Dispatch-Input akzeptiert (nur Observability-Felder).

## CURRENT_PROVIDER_LAYER

embedded (deterministische Fixtures) vs. opencode-builder-8001 (pct exec in
CT 8001 → OpenCode → LM Studio 192.168.1.195:1234). Latenter Bug:
`_opencode_sem` referenziert (Z. 425/436/449), nie definiert → NameError bei
jedem echten opencode-Dispatch.

## CURRENT_TOOL_LAYER

Kein MCP. Statische opencode-Agent-YAML (PLAN_TOOLS/PLAN_PERMS read-only,
BUILD_TOOLS write-erlaubt; bash/webfetch/task deny) in `_agent_md()`
(~Z. 821–900). Kein Tool-Registry, keine Capability/Präsentations-Trennung.

## CURRENT_CONTEXT_LAYER

Inline-f-string-Prompts je Job-Handler; ein `context.fingerprint`
(SHA-256 des Plan-Inputs). Keine stabil/variabel-Trennung, kein
Cache-Layout.

## CURRENT_VERIFIER

Deterministisch: `job_verify` (pytest, compileall, git-scope-Check) +
Plan-Gate (WF 30) + regelbasierte Reviews. Fehlerklassen: TEST/BUILD/LINT/
CONTRACT/CONTEXT/PROVIDER/INFRA_FAILURE/TIMEOUT/SECURITY_BLOCK/UNKNOWN.

## CURRENT_PRODUCTION_BASELINE

n8n 2.26.8 (41+12 Workflows), Adapter v2 2.0.0 auf pve :8081 (systemd
autodev-harness-v2), State `/var/lib/autodev-harness-v2/`, Data Tables
autodev_runs/autodev_attempts. Modell: huihui-qwen3.5-9b-abliterated
(Context 32768) via LM Studio. Beweis am 2026-08-20 frisch erbracht:
Control-Plane-Matrix 9/9 LIVE PASS, Adapter-Suite 23/23 LIVE PASS
(7 NOT_RUN: Callback-Sink-IP 192.168.1.195 offline).

## CURRENT_DEEPSEEK_PATH

KEINER (kein Code, kein Credential). Einzige Referenz: LM-Studio-Modelliste
in Evidence v2 enthält `deepseek/deepseek-r1-0528-qwen3-8b` (lokales
Distillat, NICHT DeepSeek-V4-API).

## INTEGRATION_SEAM

1. Adapter `_dispatch`/`do_POST` — akzeptiert heute kein provider/model →
   HAMH-Naht: optionale Felder + Resolver beim Dispatch.
2. Job-Record/Ledger (`new_job`/`finalize_job`) — Trageort für
   harness_id/version/fingerprint.
3. Generator-Prep-Nodes (build_single_job_workflow, Build/Verify/Fix-Prep,
   Research-/Review-Batch) — Durchreichung der HAMH-Identität.
4. `runtime/contracts/registry.py` CONTRACTS-Liste — +2 HAMH-Contracts.
5. Neue Schicht `runtime/hamh/` — Registry/Resolver/Profiles/Taxonomie/
   Evolution/Telemetrie/DeepSeek-Adapter.

## Stop-Gate-Befunde (dokumentiert, siehe Abschlussbericht)

- Kein DeepSeek-Credential → `DEEPSEEK_LIVE_PROOF=NOT_RUN`.
- LM Studio + CT 8001 offline → Value-Beweis über Live-Modelle nicht möglich.
- pve-Root-FS 100% voll (Ursache der Adapter-Crash-Loop nach
  Suite-Neustart) → mitigiert durch journalctl --vacuum-size=200M
  (nur Log-Rotation, keine Produktionsdaten), Adapter wieder aktiv.
