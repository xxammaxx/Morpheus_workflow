# HAMH Real Testing — Final Report

Datum: 2026-08-20/21 (Run: HAMH_REAL_TESTING)
Autor: Issue-Orchestrator (evidence-gated, keine Mocks, keine Secrets)

## FINAL_CLASSIFICATION

```
GREEN_HAMH_PRODUCTION_ACTIVATION_PROVEN      (Deployment + Fallback + Rollback live)
GREEN_HAMH_DEEPSEEK_V4_FLASH_RUNTIME_PROVEN  (echte Provider-Requests + Tool-Loop + State-Continuity)
GREEN_HAMH_EVOLUTION_GOVERNANCE_PROVEN       (unverändert; Live-Integration ohne Governance-Regression)
AMBER_HAMH_VALUE_NOT_PROVEN                  (Candidate evidence-basiert verworfen; negativer Befund)
```

## Abschlussreport (order §44)

```
FINAL_CLASSIFICATION=AMBER_HAMH_VALUE_NOT_PROVEN
  (Teil-GREENs: PRODUCTION_ACTIVATION_PROVEN, DEEPSEEK_V4_FLASH_RUNTIME_PROVEN,
   EVOLUTION_GOVERNANCE_PROVEN; VALUE nicht proven — ehrlich)

START_HEAD=bd4fb51838b135e0055cb8820288dc0cc27663bf
END_HEAD=<siehe git log>

PREVIOUS_PRODUCTION_BASELINE=AutoDev-Harness v2 Chain (n8n 00-90, Job-Server 8081, opencode 1.17.9 + local_llm)
CURRENT_PRODUCTION_BASELINE=unverändert + additive HAMH-Resolver-Schicht (8090, /opt/dev-fabric/hamh/)

REALITY_REFRESH=PASS (live verifiziert: Host pve, LXC 101 n8n 2.26.8, Adapter v1/v2 aktiv,
  Job-Server/Builder-Infrastruktur, Credential in auth.json; dokumentiert in reality-refresh.md)

DEEPSEEK_CONTRACT_REFRESH=PASS (offizielle Doku live validiert 2026-08-20:
  low|high|max kanonisch, medium/xhigh->high (NICHT max — Auftragsannahme korrigiert),
  thinking-Parameter wirkungslos, reasoning_content-400-Regel, account-level concurrency,
  Peak/Off-Peak-Pricing)
REASONING_EFFORT_CANONICALIZATION=PASS (Evolutionsdimensionen high|max; low/medium/xhigh
  als Evolutionsdimensionen blockiert; API-Kompatibilität unverändert)
INEFFECTIVE_THINKING_PARAMETERS_GUARD=PASS (temperature/top_p/presence_penalty/
  frequency_penalty = NON_OPTIMIZABLE, als Candidate-Dimensionen blockiert, Tests)

HAMH_DEPLOYED=TRUE (/opt/dev-fabric/hamh/, hamh-resolver.service Port 8090, Registry ACTIVE baseline)
HAMH_RUNTIME_HEALTH=GREEN (healthz 200, alle Dienste active, n8n-Connectivity bewiesen)
BASELINE_FALLBACK_LIVE=PASS (is_fallback=true für Identity ohne ACTIVE-Harness und unbekannte Modelle)

DEEPSEEK_CREDENTIAL_PRESENT=TRUE (Quelle: ~/.local/share/opencode/auth.json, Format valid,
  nur 4-Zeichen-Präfix je verarbeitet, Datei 600, nie ausgegeben/committet)

DEEPSEEK_NON_THINKING_LIVE=PASS (HTTP 200, Usage, $0.000003)
DEEPSEEK_THINKING_LIVE=PASS (HTTP 200, reasoning_state received, $0.000048)
DEEPSEEK_TOOL_CALL_LIVE=PASS (get_test_value: Request1->ToolCall->Exec->Result->Request2->Final)
REASONING_CONTENT_CONTINUITY=PASS (Echo-Back über Tool-Turns; Privacy: nur Metadaten)
DEEPSEEK_NEGATIVE_PROTOCOL_TEST=PASS (HTTP 400 erwartet und erhalten; Invariante PROTECTED)
  + live-verifizierte Zusatz-Invariante: thinking + tool_choice=required -> 400 (Guard ergänzt)

GREEN_HAMH_DEEPSEEK_V4_FLASH_RUNTIME_PROVEN=TRUE

REAL_BUILD_SLICE=PASS (disposable Workspaces, FROZEN Fixtures v1+v2,
  reale opencode-Runs auf deepseek-v4-flash, pytest-Verifikation)
REAL_TRAJECTORY_COUNT=10 Baseline (e001-e010) + 15 Pilot + Kalibrierung/Probes (dokumentiert)

WEAKNESS_PATTERN=frequent_malformed_edits (3 Runs), late_editing (3),
  same_file_repeatedly_reopened (3), excessive_tool_loops (4)
CANDIDATE_JUSTIFIED=TRUE (>=2 Runs + plausible Harness-Ursache editing_strategy)
CANDIDATE_ID=hamh/candidate/build/precision-edit/v1
CANDIDATE_FINGERPRINT=88d575f606768ac33efa19aa91c31af5bd8a8d9199bfb5a5e12481c10fbf26c4
CHANGED_COMPONENT=editing_strategy (precision_edit; einzige Variable)

EVOLUTION_SET_SIZE=10 (Baseline e001-e010, frozen)
VALIDATION_SET_SIZE=0 (nicht nötig — Pilot auf Trainings-Task)
HOLDOUT_SET_SIZE=24 (generiert, versiegelt, NICHT verwendet)
HOLDOUT_LEAKAGE_CHECK=clean (Tasks nie inspiziert; Manifest SHA256-versiegelt)

BASELINE_A_RESULT=5/5 verified, $0.002545, 36s
CANDIDATE_B_RESULT=5/5 verified, $0.003383, 46s
MATCHED_COMPUTE_C_RESULT=5/5 verified, $0.002693, 37s

VERIFIED_SUCCESS_A=5/5  VERIFIED_SUCCESS_B=5/5  VERIFIED_SUCCESS_C=5/5

COST_PER_VERIFIED_SUCCESS_A=$0.002545
COST_PER_VERIFIED_SUCCESS_B=$0.003383
COST_PER_VERIFIED_SUCCESS_C=$0.002693

VALUE_DELTA=+33.0% Kosten (B vs A), +28.3% Latenz; Success-Delta 0
MATCHED_COMPUTE_EXPLANATION=C≈A -> B-Effekt nicht compute-getrieben; B schlicht schlechter

SHADOW_RESULT=NOT_RUN (kein Shadow ohne erfolgreichen Candidate; order §34)
CANARY_RESULT=NOT_RUN (kein Canary ohne erfolgreichen Candidate)
ROLLBACK_PROOF=PASS (Promote->Rollback->exakter Fingerprint ea502fbb…; Sandbox + Live-Kopie)

MULTI_MODEL_ROUTING_REGRESSION=NONE (Control-Plane 9/9 live)
RETRY_ESCALATION_REGRESSION=NONE (Workflows 40/50/80 unverändert, 9/9)
MCP_REGRESSION=NONE (keine MCP-Änderung; MCP-Smoke inaktiv wie vorher)
CONTROLLER_AUTHORITY_REGRESSION=NONE (01 Orchestrator unverändert; HAMH additiv)
PRODUCTION_SENTINELS=GREEN (Adapter v1+v2 active, n8n active, Job-Server aktiv;
  pve-Root-FS-Vorfall mitigiert: guestfs-Cleanup 827M, Produktionsdaten unangetastet)

TOTAL_EXTERNAL_API_COST=~$0.16 USD (Live-Proof $0.000088 + Trajektorien/Pilot
  ~$0.16; weit unter MAX_EXTERNAL_API_COST_THIS_RUN=5 EUR; Pricing-Snapshot
  2026-08-20 off-peak)

VALUE_PROOF=AMBER_HAMH_VALUE_NOT_PROVEN
  (Negativer wissenschaftlicher Befund: Candidate verworfen, weil er die
   Baseline nicht schlägt — weder Qualität noch Wirtschaftlichkeit.)
```

