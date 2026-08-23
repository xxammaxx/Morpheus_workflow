# Provider Selection to Execution Proof

The local integration proof is PASS:

```text
ROUTING_DECISION provider-b/model-b
  -> adapter _dispatch()
  -> real local HTTP POST /chat/completions
  -> provider request id provider-b-request
  -> response model model-b
  -> observed provider/model match selected identity
  -> PROVIDER_SELECTION_TO_EXECUTION_PROOF=PASS
```

The test also asserts the request body model is `model-b`; routing metadata
alone cannot make the test pass. External-provider proof is
`BLOCKED_AUTH`, not claimed.
