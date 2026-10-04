from __future__ import annotations

from fastapi.testclient import TestClient

from services.api.claims_api.main import app


def test_synthetic_repair_estimate_api_is_local_and_deterministic():
    client = TestClient(app)
    token = client.post("/api/auth/login", json={"username": "adjuster.demo"}).json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}
    payload = {
        "vehicle_make": "Hyundai",
        "vehicle_model": "i20",
        "damage_type": "engine_water_ingress",
        "severity": "high",
        "fictional": True,
    }
    first = client.post("/api/integrations/repair-estimate", headers=headers, json=payload)
    second = client.post("/api/integrations/repair-estimate", headers=headers, json=payload)

    assert first.status_code == 200
    assert first.json()["provider"] == "synthetic_repair_estimate_mock"
    assert first.json()["amount"] == 180000
    assert second.json()["estimate_id"] == first.json()["estimate_id"]


def test_external_provider_routes_are_explicitly_unimplemented():
    client = TestClient(app)
    token = client.post("/api/auth/login", json={"username": "admin.demo"}).json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}
    responses = [
        client.get("/api/integrations/weather", headers=headers, params={"incident_date": "2026-08-14", "pincode": "400051"}),
        client.get("/api/integrations/geocode/pincode/400051", headers=headers),
        client.post("/api/integrations/bank/verify", headers=headers, json={"synthetic_payout_profile": "DEMO-PAYOUT-1", "fictional": True}),
        client.post("/api/integrations/razorpay/payout", headers=headers, json={
            "claim_id": "CLM-DEMO-0000000001",
            "amount": 1000,
            "currency": "INR",
            "idempotency_key": "demo-payout-0001",
        }),
    ]

    assert [response.status_code for response in responses] == [501, 501, 501, 501]
    assert all("TODO" in response.json()["detail"] for response in responses)
