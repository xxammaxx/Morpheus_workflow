# HAMH Real Testing — Tool-Loop & Reasoning-State Proof

Datum: 2026-08-20/21 (Run: HAMH_REAL_TESTING)

## §16 — Real Tool-Call Loop (DeepSeek V4 Flash, thinking=enabled, effort=high)

Abgewickelt mit dem offiziellen DeepSeek-Chat-Completions-Endpoint
(api.deepseek.com, Modell deepseek-v4-flash). Tools: get_test_value
(deterministisches Testtool, isoliert, harmlos).

```
REAL_DEEPSEEK_REQUEST_1  (tool_choice=auto, Prompt erzwingt Tool-Call)
   -> REAL_TOOL_CALL       (get_test_value, arguments {key: fixture_a})
   -> REAL_TOOL_EXECUTION  (deterministisch: fixture_a_value_42)
   -> REAL_TOOL_RESULT     (tool-Message mit tool_call_id)
   -> REAL_DEEPSEEK_REQUEST_2 (reasoning_content vollständig zurückgegeben)
   -> FINAL_RESPONSE       (HTTP 200, final content received)
```

Ergebnis:
```
REAL_DEEPSEEK_REQUEST_1  = PASS (HTTP 200)
REAL_TOOL_CALL           = PASS (1 Call, Funktion get_test_value)
REAL_TOOL_EXECUTION      = PASS (deterministisch, isoliert)
REAL_TOOL_RESULT         = PASS (tool-Message, korrekte ID)
REAL_DEEPSEEK_REQUEST_2  = PASS (HTTP 200, reasoning_content-Echo)
FINAL_RESPONSE           = PASS (Content erhalten, finish_reason=stop)
REASONING_CONTENT_CONTINUITY = PASS
```

Offline-Contract-Check vor dem Senden: validate_tool_turn_chain() == []
(400-Rule).

## §17 — Negativer Protokolltest (Provider-Invariante)

Tool-Follow-up OHNE das erforderliche reasoning_content (isoliert, eigener
Raw-Request-Pfad — der Production Request Builder wurde NIE verändert):

```
EXPECTED = HTTP 400
RECEIVED = HTTP 400  ->  Invariante PROTECTED
```

## §7 — Privacy-Grenze

reasoning_content wurde als PROTOCOL_STATE behandelt: nur Metadaten
(reasoning_state_present, reasoning_state_bytes, reasoning_tokens) in
Evidence/Telemetry; der Inhalt wurde NIE reproduziert oder persistiert.

## Live-verifizierte Zusatz-Invariante (Contract-Fix §4)

tool_choice="required" + thinking=enabled -> HTTP 400
("Thinking mode does not support this tool_choice"). Als Offline-Guard im
Adapter abgebildet (DeepSeekProtocolError) + Contract-Tests
(DS_THINKING_REQUIRED_TOOLCHOICE_BLOCKED, DS_NONTHINKING_REQUIRED_TOOLCHOICE_OK).
