# OpenRouter live selection/execution proof

Status before deployment: NOT_RUN. The implementation uses the provider-owned
`openrouter/free` route, captures the provider-supplied resolved model, and
accepts missing response cost only when the exact route is catalog-proven
hard-zero with no paid fallback. A successful live result must record selected
provider/route, actual provider, non-empty resolved model, request id, usage,
and cost proof.
