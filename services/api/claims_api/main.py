from __future__ import annotations

import os
from collections import Counter
from contextlib import asynccontextmanager
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Literal

from dotenv import load_dotenv
from fastapi import FastAPI, File, HTTPException, Query, Request, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from pydantic import BaseModel

load_dotenv()

from services.api.claims_api.auth import issue_demo_token, verify_demo_token
from services.api.claims_api.repository import ClaimsRepository
from services.api.claims_api.integrations import third_party_todo
from services.api.claims_api.schemas import (
    BankVerificationRequest,
    ClaimSubmission,
    EvidenceSubmission,
    RepairEstimateRequest,
    ReviewerDecision,
    SimulatedProviderPayoutRequest,
)
from services.application.claims import ClaimsService
from services.rag.retriever import chroma_health

repository = ClaimsRepository()
claims_service = ClaimsService(repository)

@asynccontextmanager
async def lifespan(app: FastAPI):
    chroma_health()
    yield


app = FastAPI(title="Claims Lifecycle API", version="0.2.0", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=os.getenv("CORS_ORIGINS", "http://localhost:4200").split(","),
    allow_origin_regex=(
        r"^http://(localhost|127\.0\.0\.1)(:\d+)?$"
        if os.getenv("APP_ENV", "local") == "local"
        else None
    ),
    allow_credentials=False,
    allow_methods=["GET", "POST"],
    allow_headers=["Content-Type", "Authorization"],
)


class DemoLoginRequest(BaseModel):
    username: Literal["claims.agent", "adjuster.demo", "supervisor.demo", "admin.demo"]


@app.middleware("http")
async def authenticate_and_authorize(request: Request, call_next):
    path = request.url.path
    if request.method == "OPTIONS" or path in {"/health", "/docs", "/redoc", "/openapi.json", "/api/auth/login"}:
        return await call_next(request)
    if not path.startswith("/api/"):
        return await call_next(request)

    authorization = request.headers.get("Authorization", "")
    token = authorization.removeprefix("Bearer ").strip() if authorization.startswith("Bearer ") else ""
    identity = verify_demo_token(token) if token else None
    if identity is None:
        return JSONResponse(status_code=401, content={"detail": "A valid demo bearer token is required"})

    role = identity["role"]
    method = request.method.upper()
    reviewer_roles = {"adjuster", "supervisor", "admin"}
    claim_operator_roles = {"claims_agent", "adjuster", "supervisor", "admin"}
    if method == "POST" and (path.endswith("/decision") or path.endswith("/settle")) and role not in reviewer_roles:
        return JSONResponse(status_code=403, content={"detail": "Adjuster, supervisor, or admin role required"})
    if method == "POST" and path.endswith("/decision") and role == "adjuster":
        claim_id = path.split("/")[-2]
        target_claim = repository.get_claim(claim_id)
        if target_claim and target_claim.get("route_category") == "supervisor_review":
            return JSONResponse(status_code=403, content={"detail": "Supervisor or admin role required for high-risk claims"})
    if method == "POST" and (path.endswith("/adjudicate") or path.endswith("/evidence") or path in {"/api/claims", "/api/claims/drafts"} or "/photos" in path or "/documents" in path or path == "/api/integrations/repair-estimate") and role not in claim_operator_roles:
        return JSONResponse(status_code=403, content={"detail": "Claims agent, adjuster, supervisor, or admin role required"})
    external_integration_routes = (
        "/api/integrations/weather",
        "/api/integrations/geocode/",
        "/api/integrations/bank/",
        "/api/integrations/razorpay/",
    )
    if path.startswith(external_integration_routes) and role != "admin":
        return JSONResponse(status_code=403, content={"detail": "Admin role required for integration operations"})

    request.state.identity = identity
    return await call_next(request)


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok", "environment": os.getenv("APP_ENV", "local")}


@app.post("/api/auth/login")
def demo_login(credentials: DemoLoginRequest) -> dict[str, Any]:
    if os.getenv("APP_ENV", "local") != "local":
        raise HTTPException(status_code=404, detail="Development login is disabled outside local mode")
    try:
        return {**issue_demo_token(credentials.username), "auth_mode": "development_role_stub"}
    except ValueError as error:
        raise HTTPException(status_code=401, detail="Unknown demo identity") from error


@app.get("/api/rag/health")
def rag_health() -> dict[str, Any]:
    try:
        return chroma_health()
    except Exception as error:
        raise HTTPException(status_code=503, detail="Required ChromaDB policy index is unhealthy") from error


@app.get("/api/claims/history/{policy_number}")
def policy_claim_history(policy_number: str, exclude_claim_id: str | None = None) -> list[dict[str, Any]]:
    return repository.get_policy_history(policy_number, exclude_claim_id)


