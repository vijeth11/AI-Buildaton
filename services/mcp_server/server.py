"""Claims API MCP client. Local API tools are implemented; only external providers are TODOs."""

from __future__ import annotations

import base64
import json
import os
from pathlib import PurePosixPath

import httpx
from mcp.server.fastmcp import FastMCP

server = FastMCP("claims-lifecycle-tools")
API_BASE_URL = os.getenv("CLAIMS_API_BASE_URL", "http://127.0.0.1:8000").rstrip("/")
_access_token: str | None = None


async def _request(method: str, path: str, *, params: dict | None = None, body: dict | None = None, files: dict | None = None):
    global _access_token
    async with httpx.AsyncClient(base_url=API_BASE_URL, timeout=45.0) as client:
        if path != "/api/auth/login" and _access_token is None:
            login = await client.post("/api/auth/login", json={"username": "adjuster.demo"})
            if login.is_error:
                raise RuntimeError(f"Claims API development login failed ({login.status_code})")
            _access_token = login.json()["access_token"]
        headers = {"Authorization": f"Bearer {_access_token}"} if _access_token and path != "/api/auth/login" else None
        response = await client.request(method, path, params=params, json=body, files=files, headers=headers)
        if response.status_code == 401 and path != "/api/auth/login":
            login = await client.post("/api/auth/login", json={"username": "adjuster.demo"})
            if login.is_error:
                raise RuntimeError(f"Claims API development login failed ({login.status_code})")
            _access_token = login.json()["access_token"]
            response = await client.request(
                method,
                path,
                params=params,
                json=body,
                files=files,
                headers={"Authorization": f"Bearer {_access_token}"},
            )
    try:
        result = response.json()
    except ValueError:
        result = {"detail": response.text}
    if response.is_error:
        raise RuntimeError(f"Claims API {method} {path} returned {response.status_code}: {result.get('detail', result)}")
    return result


def _json(result) -> str:
    return json.dumps(result, ensure_ascii=False, default=str)


@server.tool()
async def lookup_policy(policy_number: str) -> str:
    """GET /api/policies/{policy_number}: lookup synthetic policy, vehicle and coverage facts."""
    return _json(await _request("GET", f"/api/policies/{policy_number}"))


@server.tool()
async def submit_claim(
    policy_number: str,
    loss_type: str,
    loss_description: str,
    incident_date: str,
    incident_pincode: str,
    incident_location: str,
    garage_estimate: float,
) -> str:
    """POST /api/claims: submit typed claim facts; risk/fraud scores remain server-owned."""
    body = {
        "policy_number": policy_number,
        "loss_type": loss_type,
        "loss_description": loss_description,
        "incident_date": incident_date,
        "incident_pincode": incident_pincode,
        "incident_location": incident_location,
        "garage_estimate": garage_estimate,
        "currency": "INR",
        "fictional": True,
    }
    return _json(await _request("POST", "/api/claims", body=body))


@server.tool()
async def create_claim_draft(
    policy_number: str,
    loss_type: str,
    loss_description: str,
    incident_date: str,
    incident_pincode: str,
    incident_location: str,
    garage_estimate: float,
) -> str:
    """POST /api/claims/drafts: create a policy-enriched claim draft before attachments."""
    body = {
        "policy_number": policy_number,
        "loss_type": loss_type,
        "loss_description": loss_description,
        "incident_date": incident_date,
        "incident_pincode": incident_pincode,
        "incident_location": incident_location,
        "garage_estimate": garage_estimate,
        "currency": "INR",
        "fictional": True,
    }
    return _json(await _request("POST", "/api/claims/drafts", body=body))


