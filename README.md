# Claims Adjudication Platform (POC)

A synthetic-data-only motor-claims workflow built with Angular, FastAPI, LangGraph, LangChain, and mandatory local ChromaDB retrieval. It demonstrates three LLM-assisted claim agents, a deterministic settlement Rules Engine, human review, simulated payout, audit history, and AgentOps metrics.

> This is a local buildathon POC, not an insurance production system. Never enter customer, production, PCI, PHI, PII, bank-account, or confidential data. Real weather, geocoding, bank verification, and Razorpay payout are not connected. The API/MCP contracts mark these integrations as TODO and return HTTP 501. The only payout implemented is a synthetic local simulation.

## Architecture

1. **Intake Agent (LangChain LLM):** extracts candidate facts, finds missing/ambiguous fields and inconsistencies. It cannot overwrite submitted fields.
2. **Fraud & Risk Agent (LangChain LLM):** reviews structured facts and sanitized prior synthetic claims, returning evidence-backed indicators. Numeric scores remain server-owned.
3. **Adjudication Agent (LangChain LLM + RAG):** interprets retrieved policy passages and cites only returned source IDs. Its output is advisory.
4. **Rules Engine (deterministic):** decides coverage, exclusions, evidence sufficiency, deductible, depreciation, limits, score thresholds, and the INR 50,000 auto-settlement cap. LLMs cannot approve or pay.
5. **LangGraph:** runs LLM Intake -> mandatory ChromaDB PDF/history retrieval -> LLM Fraud/Risk -> LLM Adjudication -> deterministic Rules Engine -> optional explanation -> adjuster/supervisor routing. Agent outputs, status, duration, tokens, errors and citations are stored.
6. **Human review:** actions include approve, modify/re-evaluate, request info/re-evaluate, investigate and reject. Supervisor-routed claims require supervisor/admin role; all actions and local simulated payouts are audited.

The model name is read from `OPENAI_MODEL`. An API key is required for live LLM calls. Without one, the three LLM nodes report `unavailable`, record zero tokens and an explanatory status, and deterministic processing continues. Do not treat fallback as live LLM-agent execution. Use only approved models/services.

Local API routes require a signed, short-lived bearer session. The development role selector maps fixed demo identities to role permissions; it is not identity proof and is only for loopback development. Non-local startup requires `AUTH_SIGNING_SECRET`; production identity must be replaced with approved SSO/Cognito.

## Prerequisites

- Python 3.12+
- Node.js 20 LTS and npm
- Docker Desktop with Docker Compose v2 for containerized run
- An approved model API key only if you are authorized to call the configured model
- Tesseract OCR for host-based image/scanned-PDF OCR (otherwise the document is flagged for review; the Docker image installs English Tesseract)

## Local Setup

From the repository root in PowerShell:

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
```

The repository includes three authored synthetic motor-policy PDFs under `data/policies-pdf/`. Regenerate them only from the local script if needed:

```powershell
python -m scripts.build_policy_pdfs
```

ChromaDB is mandatory. At API startup, the service parses and indexes every PDF plus two authored synthetic-history records into the persistent `claims-policy-kb-v2` collection using a deterministic local feature-hash embedding. No external embedding endpoint or model download is required. If the PDFs, parser, ChromaDB, or collection cannot be opened, API startup fails rather than silently using a non-vector fallback. Health is available at `/api/rag/health`.

Create `.env` from `.env.example` only if `.env` does not already exist (`if (!(Test-Path .env)) { Copy-Item .env.example .env }`). Do not overwrite an existing environment file. Keep `.env` private and ignored by Git. Set `OPENAI_API_KEY` directly in that file only when authorized. Optional cost rates are USD per 1,000 input/output tokens; without both rates AgentOps shows `Not priced`.

Seed 30 fictional claims per scenario (120 total; repeat-safe):

```powershell
python -m scripts.seed_demo
```

Run the API and UI in separate terminals:

```powershell
python -m uvicorn services.api.claims_api.main:app --reload --host 127.0.0.1 --port 8000
```

```powershell
Push-Location frontend
npm ci
npm start -- --host 127.0.0.1 --port 4300
Pop-Location
```

Open `http://127.0.0.1:4300/`, select a development role, and use the synthetic policy `DIC-PC-0091273`. If the chosen port is occupied, choose another local port; local CORS permits localhost only. API docs are at `http://127.0.0.1:8000/docs`.

### MCP Server (Local)

The MCP stdio server implements the local policy, claim, history, photo, review, audit, RAG-health, metrics and synthetic repair-estimate APIs by calling FastAPI. For the host configuration in `.vscode/mcp.json`, start FastAPI first, then let VS Code launch the server over stdio. For a terminal smoke start:

```powershell
python -m services.mcp_server.server
```

