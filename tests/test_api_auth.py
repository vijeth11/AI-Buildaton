from __future__ import annotations

from fastapi.testclient import TestClient
from pathlib import Path

from services.api.claims_api.main import app


def test_api_requires_signed_local_demo_session():
    client = TestClient(app)
    assert client.get("/api/claims").status_code == 401

    login = client.post("/api/auth/login", json={"username": "adjuster.demo"})
    assert login.status_code == 200
    token = login.json()["access_token"]
    response = client.get("/api/claims", headers={"Authorization": f"Bearer {token}"})
    assert response.status_code == 200
    assert login.json()["role"] == "adjuster"


def test_local_cors_preflight_allows_bearer_header_without_bypassing_api_auth():
    client = TestClient(app)
    response = client.options(
        "/api/claims",
        headers={
            "Origin": "http://127.0.0.1:4300",
            "Access-Control-Request-Method": "GET",
            "Access-Control-Request-Headers": "authorization",
        },
    )
    assert response.status_code == 200
    assert response.headers["access-control-allow-origin"] == "http://127.0.0.1:4300"
    assert client.get("/api/claims").status_code == 401


def test_demo_role_permissions_are_enforced():
    client = TestClient(app)
    login = client.post("/api/auth/login", json={"username": "claims.agent"})
    token = login.json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}

    assert client.post(
        "/api/claims/CLM-DEMO-UNKNOWN/decision",
        headers=headers,
        json={"action": "approve", "reviewer_id": "claims.agent", "reason": "No reviewer role."},
    ).status_code == 403
    assert client.post(
        "/api/claims/CLM-DEMO-UNKNOWN/adjudicate",
        headers={"Authorization": "Bearer " + token + "tampered"},
    ).status_code == 401


def test_supervisor_routed_claim_requires_supervisor_or_admin(tmp_path, monkeypatch):
    from services.api.claims_api import main as api_main
    from services.api.claims_api.repository import ClaimsRepository
    from services.application.claims import ClaimsService

    repository = ClaimsRepository(str(Path(tmp_path) / "claims.sqlite3"))
    service = ClaimsService(repository)
    claim = service.submit({
        "policy_number": "DIC-PC-0091273",
        "claimant_name": "Synthetic Supervisor Review",
        "loss_type": "collision",
        "requested_amount": 60000,
        "deductible": 1000,
        "coverage_limit": 500000,
        "depreciation_amount": 5000,
        "payment_token_valid": True,
        "risk_score": 85,
        "fraud_score": 75,
        "inconsistency_flag": False,
        "photo_count": 1,
        "currency": "INR",
        "evidence": [
            {"kind": "repair_estimate", "text": "Fictional garage estimate."},
            {"kind": "incident_report", "text": "Fictional incident report."},
        ],
    })
    assert claim["route_category"] == "supervisor_review"
    monkeypatch.setattr(api_main, "repository", repository)
    monkeypatch.setattr(api_main, "claims_service", service)
    client = TestClient(app)
    adjuster_token = client.post("/api/auth/login", json={"username": "adjuster.demo"}).json()["access_token"]
    supervisor_token = client.post("/api/auth/login", json={"username": "supervisor.demo"}).json()["access_token"]
    decision = {"action": "approve", "reviewer_id": "adjuster.demo", "reason": "Reviewed the synthetic high-risk case."}

    denied = client.post(f"/api/claims/{claim['claim_id']}/decision", headers={"Authorization": f"Bearer {adjuster_token}"}, json=decision)
    assert denied.status_code == 403

    decision["reviewer_id"] = "supervisor.demo"
    approved = client.post(f"/api/claims/{claim['claim_id']}/decision", headers={"Authorization": f"Bearer {supervisor_token}"}, json=decision)
    assert approved.status_code == 200
    assert approved.json()["payment"]["adapter"] == "synthetic_local"


def test_reviewer_cannot_write_audit_event_under_another_identity():
    client = TestClient(app)
    token = client.post("/api/auth/login", json={"username": "adjuster.demo"}).json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}
    response = client.post(
        "/api/claims/CLM-DEMO-UNKNOWN/decision",
        headers=headers,
        json={"action": "decline", "reviewer_id": "admin.demo", "reason": "Attempt identity spoof."},
    )
    assert response.status_code == 403
