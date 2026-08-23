# Eligibility bootstrap proof

The pre-fix regression reproduced the causal cycle: a route without
`selection_to_execution_proven` was either treated as already promoted or
could not be distinguished from a normal route. The runtime now separates:

- `probe_eligibility`: safe pre-execution evidence plus exact zero-cost route
  proof; it deliberately does not require execution proof.
- `promotion_eligibility`: successful correlated execution, selection-to-
  execution proof, and zero-cost evidence are required.

`runtime/tests/test_provider_bootstrap.py` covers both states, unsafe/unknown
cost, failed probes, Groq unknown-account fail-closed behavior, DeepSeek, and
paid-route exclusion.