The process waits for MCP stdio input. Do not run it as a public HTTP server. MCP obtains a signed development adjuster session and calls the authenticated local API. Weather, pincode geocoding, bank verification, and real Razorpay payout tools are explicit TODOs and do not make external network calls.

## Docker Compose

Docker Compose binds the web UI and API to loopback only. SQLite/photo files and ChromaDB have separate named volumes. The Nginx UI proxies `/api` internally to FastAPI. A `.env` file is required by Compose; it is not copied into either image.

```powershell
if (!(Test-Path .env)) { Copy-Item .env.example .env }
# Add an approved key directly to .env only if permitted by organizational policy.
docker compose config
docker compose up --build -d
```

Open `http://127.0.0.1:4300/`; API docs are at `http://127.0.0.1:8000/docs`. Seed the database once:

```powershell
docker compose exec api python -m scripts.seed_demo
```

Inspect service status/logs and stop the stack:

```powershell
docker compose ps
docker compose logs -f api web
docker compose down
```

To remove demo claims, images, and vector data as well, explicitly remove the named volumes with `docker compose down -v`. This deletes the local demo state.

Run the separate MCP process in its Compose profile when an MCP client is attached to its stdin/stdout:

```powershell
docker compose --profile mcp run --rm mcp
```

The MCP profile is opt-in because stdio is a process transport, not a network service. Do not publish the MCP container port.

## API Surface

- `GET /api/policies/{policy_number}`: fictional policy/vehicle/coverage lookup.
- `POST /api/claims/drafts`, `POST /api/claims/{id}/photos`, `POST /api/claims/{id}/submit`: draft, validated photo upload, then LangGraph run.
- `POST /api/claims`: one-step claim submission.
- `GET /api/claims`, `GET /api/claims/{id}`, `GET /api/claims/history/{policy_number}`, `GET /api/review-queue`.
- `POST /api/claims/{id}/adjudicate`, `/decision`, `/evidence`, `/settle`; modify and request-info rerun rules; settlement rechecks the deterministic gate.
- `POST /api/claims/{id}/documents`, `GET /api/claims/{id}/documents`, `GET /api/claims/{id}/documents/{document_id}/file`: validated local document ingestion and retrieval.
- `GET /api/claims/{id}/audit`, `/photos`, `/photos/{photo_id}`, `/api/metrics`, `/api/rag/health`.
- `POST /api/integrations/repair-estimate`: local deterministic synthetic repair-estimate mock.
- `GET /api/integrations/weather`, `GET /api/integrations/geocode/pincode/{pincode}`, `POST /api/integrations/bank/verify`, `POST /api/integrations/razorpay/payout`: documented external integration boundaries; return 501 TODO, no provider request is made.

Photo files are restricted to three JPEG/PNG/WebP images, 5 MB each, checked against file signatures, assigned opaque names, and stored separately from SQLite metadata. Local file storage is a demo adapter, not production object storage or malware scanning.

Supporting documents allow up to ten PDF/JPEG/PNG/WebP files (10 MB each). Text PDFs are extracted with pypdf, scanned PDFs/images use local Tesseract when installed, and extracted candidate fields are never treated as authoritative. OCR unavailable/empty results are flagged for reviewer follow-up.

## Tests and Metrics

```powershell
python -m pytest -q
Push-Location frontend
ng test --watch=false --browsers=ChromeHeadless
ng build
Pop-Location
```

Tests cover deterministic thresholds, mocked LangChain calls, injection-safe prompts, Chroma PDF indexing, auth/RBAC and supervisor routing, PDF/OCR document ingestion, photos/history/MCP REST calls, third-party TODO responses, fail-closed audit/payment behavior, and Angular session/queue behavior.

AgentOps reports status, success rate, latency, token consumption, errors, model configuration, Chroma health, and third-party readiness. LLM tokens are zero when model calls are unavailable; cost is shown only when both token price rates are configured.

## Security and Release Boundaries

- Synthetic data only; no real policy/customer/payment credentials.
- Localhost-bound development ports, private Compose network, signed role sessions and route-level RBAC. The development login is a role stub, not a verified user credential; VPN/SSO/Cognito, robust identity proofing and production RBAC integration remain release requirements.
- `.env`, SQLite, image files, and Chroma persistence are excluded from source control/image build context.
- LLM text is treated as untrusted advice; scores, coverage status, settlement amount and payment authorization are deterministic server-owned outputs.
- Human review and audit are required for exceptions; mock payout cannot reach a payment rail. Modify and Request Info actions append events and rerun adjudication after user input.
- AWS deployment is deferred. Before any real data or payment use, complete organization-approved model/service review, VPN/identity/RBAC, TLS and encrypted storage, retention, malware scanning, threat modeling, load/recovery, privacy, legal and operational review.

See [WALKTHROUGH.md](WALKTHROUGH.md) for workflow and data mapping, and [CHECKLIST.md](CHECKLIST.md) for requirement status.
