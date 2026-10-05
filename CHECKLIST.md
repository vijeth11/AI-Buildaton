# Claims Adjudication POC Checklist

`[x]` implemented and verified; `[~]` implemented but environment/release verification remains; `[ ]` pending; `[-]` explicitly deferred. See [WALKTHROUGH.md](WALKTHROUGH.md) and [README.md](README.md).

## Functional and Technical Requirements

- [x] At least three LLM-assisted agents: LangChain Intake, Fraud/Risk, and Adjudication with Pydantic structured outputs and prompt-injection boundaries.
- [x] LangGraph orchestrates LLM agents, Chroma retrieval, deterministic Rules Engine, explanations, risk/amount routing and failure handling.
- [x] LLM outcomes/status/errors/tokens and deterministic findings are persisted in claim detail/audit; tests verify structured calls via a fake client and no-key status.
- [~] Live calls use configured model name (`OPENAI_MODEL`); a real approved-provider/model call is deliberately not part of automated tests and must be validated under model/service approval.
- [x] LLMs cannot set scores, override deterministic exclusions/limits, decide final eligibility or execute a payout.
- [x] ChromaDB is required at startup and during retrieval; three authored synthetic policy PDFs and two synthetic history records are locally vectorized and queried without remote embeddings/fallback.
- [~] Structured dataset is implemented with SQLite (claims, policy snapshot, sanitized history, document/photo metadata, payout, audit); PostgreSQL + pgvector migration for production-style relational/vector storage remains pending.
- [x] More than four implemented internal API surfaces: policy, claims/history, RAG health, audit/metrics, document/photo lifecycle, synthetic repair estimate and local payout.
- [~] Weather verification calls Open-Meteo, PIN geocoding calls ZipCodebase, bank/IFSC verification calls Razorpay IFSC lookup, and Razorpay payout API returns local simulated success; MCP payout tool remains TODO and no real payout rail is used.
- [ ] Integrate all four external APIs end-to-end (weather, PIN geocoding, bank/IFSC validation, and payout provider) in both API and MCP flows with secure credentials and audited responses.
- [x] Conditional HITL routes include auto simulation, adjuster queue and supervisor queue (risk/fraud/amount escalation).
- [x] Human actions: approve, modify and re-evaluate, request info and re-evaluate, investigate, reject.
- [x] Simulated payout is local-only; not a bank/Razorpay request.
- [x] Simulated post-decision notification workflows (for payout and rejection) run as background tasks with queued/completed audit events and persisted notification job records.
- [x] Critical agent, rule, document, reviewer, failure and payout events are audited.
- [x] AgentOps captures run status, success, latency, errors, tokens/model cost, queues, Chroma and integration health.

## Data and Document Ingestion

- [x] Synthetic-only policy, claim, history, PDF, document and test data.
- [x] Authored PDFs cover policy benefits, exclusions, deductible/depreciation/limits and evidence/settlement workflow.
- [x] PDF text extraction and local image/scanned-PDF OCR integration with extracted document type/candidate fields.
- [~] Host image OCR requires Tesseract installed; absent/empty OCR is explicitly flagged for HITL. Docker image installs English Tesseract.
- [x] File type signatures/size/count checked, filenames are opaque, and storage paths are not returned to clients.
- [x] Document/photo metadata and extracted fields are queryable from claim detail and implemented MCP tools.

## Security and Governance

- [x] Signed bearer tokens, fixed development identities and endpoint role enforcement (Claims Agent/Adjuster/Supervisor/Admin).
- [x] Reviewer ID must equal authenticated subject; supervisor-routed decisions require Supervisor/Admin.
- [~] Local login is an identity stub, not production identity proof; approved VPN/SSO/Cognito is required before shared or production access.
- [~] External requests are limited to approved weather/geocode/bank endpoints (Open-Meteo, ZipCodebase, Razorpay IFSC); payout third-party operation remains an explicit stub.
- [x] `.env` is ignored by Git and Docker; existing environment files are not overwritten by setup instructions.
- [x] LLM prompt treats evidence/RAG as untrusted; model output can only add review signals, never remove deterministic holds.
- [x] Input and file validation, sanitized error/audit details, fail-closed workflow failure and CORS preflight behavior are tested.
- [ ] Add explicit API gateway throttling/rate-limiting simulation (per-role or per-route limits) and test coverage.
- [~] Production VPN/network isolation, encryption-at-rest/in-transit, malware scanning, rate limits, durable/tamper-resistant audit, retention, backup/recovery and security/privacy/legal/model-risk sign-off remain deployment gates.

## APIs, MCP and Operations

- [x] MCP implements authenticated local REST calls for policy, claim draft/create/list/detail/history, photos/documents, adjudication, evidence, reviewer decisions, payout simulation, audit, metrics, RAG health and synthetic repair estimates.
- [x] MCP supports base64 document/photo transfer without exposing local paths.
- [x] Only weather/geocode/bank/Razorpay MCP tools are TODOs; they are explicitly described and make no calls.
- [x] VS Code MCP stdio config and optional Compose MCP profile are defined; MCP is not exposed on a network port.
- [x] README documents local setup, policy-PDF generation, seed, tests, Docker commands and persistence deletion.
- [x] API/LangGraph/MCP/PDF/Tesseract Dockerfiles, Compose services, loopback port bindings, non-root API and private network are implemented.
- [~] Docker YAML parses and service topology was statically checked; Docker CLI/daemon are unavailable here, so image build, Compose startup and container healthchecks must be run on a Docker host.

## Verification

- [x] Backend tests cover deterministic thresholds, three-agent fallback/structured invocation, Chroma PDF persistence/retrieval, API/document/history flows, auth/RBAC, supervisor routing, MCP HTTP calls, Open-Meteo/ZipCodebase/Razorpay-IFSC request parameter mapping, remaining third-party 501 stubs, and failure/audit/payout behavior.
- [x] Angular unit tests cover role login/bearer propagation, queue filtering/search and work-queue rendering.
- [x] Angular production build passed before the final review-action/document-control edits; rerun the final build/test suite before demo handoff.
- [x] Local Chroma fresh-store test verified 5 documents indexed and policy/history retrieval.
- [x] 120 fictional claims seeded (30 per four scenarios); repeat run was verified idempotent.
- [ ] Verify a real model call using an approved configured service, then confirm provider-side token usage corresponds to stored AgentOps counts.
- [ ] Validate Docker images and full Compose lifecycle on an installed Docker host.
- [-] AWS deployment is deferred by request; provision nothing until the security/governance review is approved.
