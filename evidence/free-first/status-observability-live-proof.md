# Status and observability proof

The running service reported health and active state after restart. The
credential bridge verified provider presence status-only in the service
process. A successful external provider completion was not available, so
selected/actual model correlation is not claimed for this continuation.

The deployed runtime and offline integration tests retain provider/model,
usage, cost, failover, and attempt fields without recording secrets.
