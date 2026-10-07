# Claims Adjudication Platform Walkthrough

## Purpose and Status

This POC addresses the claims-adjudication problem statement with the supplied architecture and guardrails. It uses only synthetic Indian motor-claim data. It implements three LangChain LLM agents orchestrated by LangGraph, mandatory ChromaDB RAG over authored policy PDFs, a deterministic Rules Engine, role-gated Human-in-the-Loop (HITL), a local simulated payout, background mock payout/decline notifications, audit history, AgentOps, authenticated MCP calls to local APIs, document ingestion, and Docker packaging. AWS is deferred.

No customer/production/PII/PCI/PHI/bank data may be entered. Weather verification calls Open-Meteo using latitude/longitude and date ranges, pincode geocoding calls ZipCodebase using `ZIPCODE_API_KEY`, bank verification calls Razorpay IFSC lookup using IFSC code input, and Razorpay payout endpoint returns a local simulated success response for `bankaccount` and `amount`. No real payout rail is invoked. A deterministic synthetic garage-estimate API and local mock payout are implemented. This is not a production insurance or payment system.

## Claim and Agent Flow

1. Angular/MCP obtains a signed short-lived local development session. API middleware validates the token and enforces claims-agent, adjuster, supervisor, or admin permissions. Reviewer identity is bound to the signed session.
2. Policy lookup enriches a claim draft with fictional policyholder, vehicle, coverage, deductible and limits. The intake flow supports incident details, car photos, and supporting PDFs/images.
3. **Intake Agent (LangChain LLM)** extracts candidate facts, identifies missing/ambiguous fields and contradictions, and returns typed structured output. It cannot overwrite request fields, set scores, or decide coverage.
4. **Mandatory ChromaDB RAG** extracts and vectorizes the synthetic policy PDFs and synthetic claim-history records. Retrieved text is untrusted and every result has a source ID, excerpt and distance.
5. **Fraud & Risk Agent (LangChain LLM)** analyzes structured claim facts and sanitized prior synthetic claims, returning evidence-backed fraud/risk indicators and review advice. Numeric scores remain deterministic/server-owned.
6. **Adjudication Agent (LangChain LLM + RAG)** interprets retrieved policy clauses, identifies applicable supplied source IDs and unresolved questions. Its recommendation is advisory.
7. **Deterministic Rules Engine** decides coverage/exclusions, evidence sufficiency, payment profile validity, deductible, depreciation, limit, payable amount, numeric risk/fraud thresholds and amount bands. Agent signals may add human-review flags; model text can never cancel a rule failure, numeric result, exclusion or review requirement.
8. **LangGraph risk-and-amount routing:**
   - Automatic simulated payout only when every deterministic eligibility check passes, both scores are strictly below base thresholds, payout is positive, garage estimate is at most INR 50,000, and required evidence is complete.
   - Adjuster review for medium-risk/ambiguous cases, threshold breaches or amounts above INR 50,000.
   - Supervisor review for risk score >= 80, fraud score >= 70, both base risk/fraud thresholds breached, or amount above INR 200,000.
9. Adjusters/supervisors can **Approve**, **Modify & re-evaluate**, **Request Info**, **Investigate** or **Reject**, subject to role. Modify updates the estimate and reruns LangGraph/rules. Request Info marks the claim `awaiting_evidence`; added evidence is appended/audited and reruns the workflow.
10. Every agent assessment/status/duration/token/error/reason-code, deterministic rule result, retrieved citation, evidence/document event, reviewer action, simulated payout, and queued/completed notification workflow event is stored and visible in claim detail/AgentOps. Workflow failure records a safe audit event and holds the claim for review; it never pays.

## LangGraph and LangChain Architecture

```text
Angular or MCP client -> signed local role session -> FastAPI validation/RBAC
                                              |
                                              v
LangGraph StateGraph
  Intake Agent (structured LangChain LLM)
    -> required ChromaDB policy-PDF/history retrieval
    -> Fraud & Risk Agent (structured LangChain LLM + SQLite claim history)
    -> Adjudication Agent (structured LangChain LLM + retrieved policy passages)
    -> deterministic coverage/evidence/deductible/depreciation/limit/risk Rules Engine
    -> optional LangChain reviewer explanation
    -> conditional router: auto payout | adjuster | supervisor
                                              |
                             SQLite claims, audit, payment, photo/document metadata
                             local document/photo file store; local simulated payout
```

