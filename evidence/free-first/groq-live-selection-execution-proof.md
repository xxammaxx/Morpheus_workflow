# Groq live proof

- Deployed credential presence: PASS, status-only.
- Deployed `/models` authentication/catalog request: HTTP 200.
- Groq model rows discovered: 13.
- Transport regression: no HTTP 1010 response.
- Synthetic completion: not called. The deployed catalog classified the
  account class as `unknown`; route-specific zero-cost/account evidence was
  not available. The runtime therefore correctly refused promotion.
- Selection-to-execution: `NOT_PROVEN` by fail-closed policy.

No paid or cost-uncertain Groq completion was sent.