@server.tool()
async def upload_claim_photo(claim_id: str, file_name: str, content_type: str, content_base64: str) -> str:
    """Upload a synthetic claim photo to a draft; bytes are validated by the Claims API."""
    allowed_types = {"image/jpeg", "image/png", "image/webp"}
    if content_type not in allowed_types:
        raise ValueError("Photo type must be JPEG, PNG, or WebP")
    try:
        content = base64.b64decode(content_base64, validate=True)
    except ValueError as error:
        raise ValueError("Photo content must be valid base64") from error
    safe_name = PurePosixPath(file_name.replace("\\", "/")).name
    result = await _request(
        "POST",
        f"/api/claims/{claim_id}/photos",
        files={"files": (safe_name, content, content_type)},
    )
    return _json(result)


@server.tool()
async def submit_claim_draft(claim_id: str) -> str:
    """POST /api/claims/{claim_id}/submit: run the LangGraph workflow after document upload."""
    return _json(await _request("POST", f"/api/claims/{claim_id}/submit", body={}))


@server.tool()
async def list_claims(status: str = "") -> str:
    """GET /api/claims with an optional status filter."""
    return _json(await _request("GET", "/api/claims", params={"status": status} if status else None))


@server.tool()
async def get_claim(claim_id: str) -> str:
    """GET /api/claims/{claim_id}: return facts, all agent assessments, rules, photos and audit history."""
    return _json(await _request("GET", f"/api/claims/{claim_id}"))


@server.tool()
async def get_claim_history(policy_number: str, exclude_claim_id: str = "") -> str:
    """GET /api/claims/history/{policy_number}: retrieve sanitized prior synthetic claim facts."""
    params = {"exclude_claim_id": exclude_claim_id} if exclude_claim_id else None
    return _json(await _request("GET", f"/api/claims/history/{policy_number}", params=params))


@server.tool()
async def get_claim_photos(claim_id: str) -> str:
    """GET /api/claims/{claim_id}/photos metadata; never expose local storage paths."""
    return _json(await _request("GET", f"/api/claims/{claim_id}/photos"))


@server.tool()
async def upload_claim_document(claim_id: str, file_name: str, content_type: str, content_base64: str) -> str:
    """Upload a synthetic PDF/image claim document; API extracts local PDF text or flags unavailable OCR."""
    if content_type not in {"application/pdf", "image/jpeg", "image/png", "image/webp"}:
        raise ValueError("Document type must be PDF, JPEG, PNG, or WebP")
    try:
        content = base64.b64decode(content_base64, validate=True)
    except ValueError as error:
        raise ValueError("Document content must be valid base64") from error
    safe_name = PurePosixPath(file_name.replace("\\", "/")).name
    result = await _request(
        "POST",
        f"/api/claims/{claim_id}/documents",
        files={"files": (safe_name, content, content_type)},
    )
    return _json(result)


@server.tool()
async def get_claim_documents(claim_id: str) -> str:
    """GET /api/claims/{claim_id}/documents safe metadata, extraction status, and extracted fields."""
    return _json(await _request("GET", f"/api/claims/{claim_id}/documents"))


@server.tool()
async def get_claim_document_file(claim_id: str, document_id: str) -> str:
    """Retrieve a linked document and return its bytes as base64; no local path is exposed."""
    async with httpx.AsyncClient(base_url=API_BASE_URL, timeout=45.0) as client:
        if _access_token is None:
            login = await client.post("/api/auth/login", json={"username": "adjuster.demo"})
            if login.is_error:
                raise RuntimeError(f"Claims API development login failed ({login.status_code})")
            token = login.json()["access_token"]
        else:
            token = _access_token
        response = await client.get(
            f"/api/claims/{claim_id}/documents/{document_id}/file",
            headers={"Authorization": f"Bearer {token}"},
        )
    if response.is_error:
        raise RuntimeError(f"Claims API document retrieval returned {response.status_code}")
    return _json({"content_type": response.headers.get("content-type"), "content_base64": base64.b64encode(response.content).decode("ascii")})


@server.tool()
async def get_claim_photo(claim_id: str, photo_id: str) -> str:
    """Retrieve a linked image and return its content as base64 for an authorized caller."""
    async with httpx.AsyncClient(base_url=API_BASE_URL, timeout=45.0) as client:
        response = await client.get(f"/api/claims/{claim_id}/photos/{photo_id}")
    if response.is_error:
        raise RuntimeError(f"Claims API photo retrieval returned {response.status_code}")
    return _json({"content_type": response.headers.get("content-type"), "content_base64": base64.b64encode(response.content).decode("ascii")})