Each LLM agent uses a Pydantic structured output contract. Prompts explicitly label user narrative, OCR, uploaded content and RAG text as untrusted data. Models have no payment or arbitrary tool access. GPT output cannot set numeric scores, change policy facts, override exclusions/rules or authorize payment. `OPENAI_MODEL` selects the LangChain `ChatOpenAI` model. Timeout/retry controls are `LLM_TIMEOUT_SECONDS` (default `90`), `LLM_MAX_RETRIES` (default `1`), `LLM_MAX_COMPLETION_TOKENS` (default `1200`), and `LLM_REASONING_EFFORT` (default `minimal`). Routine tests mock calls and disable external LLM requests; the live approved model call is a separate operational validation. If model credentials are missing, agent cards report `unavailable`; if a model call fails or returns empty structured output, a low-confidence safe fallback is recorded and deterministic rules remain authoritative.

## Required ChromaDB and Policy PDFs

Synthetic authored PDFs in `data/policies-pdf/`:

- `DIC-PC-0091273-coverage.pdf`
- `DIC-PC-0091273-exclusions.pdf`
- `DIC-PC-0091273-claims-evidence.pdf`

Regenerate using `python -m scripts.build_policy_pdfs`. At API startup, pypdf extracts them and ChromaDB indexes them plus two synthetic history records in persistent collection `claims-policy-kb-v2`. A deterministic local feature-hash vectorizer is used; there is no remote embedding service, model download, web scraping or static fallback. Each adjudication queries ChromaDB. Missing/corrupt PDFs, Chroma failures, or empty retrieval fail API readiness or route runtime failures to human review. `GET /api/rag/health` verifies PDF/vector counts.

For claim-creation upload testing in the UI, synthetic dummy files are provided under `data/claim-upload-photos/` and `data/claim-upload-documents/`. Usage guidance is documented in `data/README.md`.

## Document Ingestion and Storage

| Data | Storage and processing | Retrieval |
| --- | --- | --- |
| Policy/vehicle | Synthetic `data/policies.json` fixture | `GET /api/policies/{policy_number}` |
| Claim/deterministic assessment | SQLite `claims` row with policy snapshot, facts, agent outputs and rules | `/api/claims`, `/api/claims/{id}` |
| Photos | Up to 3 JPEG/PNG/WebP images, 5 MB each; signature checked, opaque filename, local file bytes + SQLite metadata | `/photos` metadata and `/photos/{photo_id}` bytes |
| Supporting documents | Up to 10 PDF/JPEG/PNG/WebP files, 10 MB each; signature checked, opaque filename, local file bytes + SQLite metadata | `/documents` metadata and `/documents/{document_id}/file` bytes |
| PDF/scanned text | pypdf extracts text PDFs; pytesseract/Tesseract performs local OCR on images/scans when installed; filename/text rules classify document and parse candidate date/PIN/amount | Intake LLM and evidence checks |
| OCR fallback | If OCR is unavailable, errors, or yields no text, extraction status explicitly requires review; it is not asserted as verified | Reviewer detail and deterministic hold flag |
| Claim history | Sanitized synthetic prior claim fields in SQLite | `/api/claims/history/{policy_number}` and Fraud/Risk context |
| RAG | Authored PDFs + history in Chroma | LangGraph retrieval node with citations |
| Audit/payout | Separate ordered SQLite audit events and simulated payment records | Claim detail, `/audit`, AgentOps |

Storage paths never leave the API. Local files and SQLite are demo adapters, not encrypted object storage, malware scanning, retention/deletion, or tamper-proof production audit solutions.

## API and MCP Coverage

### Implemented local API operations

- Authentication and local role stub: `POST /api/auth/login`.
- Policy: `GET /api/policies/{policy_number}`.
- Claim lifecycle: `POST /api/claims`, `/api/claims/drafts`, `/{id}/submit`, `/{id}/adjudicate`, `/{id}/decision`, `/{id}/evidence`, `/{id}/settle`.
- Claim reads/history: `GET /api/claims`, `/{id}`, `/api/claims/history/{policy_number}`, `/api/review-queue`, `/{id}/audit`.
- Photos/documents: upload/list/file endpoints under `/api/claims/{id}/photos` and `/documents`.
- Observability/RAG: `GET /api/metrics`, `/api/rag/health`.
- Local integration: `POST /api/integrations/repair-estimate` deterministic synthetic estimate.

### Third-party integration boundaries

`GET /api/integrations/weather` calls Open-Meteo (`/v1/forecast`) with `latitude`, `longitude`, `start_date`, `end_date`, and hourly `temperature_2m`. `GET /api/integrations/geocode/pincode/{pincode}` calls ZipCodebase search with `codes={pincode}` and `apikey` from `ZIPCODE_API_KEY`. `POST /api/integrations/bank/verify` calls Razorpay IFSC lookup (`https://ifsc.razorpay.com/{IFSC}`) with `ifsc_code` from the request body. `POST /api/integrations/razorpay/payout` returns local simulated success for `bankaccount` and `amount` without calling a real payout rail. MCP tools for weather/geocode/bank/Razorpay still contain descriptive TODO boundaries and make no network calls. The local `ClaimsService` payout is a distinct simulated task; it does not contact Razorpay/banks.

