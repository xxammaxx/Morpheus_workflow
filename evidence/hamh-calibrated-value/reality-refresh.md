# HAMH Calibrated Value Discovery — Reality Refresh

Datum: 2026-08-21 (Run: HAMH_CALIBRATED_VALUE)
Autor: Issue-Orchestrator (evidence-gated, keine Mocks, keine Secrets)

## Repository-Zustand

| Feld | Wert |
|---|---|
| REPOSITORY | /media/xxammaxx/projekte/N8N/Morpheus_workflow |
| BRANCH | master |
| START_HEAD | f7caeedd1447712e3879b8c8973a811de19368f7 |
| GIT_STATUS | unversioniert: .opencode/, .playwright-mcp/ (Lauf-Artefakte), evidence/backup/v3-backup-20260819/ (fremd, unangetastet) |
| WORKTREE | unverändert; keine fremden Änderungen |
| GIT_REMOTE | KEINER (kein Remote konfiguriert; lokale Git-Historie + Evidence-Artefakte sind Source of Truth, Run Card §41) |
| PREVIOUS_RUN_EVIDENCE | evidence/hamh-real-testing/ (final-report.md, value-analysis.md, holdout/ 24 Tasks, live/, fixtures/) |

GitHub-Quelle: Kein Remote-Repository konfiguriert und kein gh-Credential-Zugriff eingerichtet — der GitHub-Issue-Zyklus (github-source-of-truth) ist in dieser Umgebung nicht anwendbar; die Evidence-Artefakte im Repo übernehmen die Rolle der externen Nachvollziehbarkeit (etablierte Konvention aus HAMH_REAL_TESTING, siehe dessen final-report.md Zeile 15).

## Runtime-Realität (live verifiziert 2026-08-21)

| Feld | Wert |
|---|---|
| CURRENT_PRODUCTION_BASELINE | AutoDev-Harness v2 Chain: n8n Workflows 00-90 (20+ aktiv), Controller = "01 AutoDev Orchestrator", Build-Dispatch = Job-Server 192.168.1.136:8081/v1/jobs, Builder = opencode + DeepSeek |
| HAMH_SERVICE | hamh-resolver.service ACTIVE auf 192.168.1.136:8090, healthz HTTP 200, version 1.0.0 |
| HAMH_REGISTRY | /opt/dev-fabric/hamh/state/registry.json (2660 B, mtime 2026-08-21 01:27 UTC) |
| HAMH_ACTIVE_FINGERPRINT | a1e6955fa0f1aadf099a331f7c34d6068445fa221ef82827c459d07e15625271 (live via POST /v1/resolve bestätigt, is_fallback=false, resolved_harness_id=hamh/baseline/deepseek-v4-flash/build/thinking/v1) |
| HAMH_ACTIVE_HARNESS_ID | hamh/baseline/deepseek-v4-flash/build/thinking/v1 |
| OPENCODE_RUNTIME | opencode **1.15.13** (ABWEICHUNG: vorheriger Run 1.17.9 — Runtime-Revision geändert; Baseline-Fingerprint muss für diese Runtime neu eingefroren werden, Run Card §16) |
| OPENCODE_AGENT | build (primary, vorhanden in 1.15.13, permissions: allow all, doom_loop ask) |
| OPENCODE_VARIANT | --variant unterstützt (high/max/minimal) — nutzbar für Matched-Compute Bedingung C |
| DEEPSEEK_MODEL | deepseek/deepseek-v4-flash im opencode Model-Registry gelistet (`opencode models` live) |
| DEEPSEEK_CREDENTIAL | ~/.local/share/opencode/auth.json vorhanden, Mode 600; Inhalt nicht ausgegeben; Live-Beweis folgt via Smoke (kein Secret in Artefakten) |
| N8N_HEALTH | Host-Service inactive (n8n läuft in LXC 101, 192.168.1.52:5678; Port 5678 auf 192.168.1.136 nicht offen = erwartet, keine Regression) |
| ADAPTER_HEALTH | HAMH-Adapter nicht als Systemd-Service deployt (Repovorlagen; etablierter Zustand) |
| JOB_SERVER | 192.168.1.136:8081 antwortet (UNAUTHORIZED ohne Token = erwartet, Service läuft) |
| PRODUCTION_HOST | pve (192.168.1.136): root-FS **100 % voll** (68G/68G, 0 frei) — Vorfall aus HAMH_REAL_TESTING wieder aufgetreten; Inodes 8 %; RAM 2466 MB available; hamh-resolver active |

## Bewertung für diesen Run

- Die Trajektorien-Runs (opencode auf der Workstation, /tmp/opencode, Workstation-Disk GREEN mit 481G frei) sind NICHT vom pve-Root-FS abhängig.
- pve-Root-FS 100 % => BLOCK_HAMH_EXPERIMENT für SCHREIB-Operationen auf dem Produktionshost (Registry-Update/Promotion nur über autorisierten Pfad; kein Registrierungs-Schreibversuch ohne freien Platz — dokumentiert, keine Produktionsdaten löschen, Run Card §5).
- Resolver-READ (POST /v1/resolve) läuft nachweislich weiter und ist für die Eval-Pipeline ausreichend.
- Runtime-Revision (opencode 1.15.13) weicht vom vorherigen Run ab => Baseline wird für DIESE Runtime neu eingefroren (Baseline-Manifest, Run Card §16); der vorherige Fingerprint a1e6955f… bleibt als historischer Eintrag bestehen.

## Nicht-Ziele (Run Card §3)

Bestätigt: keine neuen Provider/Modelle/DB/Router/Verifier/Retry-Systeme/MCP-Systeme/Control-Plane; keine großflächige HAMH-Refaktorierung. Backbone bleibt deepseek-v4-flash.

## Kosten-Rahmen (Run Card §40)

- MAX_EXTERNAL_API_COST = 10 USD equivalent (Default der Run Card; vorheriger Run ~0.16 USD — Restbudget reicht für diesen Run)
- Cost-Accounting auf echten Usage-Daten mit Pricing-Snapshot 2026-08-20 (off-peak): cache-hit $0.007/1M, cache-miss $0.22/1M, output $0.66/1M
