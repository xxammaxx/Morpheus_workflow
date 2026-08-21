# HAMH Calibrated Value Discovery — Infrastructure Preflight

Datum: 2026-08-21 (Run: HAMH_CALIBRATED_VALUE)
Autor: Issue-Orchestrator (live verifiziert, keine Annahmen)

## Ressourcen-Gate (Run Card §5)

### Workstation (Eval-Host)

| Prüfung | Wert | Klassifikation |
|---|---|---|
| Disk free / | 481G frei von 937G (46 % belegt) | **GREEN** (>15 %) |
| Inodes / | 8 % belegt | **GREEN** |
| Memory | 5.0G available von 14Gi | OK |
| Swap | 0B (kein Swap) | OK für Eval-Größe |

### Produktionshost pve (192.168.1.136)

| Prüfung | Wert | Klassifikation |
|---|---|---|
| Disk free / (pve-root) | **0 frei von 68G (100 % belegt)** | **BLOCK_HAMH_EXPERIMENT** für Host-Schreiboperationen |
| Inodes / | 8 % belegt | GREEN |
| Memory | 2466 MB available (7724 total, 4236 swap used) | WARN |
| hamh-resolver | active | GREEN |
| n8n (Host-Service) | inactive (läuft in LXC 101 — erwartet) | INFO |

## Dienst-Gesundheit

| Dienst | Status | Detail |
|---|---|---|
| hamh-resolver (8090) | GREEN | healthz `{"status":"ok","service":"hamh-resolver","version":"1.0.0"}`; POST /v1/resolve liefert Baseline a1e6955f…, is_fallback=false |
| Job-Server (8081) | UP | HTTP erreichbar (UNAUTHORIZED ohne Token = erwartet) |
| n8n LXC 101 | nicht direkt geprüft | 192.168.1.52:5678 — für dieses Eval nicht erforderlich |
| HAMH-Adapter | n/a | nicht als Service deployt (Repovorlage, etablierter Zustand) |
| DeepSeek-Provider | SMOKE_FOLGT | opencode 1.15.13 + deepseek/deepseek-v4-flash; Live-Smoke wird vor der Kalibrierung ausgeführt |

## Klassifikation & Konsequenz (Run Card §5)

- **Eval-Integrität**: Die Trajektorien-Runs laufen ausschließlich auf der Workstation
  (/tmp/opencode/disposable + Repo-Fixtures). Workstation-Disk GREEN => kein Eval-Blocker.
- **pve-Root-FS 100 %**: Vorfall aus HAMH_REAL_TESTING wieder aufgetreten. Konsequenzen:
  1. KEINE Schreiboperationen auf /opt/dev-fabric/hamh/state/registry.json während dieses Runs
     (Candidate-Registrierung/Promotion nur bei erfolgreichem Candidate und NUR nach
     Freigabe durch autorisierten Pfad — vorher Host-Platzproblem lösen).
  2. KEINE Produktionsdaten für Eval-Platz löschen (Run Card §5).
  3. Resolver-READ bleibt nutzbar (nachgewiesen).
- **Abweichungsdokumentation**: Die Run-Card-Grenzen (>15 % GREEN, <5 % BLOCK) sind auf die
  Workstation anwendbar; für den Produktionshost gilt die Sonderregel: pve-root ist
  strukturell voll (bekannter Zustand), der Eval-Pfad ist davon entkoppelt — dokumentierte
  Abweichung gemäß Run Card §5 ("Falls die reale Umgebung andere sinnvolle Grenzen verlangt").

## Provider-Connectivity

| Prüfung | Status |
|---|---|
| HAMH-Resolver 192.168.1.136:8090 | PASS (healthz + Resolution) |
| opencode model registry: deepseek/deepseek-v4-flash | PASS (opencode models) |
| DeepSeek API End-to-End (opencode run) | PENDING — Live-Smoke vor Kalibrierung (nächster Schritt) |

## Budget (Run Card §40)

- MAX_EXTERNAL_API_COST = 10 USD equivalent
- Erwartete Run-Kosten: ~0.003 USD je Trajektorie; geplanter Umfang (Kalibrierung + Dev +
  ggf. A/B/C) ≈ 100-120 Runs ≈ 0.3-0.5 USD => Budget ausreichend, kein Teil-A/B/C-Risiko.
