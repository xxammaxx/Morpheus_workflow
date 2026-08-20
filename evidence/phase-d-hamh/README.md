# HAMH Phase D — Tests & Evidence (2026-08-20)

Alle Testergebnisse frisch und korreliert. Rohausgaben in `results/`.

## Testmatrix

| Suite | Kommando | Ergebnis |
|---|---|---|
| Contracts (12 autodev + 2 hamh) | `python3 runtime/tests/test_contracts.py` | 34/34 PASS |
| Validator-Äquivalenz Py/JS (inkl. 7 HAMH-Fixtures) | `python3 runtime/tests/test_validator_equivalence.py` | 34/34 PASS |
| Adapter-Suite v2 (LIVE, deployed old adapter) | `python3 evidence/tests/v2/adapter_suite.py` | 23/23 PASS, 7 NOT_RUN (Infra: Callback-Sink-IP 192.168.1.195 offline) |
| Control-Plane-Matrix (LIVE n8n) | `python3 evidence/tests/v2/control_plane_e2e.py` | 9/9 PASS |
| HAMH Isolation A–H | `python3 evidence/tests/hamh/test_isolation.py` | 14/14 PASS |
| HAMH Registry (AC-3/8/10 + corrupt-file + thread-safety) | `python3 evidence/tests/hamh/test_registry.py` | 22/22 PASS |
| HAMH Resolver (AC-4/5/6/9) | `python3 evidence/tests/hamh/test_resolver.py` | 14/14 PASS |
| HAMH Evolution (AC-12/13, Governance-Gates, Weakness-Mining) | `python3 evidence/tests/hamh/test_evolution.py` | 21/21 PASS |
| HAMH Capability-vs-Harness (AC-11) | `python3 evidence/tests/hamh/test_capability_vs_harness.py` | 11/11 PASS |
| HAMH DeepSeek-Adapter (offline, offizielle Semantik) | `python3 evidence/tests/hamh/test_deepseek_adapter.py` | 33/33 PASS |
| HAMH Adapter-Naht (in-process, AC-16, Registry-Verdrahtung E2E) | `python3 evidence/tests/hamh/test_adapter_hamh_seam.py` | 20/20 PASS |
| HAMH Telemetry (Privacy-Sentinel, nested sanitize) | `python3 evidence/tests/hamh/test_telemetry.py` | 29/29 PASS |
| HAMH Task-Suite (Governance ohne LLM, Promotionskette + Rollback) | `python3 evidence/tests/hamh/task_suite.py` | 24/24 PASS |

Summe HAMH-Suiten: **188/188 PASS**. Summe Regression (Contracts + Äquivalenz):
**68/68 PASS**. Live-Regression: Control-Plane **9/9**, Adapter-Suite **23/23**
(7 NOT_RUN durch Infrastruktur, ehrlich dokumentiert).

## Acceptance-Criteria-Zuordnung (aus hamh-spec.md §15)

| AC | Test | Status |
|---|---|---|
| AC-1 Isolation A | test_isolation AC1_* | PASS |
| AC-2 Isolation B | test_isolation AC2_* (Profil-Ebene + Registry-Ebene) | PASS |
| AC-3 Isolation C | test_registry AC3_*, test_evolution AC3_* | PASS |
| AC-4 Isolation D | test_resolver AC4_* | PASS |
| AC-5 Isolation E | test_resolver AC5_* | PASS |
| AC-6 Isolation F | test_resolver AC6_* | PASS |
| AC-7 Isolation G | test_isolation AC7_*, test_contracts FP_HARNESS_* | PASS |
| AC-8 Isolation H | test_registry AC8_*, task_suite SUITE_ROLLBACK_* | PASS |
| AC-9 Resolver-Determinismus | test_resolver AC9_* | PASS |
| AC-10 Registry-Autorität | test_registry AC10_* | PASS |
| AC-11 Capability-Klassifikation | test_capability_vs_harness AC11_* | PASS |
| AC-12 Leakage-Sentinel | test_evolution AC12_*, task_suite SUITE_LEAK_* | PASS |
| AC-13 Matched-Compute | test_evolution AC13_*, task_suite SUITE_MATCHED_COMPUTE_* | PASS |
| AC-14 Contracts+Fingerprint | test_contracts.py (34), test_validator_equivalence.py (34) | PASS |
| AC-15 Regression | siehe Tabelle oben (Control-Plane 9/9 live, Adapter 23/23 live) | PASS (7 NOT_RUN Infra) |
| AC-16 Adapter-Naht | test_adapter_hamh_seam.py (20) | PASS |
| AC-17 Generator-Passthrough | Generator-Exporte: nur additive Felder; Backend-Whitelist unverändert (Diff-Verifikation) | PASS |

## DeepSeek-Live-Beweis

`python3 evidence/scripts/deepseek_live_smoke.py` →
`DEEPSEEK_LIVE_PROOF=NOT_RUN` (kein DEEPSEEK_API_KEY in der Umgebung).
Opt-in-Skript liegt bereit; Verifikationsgegenstand: Thinking-Modus,
Tool-Call-Round-Trip, reasoning_content-Echo-Back (400-Regel), Folge-Tool-Turn,
finale Antwort, vollständiger Audit-Trail (JSONL).

## Infrastruktur-Vorfälle (dokumentiert, mitigiert)

1. pve-Root-FS 100% voll → Adapter-Crash-Loop nach Suite-Neustart
   (`OSError: No space left on device` beim Ledger-Write). Mitigation:
   `journalctl --vacuum-size=200M` (nur Log-Rotation), Service-Neustart,
   Healthcheck 200. Produktionsdaten (/var/lib/vz 35G, Backups 13G)
   unangetastet.
2. LM-Studio-Host 192.168.1.195 offline → Adapter-Suite-Callback-Sink kann
   nicht binden (Errno 99) → 7 Tests NOT_RUN; Builder-CT 8001 stopped.
3. Kein Git-Remote → GitHub-Issue-Zyklus nicht möglich; Evidence-READMEs
   sind Source of Truth (dokumentierte Abweichung).

## Value-Beweis (ehrlich)

Ohne Live-Modelle (LM Studio offline, kein DeepSeek-Credential) ist kein
belastbarer Value-Vergleich möglich. Die Governance-Mechanik inkl.
Matched-Compute-Komparator ist deterministisch bewiesen (task_suite,
AC-13), der wirtschaftliche/qualitative Mehrwert eines Kandidaten gegenüber
Baseline + Matched-Compute ist es NICHT.

`HARNESS_VALUE=NOT_PROVEN` → erwartete Klassifikation `AMBER_HAMH_VALUE_NOT_PROVEN`.
