# ADR-2026-08-24: Control Tower read-only projection

Status: ACCEPTED for V1.1

The Control Tower is an observability read model, not a second control plane.
n8n remains the sole control plane and Data Tables remain the Run-State system
of record. The Harness Adapter remains the execution plane and LLMs remain
workers.

The browser talks only to the same-origin Python stdlib BFF. The BFF performs
bounded authenticated GETs to the n8n Public API and Harness Adapter read API.
It never accesses the n8n database, stores run state, invokes an LLM, selects a
provider, starts/retries/stops a job, or writes to an upstream.

Credentials are server-side LoadCredential inputs. The viewer token is a
dedicated root-only file and is accepted with constant-time comparison. The
dashboard is bound to the private LAN address only. Native HTML/CSS/JS avoids
runtime CDN and frontend supply-chain dependencies.

The projection deliberately emits UNKNOWN/UNAVAILABLE and observed attempt
timestamps only. It does not invent workflow transition timestamps.
