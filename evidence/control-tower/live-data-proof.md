# Control Tower live-data proof

Verified live acceptance:

```text
N8N_SOURCE=LIVE
ADAPTER_SOURCE=LIVE
N8N_WORKFLOWS=12
FREE_POOL_SIZE=2
FREE_POOL_PROVIDERS=openrouter,ollama
GOLDEN_JOURNEY_RUN_ID=run-mt6unuge-agsdu4
FAILURE_RECOVERY_RUN_ID=run-mt6uony8-jjp9hf
CONTROL_TOWER_DATA_MODE=LIVE
N8N_HEALTH=HEALTHY
ADAPTER_HEALTH=HEALTHY
GOLDEN_JOURNEY_STATE=DONE
OVERVIEW_RESPONSE_SECONDS=0.146
```

The deployed BFF has no production fixture mode; the values above were
observed from the deployed live service.
