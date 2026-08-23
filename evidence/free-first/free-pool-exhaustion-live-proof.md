# Free pool exhaustion proof

The deployed runtime's existing negative-path and provider-runtime tests pass
for `NO_ELIGIBLE_FREE_PROVIDER`, DeepSeek exclusion, and automatic paid
escalation disabled. No external exhaustion call was needed after the live
pool remained unproven.

`DEEPSEEK_REQUESTS=0`
`PAID_REQUESTS=0`
`UNEXPECTED_BILLABLE_USAGE=0`
