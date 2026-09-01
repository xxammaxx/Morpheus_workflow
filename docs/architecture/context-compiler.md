# Context Compiler

`runtime/adaptive/context.py` builds five explicit blocks: immutable Control
Core, current task state, repository references, recent execution metadata and
bounded experience retrieval. Each block carries source, trust, hash, reason
and token count. Repository content and memory are references/observations, not
system instructions. Budgets are deterministic and the Control Core is never
LLM-summarized.
