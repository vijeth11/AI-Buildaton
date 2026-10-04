from __future__ import annotations

from fastapi.testclient import TestClient

from services.api.claims_api import main as claims_api
from services.api.claims_api.attachments import ClaimPhotoStorage
from services.api.claims_api.repository import ClaimsRepository
from services.application.claims import ClaimsService


def test_wireframe_claim_creation_upload_retrieval_and_review_payload(tmp_path, monkeypatch):
    repository = ClaimsRepository(str(tmp_path / "claims.sqlite3"))
    photo_storage = ClaimPhotoStorage(str(tmp_path / "photos"))
    service = ClaimsService(repository, photo_storage=photo_storage)
    monkeypatch.setattr(claims_api, "repository", repository)
    monkeypatch.setattr(claims_api, "claims_service", service)
    client = TestClient(claims_api.app)
    token = client.post("/api/auth/login", json={"username": "adjuster.demo"}).json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}

    policy_response = client.get("/api/policies/DIC-PC-0091273", headers=headers)
    assert policy_response.status_code == 200
    assert policy_response.json()["coverage_summary"] == "Comprehensive cover with Engine Protector"

    draft_response = client.post("/api/claims/drafts", headers=headers, json={
        "policy_number": "DIC-PC-0091273",
        "loss_type": "flood",
        "loss_description": "Car stalled in synthetic flood water. Engine will not start.",
        "incident_date": "2026-08-14",
        "incident_pincode": "400051",
        "incident_location": "Andheri West, Mumbai",
        "garage_estimate": 140000,
        "fictional": True,
    })
    assert draft_response.status_code == 201
    claim_id = draft_response.json()["claim_id"]

    image = b"\x89PNG\r\n\x1a\nsynthetic-demo-image"
    upload_response = client.post(
        f"/api/claims/{claim_id}/photos",
        headers=headers,
        files=[("files", ("vehicle-front.png", image, "image/png"))],
    )
    assert upload_response.status_code == 201

    submit_response = client.post(f"/api/claims/{claim_id}/submit", headers=headers)
    assert submit_response.status_code == 200
    assert submit_response.json()["status"] == "human_review"
    assert submit_response.json()["adjudication"]["settlement_calculations"][-1]["amount"] == 112400
    assert submit_response.json()["adjudication"]["confidence"] == "High"
    assert "amount_above_auto_settlement_limit" in submit_response.json()["adjudication"]["review_flags"]

    detail_response = client.get(f"/api/claims/{claim_id}", headers=headers)
    detail = detail_response.json()
    assert detail["incident_pincode"] == "400051"
    assert detail["vehicle_registration"] == "MH01 AB 1234"
    assert detail["photos"][0]["file_name"] == "vehicle-front.png"
    assert detail["adjudication"]["policy_clauses"]
    assert detail["adjudication"]["evidence_checks"]
    assert detail["agent_steps"]

    photo_id = detail["photos"][0]["photo_id"]
    photo_response = client.get(f"/api/claims/{claim_id}/photos/{photo_id}", headers=headers)
    assert photo_response.status_code == 200
    assert photo_response.content == image

    metrics_response = client.get("/api/metrics?period=today", headers=headers)
    assert metrics_response.status_code == 200
    assert metrics_response.json()["claim_runs"] == 1
    assert metrics_response.json()["agent_performance"]