@app.post("/api/integrations/repair-estimate")
def mock_repair_estimate(request: RepairEstimateRequest) -> dict[str, Any]:
    base_amount = {
        "collision": 45000,
        "flood": 70000,
        "engine_water_ingress": 120000,
        "glass": 18000,
        "bodywork": 32000,
    }[request.damage_type]
    severity_factor = {"low": 0.5, "medium": 1.0, "high": 1.5}[request.severity]
    estimate = round(base_amount * severity_factor, 2)
    return {
        "estimate_id": f"EST-DEMO-{request.damage_type.upper()}-{request.severity.upper()}",
        "provider": "synthetic_repair_estimate_mock",
        "vehicle": f"{request.vehicle_make} {request.vehicle_model}",
        "damage_type": request.damage_type,
        "severity": request.severity,
        "amount": estimate,
        "currency": "INR",
        "fictional": True,
    }


@app.get("/api/integrations/weather")
def weather_verification(incident_date: str = Query(...), pincode: str = Query(..., pattern=r"^\d{6}$")) -> None:
    third_party_todo("weather provider", f"weather verification for {incident_date} and PIN {pincode}")


@app.get("/api/integrations/geocode/pincode/{pincode}")
def pincode_geocode(pincode: str) -> None:
    if len(pincode) != 6 or not pincode.isdigit():
        raise HTTPException(status_code=422, detail="PIN must contain exactly six digits")
    third_party_todo("approved PIN geocoding provider", f"latitude/longitude resolution for PIN {pincode}")


@app.post("/api/integrations/bank/verify")
def bank_verification(request: BankVerificationRequest) -> None:
    third_party_todo("approved bank/IFSC provider", "synthetic payout-profile verification")


@app.post("/api/integrations/razorpay/payout")
def razorpay_payout(request: SimulatedProviderPayoutRequest) -> None:
    third_party_todo("Razorpay payout API", "real payment creation and notification")


@app.post("/api/claims", status_code=201)
def submit_claim(submission: ClaimSubmission) -> dict[str, Any]:
    try:
        draft = claims_service.create_draft(submission.to_claim_data())
        return claims_service.submit_draft(draft["claim_id"])
    except ValueError as error:
        raise HTTPException(status_code=422, detail=str(error)) from error


@app.get("/api/policies/{policy_number}")
def get_policy(policy_number: str) -> dict[str, Any]:
    try:
        return claims_service.policy_summary(policy_number)
    except KeyError as error:
        raise HTTPException(status_code=404, detail="Active policy not found") from error


@app.post("/api/claims/drafts", status_code=201)
def create_claim_draft(submission: ClaimSubmission) -> dict[str, Any]:
    try:
        return claims_service.create_draft(submission.to_claim_data())
    except ValueError as error:
        raise HTTPException(status_code=422, detail=str(error)) from error


@app.post("/api/claims/{claim_id}/photos", status_code=201)
async def upload_claim_photos(claim_id: str, files: list[UploadFile] = File(...)) -> list[dict[str, Any]]:
    if not files or len(files) > 3:
        raise HTTPException(status_code=422, detail="Upload between one and three photos")
    try:
        return [await claims_service.add_photo(claim_id, upload) for upload in files]
    except KeyError as error:
        raise HTTPException(status_code=404, detail="Claim not found") from error
    except ValueError as error:
        raise HTTPException(status_code=409, detail=str(error)) from error


@app.post("/api/claims/{claim_id}/submit")
def submit_claim_draft(claim_id: str) -> dict[str, Any]:
    try:
        return claims_service.submit_draft(claim_id)
    except KeyError as error:
        raise HTTPException(status_code=404, detail="Claim not found") from error
    except ValueError as error:
        raise HTTPException(status_code=409, detail=str(error)) from error


@app.get("/api/claims/{claim_id}/photos")
def list_claim_photos(claim_id: str) -> list[dict[str, Any]]:
    try:
        detail = claims_service.detail(claim_id)
    except KeyError as error:
        raise HTTPException(status_code=404, detail="Claim not found") from error
    return detail["photos"]


@app.get("/api/claims/{claim_id}/photos/{photo_id}")
def get_claim_photo(claim_id: str, photo_id: str) -> FileResponse:
    photo = repository.get_photo(claim_id, photo_id)
    if photo is None or not Path(photo["storage_path"]).is_file():
        raise HTTPException(status_code=404, detail="Photo not found")
    return FileResponse(
        photo["storage_path"],
        media_type=photo["content_type"],
        filename=photo["file_name"],
    )


