# OpenRouter live proof

- Deployed credential presence: PASS, status-only.
- Deployed catalog refresh: PASS; 422 models discovered.
- Dynamic filter found 18 current explicit `:free` routes with zero input and
  output price and healthy discovery status.
- Maximum live candidate attempts: 3.
- Candidate 1: `dots-studio/dots-3-note-preview:free`, HTTP 429; one retry,
  HTTP 429.
- Candidate 2: `liquid/lfm-2.5-2.6b:free`, HTTP 404.
- Candidate 3: `nvidia/nemotron-3.5-lightning:free`, HTTP 404.
- The bounded probe stopped after the third candidate.
- Completion and selection-to-execution: `NOT_PROVEN`.

No non-free route was attempted and no paid fallback was used.