## Weitere Pflichtfelder (order §44)

```
FILES_CHANGED=runtime/hamh/deepseek_adapter.py, runtime/hamh/evolution.py,
  evidence/tests/hamh/test_deepseek_adapter.py, test_evolution.py,
  evidence/hamh-real-testing/** (reality-refresh, deployment-proof,
  deepseek-live-proof, tool-loop-proof, candidate-hypothesis, value-analysis,
  rollback-proof, final-report, live/**, deploy/**, fixtures/**, holdout/**,
  results/**)
TESTS_ADDED=~20 neue Contract-/Guard-/Holdout-Verifikationen (52+31 Adapter/Evolution,
  Holdout-Generator mit 24 Task-Verifikationen)
TESTS_EXECUTED=285 Unit-Tests (11 Suiten) + 9 Control-Plane + 23 Adapter (live)
LIVE_TESTS_EXECUTED=DeepSeek 5 Live-Beweise + 35+ reale Build-Runs (opencode/DeepSeek)
COMMITS=<siehe git log; logische Trennung: Contracts, Deployment, Live-Proof,
  Pipeline, Holdout/Candidate, Ergebnis>
KNOWN_LIMITATIONS=Pilot-n klein (5/Bedingung, 1 Trainings-Task); kein Holdout
  (gerechtfertigt durch §27); v1-Fixture-Inzident (probe-002 cwd) dokumentiert;
  Callback-Sink 192.168.1.195 offline (7 Adapter-Tests NOT_RUN, Infra)
REMAINING_RISKS=Credential lebt in auth.json (bestehender Store, 600); 
  HAMH-Resolver-Service bleibt additiv aktiv (reversibel via rollback_hamh.sh);
  pve-Root-FS strukturell voll (35G vz + 14G Backups) — erneute Log-Rotation
  erforderlich, kein Run-Blocker
NEXT_EVIDENCE_DRIVEN_STEP=Bei neuem Schwäche-Muster: Holdout (24 versiegelte
  Tasks) mit A/B/C ausrollen; vorher Task-Kalibrierung auf ~70-80% Success
  für aussagekräftige Deltas; Kosten-Budget bleibt gedeckelt
```

## Definition of Done (order §45)

Erfolgsfall erreicht (HAMH deployed, DeepSeek live, Thinking live, Tool-Call
live, reasoning state continuity, reale Build-Trajektorien, Candidate aus
echten Daten, A/B/C mit Matched-Compute, Rollback bewiesen, keine
Control-Plane-Regression) UND ehrliches Value-Urteil gefällt:

**Negativer wissenschaftlicher Befund** — Candidate schlägt weder Baseline
noch Matched-Compute-Kontrolle; Candidate verworfen, AMBER_HAMH_VALUE_NOT_PROVEN.
Kein Candidate wurde gerettet. Alle Beweise real, keine Mocks, keine
versteckten Parameteränderungen, keine Self-Promotion, keine
Architektur-Erweiterung vor dem Value-Urteil.