@app.post("/api/claims/{claim_id}/documents", status_code=201)
async def upload_claim_documents(claim_id: str, files: list[UploadFile] = File(...)) -> list[dict[str, Any]]:
    if not files or len(files) > 10:
        raise HTTPException(status_code=422, detail="Upload between one and ten supporting documents")
    try:
        return [await claims_service.add_document(claim_id, upload) for upload in files]
    except KeyError as error:
        raise HTTPException(status_code=404, detail="Claim not found") from error
    except ValueError as error:
        raise HTTPException(status_code=409, detail=str(error)) from error


@app.get("/api/claims/{claim_id}/documents")
def list_claim_documents(claim_id: str) -> list[dict[str, Any]]:
    try:
        return claims_service.detail(claim_id)["documents"]
    except KeyError as error:
        raise HTTPException(status_code=404, detail="Claim not found") from error


@app.get("/api/claims/{claim_id}/documents/{document_id}/file")
def get_claim_document(claim_id: str, document_id: str) -> FileResponse:
    document = repository.get_document(claim_id, document_id)
    if document is None or not Path(document["storage_path"]).is_file():
        raise HTTPException(status_code=404, detail="Document not found")
    return FileResponse(document["storage_path"], media_type=document["content_type"], filename=document["file_name"])


@app.get("/api/claims")
def list_claims(status: str | None = Query(default=None)) -> list[dict[str, Any]]:
    return repository.list_claims(status)


@app.get("/api/review-queue")
def review_queue() -> list[dict[str, Any]]:
    return repository.list_claims("human_review") + repository.list_claims("awaiting_evidence") + repository.list_claims("investigation")


@app.get("/api/claims/{claim_id}")
def get_claim(claim_id: str) -> dict[str, Any]:
    try:
        return claims_service.detail(claim_id)
    except KeyError as error:
        raise HTTPException(status_code=404, detail="Claim not found") from error


@app.post("/api/claims/{claim_id}/adjudicate")
def adjudicate_claim(claim_id: str) -> dict[str, Any]:
    try:
        return claims_service.adjudicate(claim_id)
    except KeyError as error:
        raise HTTPException(status_code=404, detail="Claim not found") from error
    except ValueError as error:
        raise HTTPException(status_code=409, detail=str(error)) from error


@app.post("/api/claims/{claim_id}/settle")
def settle_claim(claim_id: str) -> dict[str, Any]:
    try:
        return claims_service.settle(claim_id)
    except KeyError as error:
        raise HTTPException(status_code=404, detail="Claim not found") from error
    except ValueError as error:
        raise HTTPException(status_code=409, detail=str(error)) from error


@app.post("/api/claims/{claim_id}/decision")
def record_decision(claim_id: str, decision: ReviewerDecision, request: Request) -> dict[str, Any]:
    identity = getattr(request.state, "identity", {})
    if decision.reviewer_id != identity.get("sub"):
        raise HTTPException(status_code=403, detail="Reviewer ID must match the authenticated session")
    try:
        return claims_service.record_decision(
            claim_id,
            decision.action,
            decision.reviewer_id,
            decision.reason,
            decision.modified_amount,
        )
    except KeyError as error:
        raise HTTPException(status_code=404, detail="Claim not found") from error
    except ValueError as error:
        raise HTTPException(status_code=409, detail=str(error)) from error


@app.post("/api/claims/{claim_id}/evidence")
def submit_additional_evidence(claim_id: str, submission: EvidenceSubmission, request: Request) -> dict[str, Any]:
    identity = getattr(request.state, "identity", {})
    try:
        return claims_service.add_evidence(claim_id, submission.kind, submission.text, identity.get("sub", "unknown"))
    except KeyError as error:
        raise HTTPException(status_code=404, detail="Claim not found") from error
    except ValueError as error:
        raise HTTPException(status_code=409, detail=str(error)) from error


@app.get("/api/claims/{claim_id}/audit")
def claim_audit(claim_id: str) -> list[dict[str, Any]]:
    try:
        claims_service.detail(claim_id)
    except KeyError as error:
        raise HTTPException(status_code=404, detail="Claim not found") from error
    return repository.get_events(claim_id)


