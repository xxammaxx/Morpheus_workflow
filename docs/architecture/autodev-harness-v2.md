# ADR-2026-08-17: AutoDev Harness v2 — durable n8n Control Plane

Status: IMPLEMENTED (dokumentiert vor dem Bau als kanonische Bauvorgabe;
danach am realen System verifiziert)

## Kontext

Der bestehende AutoDev-Harness-v1 (Workflow `NdM7vcGvA4wkYswp`, Adapter
192.168.1.136:8080) ist ein bewährter, aber monolithischer Graph-Orchestrator
mit flachem State. v2 ersetzt ihn nicht, sondern wird als isolierte,
modulare Control Plane ergänzt (eigene Webhook-Pfade, eigener Adapter,
eigener State Store).

Bauprinzip laut Auftrag (kanonisch):

```text
LLMs ARE WORKERS. LLMs ARE NOT THE CONTROLLER.
n8n = CONTROL PLANE
Execution Worker = EXECUTION PLANE
```

## Entscheidungen

### E1. n8n = Control Plane, Adapter = Execution-Plane-Boundary

n8n (12 modulare Workflows 00–90) treibt die Zustandsmaschine deterministisch.
LLM-Arbeit findet ausschließlich im Harness Adapter bzw. auf dem Builder
(OpenCode) statt. n8n führt OpenCode NICHT direkt über Execute Command aus;
die Boundary ist `n8n → authenticated HTTP → Harness Adapter → Worker`.

### E2. Kein zweiter autonomer Orchestrator

Der Adapter ist ein job-/batch-ausführender Worker-Pool mit Ledger, KEINE
Task-Scheduling-Instanz. Alle Transitionen entscheidet n8n deterministisch
(Code Nodes, keine LLM-Controller).

### E3. Reale Parallelität via Batch-Dispatch + Barrier

```text
n8n → POST /v1/batches → Adapter (Threads) → Worker A/B/C → Barrier → n8n pollt
```

Mehrere sichtbare Canvas-Branches gelten NICHT als Parallelität. Parallelität
wird ausschließlich über überlappende `started_at`/`ended_at` im Adapter-Ledger
bewiesen (Research-Batch, Review-Batch, Batch-Canary).

### E4. Persistenter Run-State in n8n Data Tables (primär)

Data-Tables-Public-API ist in n8n 2.26.8 vorhanden (Schema geprüft:
`data_table`, `data_table_column`; persönliches Projekt
`fLfBCnB9rifW9Cu2`). Zwei Tabellen:

- `autodev_runs` — run_id, state, task_ref, repository_ref, current_job,
  decision, reason_code, created_at, updated_at, result_ref, trace_id
- `autodev_attempts` — run_id, job_id, attempt_id, status, input_contract,
  input_fingerprint, output_contract, output_fingerprint, provider, model,
  started_at, ended_at, failure_signature, strategy_delta, result_ref

Keine Prompts, keine Repo-Blobs, keine Secrets im State Store.
Fallback (falls Lizenz-Gate greift): State Store im Adapter
(SQLite/JSONL auf pve), n8n liest/schreibt über Adapter-Endpunkte.
Entscheidung empirisch in Phase C (Test `DATA_TABLES_AVAILABLE`).

### E5. Execution History ≠ System of Record

n8n-Execution-History bleibt unangetastet (nur zusätzliche Workflows).
System of Record = Data Tables (Run-State) + Adapter-Ledger (Job-Ebene).

### E6. Adapter v2 als separater Dienst

- pve, Port **8081**, Bindung nur `192.168.1.136`, eigener systemd-Service
  `autodev-harness-v2.service`, eigenes Token (0600,
  `/var/lib/autodev-harness-v2/token`), eigener State
  (`/var/lib/autodev-harness-v2/`). v1 bleibt unangetastet.
- Python 3.11 stdlib (konsistent mit v1; kein jsonschema auf pve → eigener
  Subset-Validator im Projekt, der auch für Tests genutzt wird).
- Endpunkte: `GET /healthz`, `POST /v1/jobs`, `GET /v1/jobs/{job_id}`,
  `POST /v1/batches`, `GET /v1/batches/{batch_id}`, optionale Callback-Delivery
  an `resume_url` (duplikatssicher).
- Jobtypen: baseline, research.code, research.docs, research.tests, plan,
  build, verify, fix, review.correctness, review.security, review.quality.

### E7. Abholen der Ergebnisse: Polling (primär) + Callback (unterstützt)

Der Auftrag bevorzugt Wait-Resume per Callback (§23). Empirische Entscheidung
in Phase C (Canary): Wenn n8n-Wait-Resume in Main-Mode zuverlässig läuft, wird
es genutzt; andernfalls deterministisches Polling (Wait fixed → GET → IF).
Praktisch vorgesehen: **Polling** als Primärpfad (deterministisch, kein
ungeprüfter Webhook-Surface, token-authentifiziert, idempotent), Callback-
Delivery im Adapter implementiert und per Test nachgewiesen. Abweichung wird
hier dokumentiert: Beide Mechanismen stützen denselben Data Flow.

### E8. Versionierte Data Contracts (JSON Schema, stdlib-Validatoren)

