# OpenCode compatibility proof

- CLI and help: PASS
- Config resolution and agent listing: PASS
- Local Ollama route: PASS (`qwen3:1.7b`)
- Builder JSONL event types: `step_start`, `text`, `step_finish`
- Adapter parser compatibility: PASS
- Permission regression and bounded plan safety: PASS
- DeepSeek mappings/execution: 0

The final VoiceWiki plan job used CT 8001, `/opt/dev-fabric/opencode/opencode`, OpenCode `1.18.22`, Ollama, and completed with `autodev.plan.v1` scope/safety validation.