@server.tool()
async def get_review_queue() -> str:
    """GET /api/review-queue."""
    return _json(await _request("GET", "/api/review-queue"))


@server.tool()
async def adjudicate_claim(claim_id: str) -> str:
    """POST /api/claims/{claim_id}/adjudicate: run Intake, Fraud/Risk, Adjudication and Rules nodes."""
    return _json(await _request("POST", f"/api/claims/{claim_id}/adjudicate", body={}))


@server.tool()
async def settle_claim(claim_id: str) -> str:
    """POST /api/claims/{claim_id}/settle: invoke only the local simulated payout gate."""
    return _json(await _request("POST", f"/api/claims/{claim_id}/settle", body={}))


@server.tool()
async def record_reviewer_decision(
    claim_id: str,
    action: str,
    reviewer_id: str,
    reason: str,
    modified_amount: float | None = None,
) -> str:
    """POST /api/claims/{claim_id}/decision with an audited human action."""
    body = {"action": action, "reviewer_id": reviewer_id, "reason": reason}
    if modified_amount is not None:
        body["modified_amount"] = modified_amount
    return _json(await _request("POST", f"/api/claims/{claim_id}/decision", body=body))


@server.tool()
async def submit_additional_evidence(claim_id: str, kind: str, text: str) -> str:
    """POST /api/claims/{claim_id}/evidence: append requested evidence and rerun LangGraph."""
    return _json(await _request("POST", f"/api/claims/{claim_id}/evidence", body={"kind": kind, "text": text}))


@server.tool()
async def get_claim_audit(claim_id: str) -> str:
    """GET /api/claims/{claim_id}/audit."""
    return _json(await _request("GET", f"/api/claims/{claim_id}/audit"))


@server.tool()
async def get_metrics(period: str = "today") -> str:
    """GET /api/metrics for today or the last seven days."""
    return _json(await _request("GET", "/api/metrics", params={"period": period}))


@server.tool()
async def get_policy_rag_health() -> str:
    """GET /api/rag/health: verify mandatory local ChromaDB policy indexing."""
    return _json(await _request("GET", "/api/rag/health"))


@server.tool()
async def get_synthetic_repair_estimate(vehicle_make: str, vehicle_model: str, damage_type: str, severity: str) -> str:
    """POST /api/integrations/repair-estimate: execute the local synthetic estimate adapter."""
    body = {"vehicle_make": vehicle_make, "vehicle_model": vehicle_model, "damage_type": damage_type, "severity": severity, "fictional": True}
    return _json(await _request("POST", "/api/integrations/repair-estimate", body=body))


@server.tool()
async def verify_weather_third_party(incident_date: str, pincode: str) -> str:
    """TODO: integrate an approved weather API; currently returns HTTP 501 and does not make external calls."""
    raise NotImplementedError("TODO: weather provider contract, credentials, timeout, and provenance review")


@server.tool()
async def geocode_pincode_third_party(pincode: str) -> str:
    """TODO: integrate an approved pincode-to-latitude/longitude API."""
    raise NotImplementedError("TODO: geocoding provider selection, data licensing, and validation")


@server.tool()
async def verify_bank_details_third_party(synthetic_payout_profile: str) -> str:
    """TODO: integrate approved bank/IFSC verification without collecting live bank details in this demo."""
    raise NotImplementedError("TODO: approved bank verification API, PCI review, authentication, and data minimization")


@server.tool()
async def razorpay_payout_third_party(claim_id: str, amount: float, currency: str = "INR") -> str:
    """TODO: integrate Razorpay after approval; current payout is local simulation only."""
    raise NotImplementedError("TODO: Razorpay authorization, idempotency, reconciliation, notification, and security review")


if __name__ == "__main__":
    server.run(transport="stdio")
