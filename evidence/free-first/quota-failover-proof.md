# Quota and Failover Proof

The offline integration test makes provider A return HTTP 429 and then routes
to provider B. It records one bounded `PROVIDER_FAILOVER` chain entry and does
not create a semantic task retry or increment an AutoDev attempt.

Result: `FREE_FAILOVER_PROOF=PASS` for the normalized runtime contract.
External provider failover remains credential-blocked.
