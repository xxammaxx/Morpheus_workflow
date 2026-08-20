# HAMH Real Testing — Reality Refresh

Datum: 2026-08-20 (Run: HAMH_REAL_TESTING)
Autor: Issue-Orchestrator (evidence-gated)

## Repository-Zustand

| Feld | Wert |
|---|---|
| REPOSITORY | /media/xxammaxx/projekte/N8N/Morpheus_workflow |
| BRANCH | master |
| START_HEAD | bd4fb51838b135e0055cb8820288dc0cc27663bf |
| GIT_STATUS | clean (nur unversioniert: .opencode/, .playwright-mcp/ Lauf-Artefakte, evidence/backup/v3-backup-20260819/ — fremd, unangetastet) |
| WORKTREE | unverändert, keine fremden Änderungen |
| GIT_REMOTE | KEINER (kein Remote konfiguriert; lokale Git-Historie + Evidence-Artefakte sind Source of Truth, §41) |

## Runtime-Realität (live verifiziert per SSH/Docker/API)

| Feld | Wert |
|---|---|
| CURRENT_PRODUCTION_BASELINE | AutoDev-Harness v2 Chain: n8n Workflows 00-90 (20+ aktiv), Controller = "01 AutoDev Orchestrator", Build-Dispatch = Job-Server 192.168.1.136:8081/v1/jobs, Builder = opencode-1.17.9 + local_llm Overlay |
| N8N_RUNTIME | LXC 101 "lxc-n8n-local" (192.168.1.52:5678), n8n 2.26.8, aktiv seit 2026-08-19 14:50 UTC, 60 Workflows, API-Key in /opt/dev-fabric/n8n/.env |
| ADAPTER_RUNTIME | NICHT als Service deployt auf Host/CTs (Systemd-Units nur als Repo-Vorlagen). Reale Modell-Ebene: local_llm Overlay (LM-Studio-kompatibler OpenAI-Client) in Builder-Containern + lokaler opencode 1.17.9 (Workstation) mit deepseek-Provider |
| HAMH_REPO_STATE | Implementiert: registry, resolver, profiles, taxonomy, evolution, telemetry, deepseek_adapter (Commits bf12e48..bd4fb51); 188/188 HAMH-Tests + 68/68 Regression bestanden; DEEPSEEK_LIVE_PROOF=NOT_RUN |
| CURRENT_DEEPSEEK_ADAPTER | runtime/hamh/deepseek_adapter.py — offline, offizielle Semantik 2026-08-20 |
| CURRENT_HAMH_REGISTRY | runtime/hamh/registry.py — JSON-backed, States DRAFT..ACTIVE, Authority-gated Promotion |
| CURRENT_HAMH_RESOLVER | runtime/hamh/resolver.py — deterministisch, Fallback baseline/shared/default (is_fallback=true) |
| CURRENT_CONTROLLER_AUTHORITY | n8n 01 Orchestrator (State Machine, Data-Tables P3Eyck556Y76TC4p/5ArfenIk1qhsigL6), ghiw-lockctl |
| CURRENT_PROVIDER_ROUTING | n8n → Job-Server (ghiw_provisioner_entry.py) → Builder-CT (Clone von 109) → opencode → local_llm/DeepSeek |
| CURRENT_RETRY_ESCALATION | Workflows 40 Build → 50 Verify → 80 Fix (Retry-Policy in 01 Orchestrator) |
| CURRENT_MCP_BOUNDARY | MCP-Smoke-Workflow (inaktiv), searxng lokal (Docker 127.0.0.1:8888) |
| CURRENT_PRODUCTION_HEALTH | n8n grün (Systemd active), Job-Server grün (8081, python3 pid 623208), Builder-Container 8000-8011 gestoppt, Callback-Sink/LM-Studio 192.168.1.195 OFFLINE |

## DeepSeek-Credential (sichere Suche, §13)

