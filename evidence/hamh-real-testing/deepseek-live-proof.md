# HAMH Real Testing — DeepSeek Live Proof

Datum: 2026-08-20/21 (Run: HAMH_REAL_TESTING)
Provider: https://api.deepseek.com (offizielle API, echte Requests)
Modell: deepseek-v4-flash (DeepSeek-V4-Flash-0731)

## §13 — Credential

DEEPSEEK_CREDENTIAL_PRESENT = TRUE
Quelle: ~/.local/share/opencode/auth.json (legitimer opencode Secret-Store
des dokumentierten deepseek-Providers). Key nur im RAM des Test-Skripts,
niemals in Dateien/Logs/Evidence. Verifiziert durch security-agent:
Format sk- + 32 hex = 35 Zeichen, Datei-Permission 600.
Quellen-Lücken geprüft: env (nein), CT102 opencode-provider.env (Key leer),
n8n Credential-Store (kein deepseek), /etc/environment (keine Referenz).

## §14 — Provider Connectivity Smoke (thinking=disabled)

```
HTTP_SUCCESS=true  MODEL_RESPONSE_RECEIVED=true
USAGE_RECEIVED=true  NO_PROTOCOL_ERROR=true
latency=1552ms  cost=$0.000003
```

## §15 — Thinking Smoke (thinking=enabled, reasoning_effort=high)

```
RESPONSE_SUCCESS=true  REASONING_STATE_RECEIVED=true
FINAL_CONTENT_RECEIVED=true
reasoning_state_bytes=167-225 (Inhalt NIE reproduziert, §7)
cost=$0.000048
```

## §16 — Real Tool-Call Proof (thinking=enabled, reasoning_effort=high)

```
REAL_DEEPSEEK_REQUEST_1 (get_test_value, key=fixture_a)
   -> REAL_TOOL_CALL (tool_call_00_…, Funktion get_test_value)
   -> REAL_TOOL_EXECUTION (deterministisch: fixture_a_value_42)
   -> REAL_TOOL_RESULT
   -> REAL_DEEPSEEK_REQUEST_2 (mit reasoning_content-Echo, tool_choice=auto)
   -> FINAL_RESPONSE (HTTP 200, content received)
REASONING_CONTENT_CONTINUITY = PASS
```

Zusätzlich offline verifiziert: ds.validate_tool_turn_chain() == [] vor dem
Senden (400-Rule-Contract). reasoning_content als PROTOCOL_STATE behandelt:
nur Metadaten (present/bytes) im Evidence-Trail, nie der Inhalt.

## §17 — Negativer Protokolltest (isoliert)

Tool-Follow-up OHNE erforderliches reasoning_content (eigener Raw-Pfad,
Production Request Builder unverändert):

```
EXPECTED=400  RECEIVED=400  -> Provider-Invariante PROTECTED
```

## Live-verifizierte Provider-Invariante (Contract-Fix, §4)

"Thinking mode does not support this tool_choice" (HTTP 400) bei
tool_choice="required" + thinking=enabled. Im Adapter als Offline-Guard
abgebildet (DeepSeekProtocolError); Test DS_THINKING_REQUIRED_TOOLCHOICE_
BLOCKED + DS_NONTHINKING_REQUIRED_TOOLCHOICE_OK ergänzt.

## §18 — Classification

**GREEN_HAMH_DEEPSEEK_V4_FLASH_RUNTIME_PROVEN**

Erfüllt: real provider request, real thinking request, real tool call,
real tool result, real follow-up request, reasoning state continuity,
final answer. (HAMH resolution + telemetry/audit: siehe deployment-proof
§20 + Trajektorien-Beweis, da die Resolution im Execution Path liegt.)

## Cost Accounting (§38)

```
total_cost_usd=0.000088  (winzig, weit unter 5 EUR-Grenze)
Preis-Snapshot 2026-08-20 (off-peak): cache-hit $0.007/1M, cache-miss
$0.22/1M, output $0.66/1M USD (Peak 01:00-04:00 + 06:00-10:00 UTC)
```

## Privacy (§7)

reasoning_content wurde weder im Report noch in Evidence-Dateien
reproduziert. Nur: reasoning_state_present, reasoning_state_bytes,
reasoning_tokens (Usage).

## Artefakte

- evidence/hamh-real-testing/results/deepseek-live-proof.jsonl (Trail)
- evidence/hamh-real-testing/results/deepseek-live-summary.json (Zusammenfassung)
