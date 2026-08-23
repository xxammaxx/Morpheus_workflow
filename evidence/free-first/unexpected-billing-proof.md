# Unexpected Billing Proof

The offline provider response reports `cost=0.01` for a route classified
`FREE_HARD_STOP` with expected cost zero. The runtime emits
`UNEXPECTED_BILLABLE_USAGE`, sets execution proof to the sentinel state, and
quarantines the exact provider/model/endpoint. A subsequent free selection is
not permitted until catalog review clears the quarantine.