`runtime/contracts/`:
- `schemas/autodev.<name>.v1.schema.json` (Draft-07-Subset)
- `validator.py` — Subset-Validator mit maschinenlesbaren Fehlern
- `fingerprint.py` — kanonische Serialisierung (stabile Sortierung,
  ensure_ascii) → SHA-256; `x-metadata`-Felder fließen nicht in den Hash

Contracts: issue, baseline, research, plan, build-input, build-result,
verification, finding, review-batch, decision, split, run-event.

### E9. Deterministische Gates, keine LLM-Urteile

- Plan Gate: Schema/run_id/Repository/HEAD/Acceptance-Criteria/Build-Scope/
  Required-Tests/Fingerprint/Forbidden-Mutations → APPROVED/REJECTED/BLOCKED.
- Verify: deterministische Checks (pytest, Lint, Schema, Invarianten).
- Decision: vollständig deterministische Policy → DONE/FIX/SPLIT/BLOCKED.
- Security = Hard Gate: `security CRITICAL/HIGH + blocking=true` → BLOCKED,
  nie "2 von 3 PASS → DONE".

### E10. Retry nur mit Information Gain

Retry erlaubt nur wenn `attempt < max_attempts` UND failure_signature
existiert UND (new_evidence ODER strategy_delta ODER provider_change ODER
model_change). Identischer Retry → `RETRY_DENIED_NO_STRATEGY_DELTA` → SPLIT.

### E11. Plan-Safety-Canary

Plan-Agent (OpenCode, read-only: write/edit/bash/task/external_directory
denied) erhält die Aufforderung, eine Sentinel-Datei zu schreiben. Erwartung
WRITE_DENIED; Gate prüft zusätzlich Sentinel-Abwesenheit + unveränderten
Working Tree.

### E12. DFG/TSG getrennt

Data Flow Graph: Issue → Baseline → Research → Plan → ApprovedPlan →
BuildResult → Verification → ReviewBatch → Decision.
Task Schedule Graph: INTAKE → BASELINE → RESEARCH_BATCH → PLAN → PLAN_GATE →
BUILD → VERIFY → REVIEW_BATCH → DECIDE. Scheduling überspringt nie eine
Datenabhängigkeit (Jeder Job bekommt nur den vertragskonformen Input).

### E13. Observability metadata-first

- Adapter-Ledger (JSONL): run_id, job_id, attempt_id, job_type, status,
  duration_ms, backend, provider, model, input/output_contract,
  input/output_fingerprint, failure_signature, strategy_delta.
- Run-State-Transitions mit timestamp/previous_state/new_state/reason_code
  in `autodev_runs.updated_at` + run-event-Vermerk.
- Kein OTel-Aktivieren (nicht konfiguriert; keine ungefragten
  Infrastrukturänderungen). Konzept dokumentiert (Trace=Run, Span=Job,
  Attempt=Child-Span; Namespace `autodev.*`) — der Harness hängt nicht an OTel.
- Privacy by Default: METADATA_FIRST, CONTENT_OFF_BY_DEFAULT. Keine Prompts/
  Blobs/Responses/Secrets im Ledger oder State Store.

### E14. Idempotenz

Idempotency Key `run_id:job_id:attempt_id`. Doppelte Dispatches → bestehender
Job wird zurückgegeben, keine Doppelausführung. Duplikat-Callbacks werden
ignoriert. Erfolgreich abgeschlossene Jobs werden nach Adapter-Neustart nicht
erneut ausgeführt.

### E15. Recovery

Adapter-Ledger append-only mit fsync; nach Neustart werden `running`-Jobs als
`interrupted` markiert (INFRA_FAILURE). n8n-Polling erkennt das und klassifiziert
klar (keine falsche Modell-Unfähigkeitsdiagnose). Run-State (Data Tables)
überlebt Prozessausfälle.

### E16. Sicherheit

- Adapter: Token-Auth (X-Harness-Token), 0600-Tokenfile, nur internes Netz
  (192.168.1.136), kein Secret im Workflow-JSON (Credentials im
  n8n-Credential-Store).
- Webhook-Auth: Header Auth über n8n-Credential (httpHeaderAuth), keine
  hardcodierten Werte; Pfade `/autodev/start`, `/autodev/status` kollisionsfrei.
- SSRF: kein globaler Allowlist-Eingriff; nur die konkrete Adapter-Adresse
  `http://192.168.1.136:8081` wird vom n8n-Control-Plane verwendet.
- Kein Credential ersetzt, kein bestehender Webhook verändert, keine
  bestehende Workflow-ID überschrieben.

## Konsequenzen

- 12 neue Workflows (00, 01, 02, 10, 20, 30, 40, 50, 60, 70, 80, 90) →
  Workflow-Count 41 → 53.
- Neue Credentials: `autodev-n8n-api` (httpHeaderAuth, n8n-API-Key),
  `autodev-api-auth` (httpHeaderAuth, Webhook-Schutz).
- Neue Artefakte: Adapter v2, Contracts, Tests, Exporte
  (`n8n/workflows/autodev/`), Doku (`docs/architecture/`,
  `docs/operations/`).
- Verifikation über Pflichttestmatrix (§58 Auftrag) + zwei reale Vertical
  Slices (happy + fix) + Recovery + Regression.
