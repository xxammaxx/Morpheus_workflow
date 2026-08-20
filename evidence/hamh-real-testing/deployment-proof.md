# HAMH Real Testing — Deployment Proof

Datum: 2026-08-20 (Run: HAMH_REAL_TESTING)

## Pre-Deploy Baseline (§10)

| Feld | Wert |
|---|---|
| PRE_DEPLOY_HEAD | 653d0d0 (nach Contract-Fixes; vor Deployment) |
| PRE_DEPLOY_ADAPTER_VERSION | autodev-harness-v2: 2.0.0 (healthz), autodev-harness v1: v1 |
| PRE_DEPLOY_CONFIG_FINGERPRINT | harness_adapter_v2.py sha256 prefix 6e994236d161cb99 |
| PRE_DEPLOY_HAMH_STATE | NOT_DEPLOYED (kein HAMH-Layer auf Host/CTs) |
| PRE_DEPLOY_SERVICE_STATUS | autodev-harness-v2 active, autodev-harness active, n8n active (LXC 101) |
| PRE_DEPLOY_HEALTH | healthz 200 (8081), n8n API 200 (5678), Job-Server 8081 | 
| PRE_DEPLOY_REGISTRY | leer (keine Registry auf Runtime) |

## Deployment (§11) — additiv, kein Produktionsumbau

Zielarchitektur (unverändert bis auf additive HAMH-Schicht):
```
n8n Controller (LXC 101, unverändert)
      │
      ▼
existing Adapter v2 (8081, unverändert, sha 6e9942…)
      │
      ▼
HAMH Resolver Service (NEU, /opt/dev-fabric/hamh/, Port 8090)
      │
      ▼
Model Adapter (deepseek_adapter.py, in HAMH-Layer)
      │
      ▼
effective Harness (Registry-Profile, hamh.harness.v1)
      │
      ▼
Provider (DeepSeek / LM Studio)
```

Deployte Artefakte (Host 192.168.1.136, /opt/dev-fabric/hamh/):
- hamh_service.py (HTTP: /healthz, /v1/resolve, /v1/registry)
- hamh_resolve.py (CLI)
- init_registry.py (Operator-Initialisierung)
- hamh-resolver.service (systemd, Port 8090)
- rollback_hamh.sh (Rollback-Skript)
- runtime/ (hamh/*, contracts/* — zero externe Dependencies, stdlib only)
- state/registry.json (Registry mit ACTIVE-Eintrag)

Registry-Initialisierung (operator-authorized, Authority aus bestehendem
Adapter-Secret-Store /var/lib/autodev-harness-v2/api-token):
```
PROMOTED hamh/baseline/deepseek-v4-flash/build/thinking/v1 -> ACTIVE
REGISTRY hamh/baseline/deepseek-v4-flash/build/thinking/v1 | ACTIVE | AUTHORIZED_PROMOTION
```

## Post-Deploy Verification (§11)

| Check | Ergebnis |
|---|---|
| service status | hamh-resolver active, autodev-harness-v2 active, autodev-harness active, n8n active |
| healthz | {"status":"ok","service":"hamh-resolver","version":"1.0.0"} HTTP 200 |
| contract compatibility | Registry-Eintrag validiert gegen hamh.harness.v1 (init add() ok) |
| controller connectivity | LXC 101 (n8n) erreicht 8090: resolution OK, is_fallback=false |
| logs | journalctl hamh-resolver: keine Fehler |
| production unchanged | Adapter v1+v2, n8n-Workflows unverändert (kein File-Write auf deren Pfade) |

## §20 — HAMH Resolution Live (build / deepseek / thinking)

```
resolved_harness_id: hamh/baseline/deepseek-v4-flash/build/thinking/v1
is_fallback: False
effective_tools: {read,edit,write,list,glob,grep: True; bash,webfetch,task,skill,question,todowrite: False}
effective_context: stable_first (stable_prefix=[system_instructions,tool_schemas])
effective_reasoning: {thinking: enabled, reasoning_effort: high}
fingerprint: a1e6955fa0f1aadf099a331f…
```
Exakt Registry-Eintrag entsprechend (kein Tuning, Baseline-Profile explizit registriert).

## §12 — Baseline Fallback Live

| Request | resolved_harness_id | is_fallback |
|---|---|---|
| deepseek-v4-pro / review / thinking | baseline/shared/default/thinking/review | true |
| unknown model / build | baseline/shared/default/thinking/build | true |

Fallback explizit, deterministisch, Produktionspfad unverändert.
FALLBACK_LIVE_PROOF = PASS

## §10 — Rollback-Pfad praktisch verifiziert (Sandbox-Registry-Kopie, Host)

```
ACTIVE_BEFORE:                    [hamh/baseline/deepseek-v4-flash/build/thinking/v1]
ACTIVE_AFTER_PROMOTE (Probe):     [hamh/candidate/probe/v1]
ROLLBACK:                         ok, restored hamh/baseline/deepseek-v4-flash/build/thinking/v1
ACTIVE_AFTER_ROLLBACK:            [hamh/baseline/deepseek-v4-flash/build/thinking/v1]
FINGERPRINT_MATCH:                True
```

Rollback-Pfad praktisch verifiziert (nicht nur dokumentiert). Der finale
Live-Rollback-Beweis inkl. Fingerprint-Vergleich folgt in §35.

## Service-Unit (deployt)

```ini
[Unit]
Description=HAMH Resolver Service (additive harness resolution layer)
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
ExecStart=/usr/bin/python3 /opt/dev-fabric/hamh/hamh_service.py
Restart=on-failure
RestartSec=3
NoNewPrivileges=true
PrivateTmp=true
Environment=HAMH_PORT=8090
Environment=HAMH_REGISTRY_PATH=/opt/dev-fabric/hamh/state/registry.json
ReadWritePaths=/opt/dev-fabric/hamh/state

[Install]
WantedBy=multi-user.target
```

## Infrastruktur-Vorfall (dokumentiert, mitigiert)

pve-Root-FS 100% voll → Adapter-Crash-Loop (OSError 28, Ledger-Write) →
Live-Regression rot. Mitigation: verwaisten libguestfs-Temp-Ordner
(/var/tmp/.guestfs-0, 827M) entfernt + Adapter-Restart. Produktionsdaten
(/var/lib/vz 35G, /var/backups/n8n 14G, /root-VMs) unangetastet.
Danach: Adapter-Suite 23/23 PASS (7 NOT_RUN: Callback-Sink 192.168.1.195
offline, dokumentierter Infra-Zustand), Control-Plane 9/9 PASS.

## Deployment-Status

HAMH_DEPLOYED = TRUE
HAMH_RUNTIME_HEALTH = GREEN (alle Dienste active, healthz 200)
BASELINE_FALLBACK_LIVE = PASS