@app.get("/api/metrics")
def metrics(period: str = Query(default="today", pattern="^(today|last_7_days)$")) -> dict[str, Any]:
    all_claims = repository.list_claims()
    now = datetime.now(timezone.utc)
    start = now.replace(hour=0, minute=0, second=0, microsecond=0) if period == "today" else now - timedelta(days=7)
    claims = [
        claim for claim in all_claims
        if not claim.get("created_at") or datetime.fromisoformat(claim["created_at"]).astimezone(timezone.utc) >= start
    ]
    counts = Counter(claim.get("status", "unknown") for claim in claims)
    route_counts = Counter(claim.get("route_category", "human_queue") for claim in claims)
    payments = [claim.get("payment") for claim in claims if claim.get("payment")]
    steps = [step for claim in claims for step in claim.get("agent_steps", [])]
    llm_steps = [step for step in steps if step.get("agent", "").endswith("_llm")]
    agent_performance = []
    for agent in sorted({step["agent"] for step in steps}):
        agent_steps = [step for step in steps if step["agent"] == agent]
        latencies = sorted(step.get("duration_ms", 0) for step in agent_steps)
        p95_index = max(0, int(len(latencies) * 0.95) - 1)
        agent_performance.append({
            "agent": agent,
            "runs": len(agent_steps),
            "success_rate": round(100 * sum(step["status"] == "completed" for step in agent_steps) / len(agent_steps), 1),
            "p95_latency_ms": latencies[p95_index] if latencies else 0,
            "average_tokens": round(sum(step.get("tokens_used", 0) for step in agent_steps) / len(agent_steps)),
            "errors": sum(step.get("error_count", 0) for step in agent_steps),
        })
    end_to_end = sorted(
        sum(step.get("duration_ms", 0) for step in claim.get("agent_steps", []))
        for claim in claims
    )
    p95_end_to_end = end_to_end[max(0, int(len(end_to_end) * 0.95) - 1)] if end_to_end else 0
    input_price = os.getenv("OPENAI_INPUT_COST_PER_1K_USD", "").strip()
    output_price = os.getenv("OPENAI_OUTPUT_COST_PER_1K_USD", "").strip()
    pricing_configured = bool(input_price and output_price)
    estimated_model_cost = None
    if pricing_configured:
        estimated_model_cost = round(sum(
            step.get("input_tokens", 0) / 1000 * float(input_price)
            + step.get("output_tokens", 0) / 1000 * float(output_price)
            for step in steps
        ), 6)
    try:
        rag_status = chroma_health()
        chroma_status = rag_status["status"]
        chroma_detail = f"{rag_status['documents_indexed']} policy/history vectors in {rag_status['collection']}"
    except Exception as error:
        chroma_status = "unhealthy"
        chroma_detail = f"Required local ChromaDB is unavailable ({type(error).__name__})."
    return {
        "period": period,
        "total_claims": len(claims),
        "status_counts": dict(counts),
        "route_counts": dict(route_counts),
        "review_queue_count": counts.get("human_review", 0),
        "synthetic_payment_count": len(payments),
        "synthetic_payment_total": round(sum(payment["amount"] for payment in payments), 2),
        "claim_runs": len(claims),
        "success_rate": round(100 * sum(claim.get("status") == "paid" for claim in claims) / len(claims), 1) if claims else 0,
        "p95_end_to_end_ms": p95_end_to_end,
        "tokens_used": sum(step.get("tokens_used", 0) for step in steps),
        "estimated_model_cost_usd": estimated_model_cost,
        "model_cost_pricing_configured": pricing_configured,
        "model_name": os.getenv("OPENAI_MODEL", "gpt-5"),
        "llm_agent_calls": sum(step.get("status") == "completed" for step in llm_steps),
        "llm_agent_unavailable": sum(step.get("status") == "unavailable" for step in llm_steps),
        "agent_performance": agent_performance,
        "api_health": [
            {"name": "Claims API", "status": "healthy", "detail": "Local service response"},
            {"name": "Policy lookup", "status": "healthy", "detail": "Local fictional policy fixture"},
            {"name": "Weather verification", "status": "not_configured", "detail": "External provider is not connected"},
            {"name": "PIN verification", "status": "format_only", "detail": "Six-digit PIN format is checked locally"},
            {"name": "Bank/IFSC validation", "status": "synthetic_only", "detail": "No account number or IFSC lookup is performed"},
            {"name": "Payout adapter", "status": "synthetic_only", "detail": "Local test records only; no payment rail"},
            {"name": "LangChain LLM agents", "status": "configured" if os.getenv("OPENAI_API_KEY", "").strip() else "credentials_missing", "detail": f"Configured model: {os.getenv('OPENAI_MODEL', 'gpt-5')}"},
            {"name": "ChromaDB policy RAG", "status": chroma_status, "detail": chroma_detail},
            {"name": "LLM pricing", "status": "configured" if pricing_configured else "not_configured", "detail": "Set input/output USD per 1K token rates to estimate cost"},
        ],
        "average_tokens_per_claim": round(sum(step.get("tokens_used", 0) for step in steps) / len(claims)) if claims else 0,
    }
