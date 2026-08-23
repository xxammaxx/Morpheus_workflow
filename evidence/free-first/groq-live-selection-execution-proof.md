# Groq live selection-to-execution proof

- `GROQ_ACCOUNT_CLASS=NOT_PROVEN`.
- `GROQ_FREE_ACCOUNT_EVIDENCE=NOT_PROVEN_FROM_AUTH_CATALOG_HEADERS`.
- `GROQ_AUTH=PASS`.
- `GROQ_CATALOG=PASS`.
- Dynamic catalog: 13 models.
- The local committed `runtime.providers.adapters.ProviderAdapter` performed `GET https://api.groq.com/openai/v1/models` and received HTTP `200`.
- `GROQ_TRANSPORT_1010=ABSENT` for that local provider-adapter probe.
- `CANONICAL_MORPHEUS_ADAPTER_HTTP=NOT_PROVEN`: the remote service is the old deployed adapter and lacks the committed provider runtime.
- `GROQ_COMPLETION=NOT_RUN_FAIL_CLOSED`: the account class/free eligibility was not sufficiently proven.
- `GROQ_SELECTED_PROVIDER=NOT_RUN`.
- `GROQ_ACTUAL_PROVIDER=NOT_RUN`.
- `GROQ_SELECTION_TO_EXECUTION=NOT_PROVEN_FAIL_CLOSED`.
- `GROQ_ZERO_COST=NOT_PROVEN_FAIL_CLOSED`.

No Groq completion was sent. This preserves the zero-cost invariant under uncertain account billing.