The separate MCP stdio server implements HTTP calls to all local API functions, including auth, claim/document/photo transfer, history, RAG health, metrics and repair estimate. Binary data transfers as base64 in MCP arguments/results; machine paths are never exposed. Only named third-party integrations are unimplemented. Host VS Code configuration is `.vscode/mcp.json`; Docker exposes MCP as an opt-in stdio profile, never a public port.

## Guardrails and Access

- Synthetic data only; no real customer, policyholder, bank, PCI/PHI/PII or confidential information.
- Signed bearer token required for API routes (except health/docs/local login); role checks protect reviewer and supervisor actions. A reviewer cannot claim another reviewer ID.
- Local development login is a fixed-user role stub without identity proof. It is only for loopback development, not production authentication. Replace with approved TGS VPN/SSO/Cognito before shared/production access. `AUTH_SIGNING_SECRET` is required outside local mode.
- Docker UI/API ports bind to loopback; Compose has a private network; FastAPI runs non-root. Docker/Compose is not installed in the current environment, so image/runtime validation remains pending.
- `.env` is gitignored and dockerignored. Never overwrite a populated `.env` with `.env.example`, print, or commit its credentials.
- Photo/document types, byte sizes and signatures are checked; filenames are opaque; OCR failures require review.
- All LLM output is advisory, structured and auditable. No model tool grants payment or API authority.
- External integrations are explicitly unavailable until approved provider selection, licensing, credentials and security review.
- AWS deployment, TLS/KMS, rate limiting, SSO, durable retention, resilience, threat modeling and organizational security/privacy/legal/model-risk approval remain later release gates.

## Success Metrics and Observability

AgentOps and persisted graph telemetry report executions/status/success, latency/p95, per-agent errors, input/output tokens, model configuration/cost, human/supervisor queue volume, simulated settlement totals, Chroma readiness and external API health. Unavailable LLM calls are not successful LLM runs; cost is `Not priced` unless input/output per-1K rates are configured. Audit history records all key state transitions and failures.

## Local Setup and Run

1. Install Python 3.12+, Node 20/npm. Tesseract is optional on the host; without it image/scanned-PDF OCR is flagged for review. The Docker API image installs English Tesseract.
2. Create a venv and install `python -m pip install -r requirements.txt`.
3. Create `.env` only if absent: `if (!(Test-Path .env)) { Copy-Item .env.example .env }`. Preserve a populated existing file.
4. Configure an approved model key in `.env` only when authorized; no live model call is needed for normal tests or deterministic fallback.
5. Run `python -m scripts.build_policy_pdfs` if the authored PDFs are absent; then run `python -m scripts.seed_demo` (30 records in each of 4 synthetic scenarios, 120 total; idempotent).
6. Start API: `python -m uvicorn services.api.claims_api.main:app --reload --host 127.0.0.1 --port 8000`.
7. Start UI separately: `cd frontend; npm ci; npm start -- --host 127.0.0.1 --port 4300`.
8. Open `http://127.0.0.1:4300/`, choose a dev role, and use `DIC-PC-0091273`. API docs: `http://127.0.0.1:8000/docs`; RAG health requires a bearer token at `/api/rag/health`.
9. Run `python -m pytest -q`; from `frontend/`, run `ng test --watch=false --browsers=ChromeHeadless` and `ng build`.

## Docker Compose

Docker Desktop/Compose is required and was unavailable in the current environment; config is statically validated but image/runtime execution still needs a Docker host.

```powershell
if (!(Test-Path .env)) { Copy-Item .env.example .env }
docker compose config
docker compose up --build -d
docker compose exec api python -m scripts.seed_demo
docker compose ps
```

UI `http://127.0.0.1:4300/`, API docs `http://127.0.0.1:8000/docs`. Stop: `docker compose down`. To remove persisted claims, document/photo files and vectors, explicitly run `docker compose down -v`. MCP stdio: `docker compose --profile mcp run --rm mcp`; do not publish it as HTTP.

## AWS Later

AWS is optional for this POC. Later work must define private VPC access, approved SSO/Cognito, TLS/KMS, secret management, durable Chroma/object storage, secure external-provider adapters, backups, audit retention, monitoring/alerts, authorization/load/recovery tests and organizational review before any real data or payment integration.
