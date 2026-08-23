# Free-First Reality Refresh

Date: 2026-08-21

## Repository

- Repository: `/media/xxammaxx/projekte/N8N/Morpheus_workflow`
- Branch: `master`
- Start head: `7e215aa6150ecfdb3a4cec399528f074ce81d714`
- Worktree: pre-existing untracked `.opencode/`, `.playwright-mcp/`, and
  `evidence/backup/v3-backup-20260819/` left untouched.

## Infrastructure

- Root filesystem: 937G total, 410G used, 480G free, 47% used.
- Inodes: 8% used, 57.8M free.
- Memory: 14Gi total, 8.4Gi available.
- Infrastructure gate: GREEN, no root filesystem critical condition.
- Docker and Redis are running locally; no destructive cleanup performed.

## Live Services

| Component | Observation |
|---|---|
| n8n | `http://192.168.1.52:5678/healthz` HTTP 200, `{"status":"ok"}` |
| Adapter v2 | `http://192.168.1.136:8081/healthz` HTTP 200, version 2.0.0, 0 running jobs, 1077 total jobs |
| Legacy adapter | `http://192.168.1.136:8080/healthz` HTTP 200, v1 |
| LM Studio | `192.168.1.195:1234` unreachable from this workstation, health `UNAVAILABLE` |
| Local Ollama | HTTP 200, models endpoint reachable; not part of the existing HAMH backend and not silently promoted |

## Credentials

Shell environment inventory found no values for the provider credential names.
Values were never printed or searched in shell history, logs, or Git history.
The n8n credential store and systemd environment remain opaque and were not
dumped.
