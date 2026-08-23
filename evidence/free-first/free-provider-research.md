# Provider Research Snapshot

Official sources were checked on 2026-08-21. A fetch failure is recorded as an
uncertainty and never converted into a free classification.

| Provider | Official source / live result | Conservative conclusion |
|---|---|---|
| OpenRouter | `https://openrouter.ai/docs/` and model pages were not retrievable by the documentation fetcher | Dynamic pricing adapter implemented; no live classification without catalog/credential |
| Gemini Developer API | `https://ai.google.dev/gemini-api/docs/pricing` timed out | Adapter implemented; privacy-gated and billing-risk until account policy is proven |
| Groq | `https://console.groq.com/docs/rate-limits` retrieved | Free Plan has RPM/RPD/TPM/TPD and rate-limit headers; `FREE_QUOTA` with hard quota routing |
| Mistral | requested tier URL returned 404 | Dynamic catalog only; zero price must be proven per model/account |
| Cohere | `https://docs.cohere.com/docs/rate-limits` retrieved | Evaluation keys are free and limited; North Mini Code is discovered, not hardcoded |
| Cloudflare Workers AI | `https://developers.cloudflare.com/workers-ai/platform/pricing/` retrieved | 10,000 neurons/day free; Free plan stops, Paid plan bills above allocation |
| NVIDIA Build | `https://build.nvidia.com/explore/discover` retrieved | Hosted endpoints classified `FREE_PROTOTYPING` only |
| NVIDIA NIM | official NIM introduction URL was not retrievable in this run | Self-hosted path kept separate; hardware/electricity are not external zero cost |
| Cerebras | requested rate-limit URL returned 404 | `FREE_TRIAL` only until current account terms are proven |
| Hugging Face | `https://huggingface.co/docs/inference-providers/index` retrieved | Free tier/credits exist; proxy provider identity and credit state are first-class |
| SambaNova | requested official getting-started URL returned 404 | `PAID_ONLY` / unknown, never free-primary |
| Together AI | `https://www.together.ai/pricing` retrieved | Token pricing and account credits; no durable free-primary classification |
| Fireworks AI | `https://fireworks.ai/pricing` retrieved | $1 free credits, postpaid token pricing; `FREE_CREDIT` only |
| Scaleway Generative APIs | official docs index retrieved, requested pricing URL returned 404 | Billing/account semantics unresolved; `PAID_ONLY` |
| GitHub Models | marketplace page redirected to sign-in | `RETIRED`, no implementation |
| DeepInfra | `https://deepinfra.com/pricing` retrieved; per-token and execution-time pricing | `PAID_ONLY` |
| Replicate | `https://replicate.com/pricing` retrieved; public models billed by time or tokens | `PAID_ONLY` |
| Modal | `https://modal.com/pricing` retrieved; starter includes credits but compute is metered | `FREE_CREDIT` only, not an inference zero-cost path |
| Novita AI | `https://novita.ai/pricing` retrieved; model API prices are listed | `PAID_ONLY` |
| Public AI | requested official pricing URL returned 404 | `UNKNOWN_NOT_ELIGIBLE` |
