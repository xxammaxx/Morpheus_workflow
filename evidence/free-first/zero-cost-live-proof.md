# Zero-cost live proof

The runtime distinguishes explicit response cost, usage cost metadata, and
exact catalog hard-zero evidence. Missing top-level response cost is not
treated as zero generally. It is accepted only for an exact hard-zero route
with zero input/output prices and disabled paid fallback; otherwise cost is
UNKNOWN and the route is blocked.
