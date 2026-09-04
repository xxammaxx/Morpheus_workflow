# MorpheusBench Operations

Task definitions live under `bench/tasks/{development,validation,holdout}` and
are hashed into immutable task sets. A result records code head, harness,
configuration, provider catalog snapshot and result hash. Missing telemetry is
`UNKNOWN`. Use `runtime.adaptive.benchmark.summarize()` for separate
correctness, reliability, security, cost, latency, token and tool metrics.

The current repository slice is implemented and locally tested; no new live
provider run or production deployment is claimed by this milestone.