| Quelle | Ergebnis |
|---|---|
| env (Workstation) | KEIN DEEPSEEK_KEY |
| /etc/environment, ~/.bashrc, ~/.profile | keine Referenz |
| Docker | kein DeepSeek |
| CT102 /opt/dev-fabric/secrets/opencode-provider.env | OPENCODE_PROVIDER=deepseek, OPENCODE_MODEL=deepseek-v4-pro, OPENCODE_BASE_URL=https://api.deepseek.com/v1, OPENCODE_MAX_COST_USD=0.25, OPENCODE_API_KEY=LEER |
| n8n Credential-Store (LXC 101 sqlite) | keine deepseek-Credential |
| ~/.local/share/opencode/auth.json (legitimer opencode Secret-Store) | **deepseek.key: sk-… (35 Zeichen, Format valid), Datei 600 xxammaxx** |
| Shell-History / Git-History / Logs | NICHT durchsucht (verboten, §13) |

DEEPSEEK_CREDENTIAL_PRESENT = TRUE (Quelle: auth.json, verifiziert durch security-agent)

## DeepSeek-Contract-Refresh (live validiert durch research-agent, 2026-08-20)

Quellen: api-docs.deepseek.com (/api/create-chat-completion, /guides/thinking_mode, /quick_start/pricing, /quick_start/rate_limit, /quick_start/error_codes, /updates)

| Contract-Punkt | Doku-Ergebnis | Konsequenz |
|---|---|---|
| Modelle | deepseek-v4-flash (0731), deepseek-v4-pro (0813); chat/reasoner retired 2026-07-24 | bestätigt |
| thinking | {"type": enabled\|disabled}, default enabled | bestätigt |
| reasoning_effort | **Possible values: low\|high\|max**; medium→high, **xhigh→high** (NICHT max) | **Auftrags-Annahme "xhigh→max" ist FALSCH; Doku ist Quelle.** low bleibt kanonischer API-Wert, wird aber NICHT als HAMH-Evolutionsdimension behandelt (nur high\|max laut Auftrag §26) |
| temperature/top_p/presence_penalty/frequency_penalty | wirkungslos in Thinking Mode (kein Error, kein Effekt); presence/frequency zusätzlich deprecated | NON_OPTIMIZABLE-Guard nötig (§5) |
| reasoning_content bei tools | muss in allen Folge-Requests zurückgegeben werden, sonst HTTP 400 | bestätigt (§6/7/16) |
| usage | prompt_cache_hit_tokens / prompt_cache_miss_tokens | bestätigt (§38) |
| Fehler-Codes | 400/401/402/422/429/500/503 | bestätigt |
| Concurrency | flash 2500, pro 500, **account-level** | refactoren zu mutable_external_fact (§8) |
| Pricing ab 2026-08-16 16:00 UTC | **Peak/Off-Peak**: v4-flash cache-hit $0.007/$0.014, cache-miss $0.22/$0.44, output $0.66/$1.32 pro 1M USD; Peak 01:00-04:00 + 06:00-10:00 UTC | Preis-Snapshot mit Datum dokumentieren (§38) |

## Erforderliche Contract-Korrekturen (identifiziert)

1. §8: `concurrency_limit: 2500` als Modellkonstante in MODEL_IDS → Refactoring zu `provider_limits.concurrency {documented_value, scope: account, mutable_external_fact: true}`
2. §5: NON_OPTIMIZABLE-Markierung für thinking-mode-tote Parameter (temperature, top_p, presence_penalty, frequency_penalty) + Blockade als HAMH-Evolutionsdimension + Contract-Test
3. §4/§26: HAMH-Evolutionsdimensionen für reasoning_effort auf (high, max) beschränken — low/medium/xhigh dürfen nicht als eigenständige Evolutionsstufen dienen (Adapter bleibt dokukonform: akzeptiert low, mappt medium/xhigh→high)
4. Kein xhigh→max-Fix im Adapter (Doku widerlegt Auftragsannahme; Änderung wäre ein Provider-Contract-Bruch)

## Kosten-Rahmen (§1/§38)

- OPENCODE_MAX_COST_USD=0.25 (Produktions-Run-Grenze, CT102)
- Für diesen Run: MAX_EXTERNAL_API_COST_THIS_RUN = 5 EUR (≈5.45 USD bei EUR/USD 1.09) — keine explizite Testkosten-Grenze dokumentiert
- Cost-Accounting auf echten Usage-Daten (Pricing-Snapshot 2026-08-20, Peak/Off-Peak)
