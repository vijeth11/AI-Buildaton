from __future__ import annotations

from datetime import date

from fastapi.testclient import TestClient

import services.api.claims_api.main as claims_main
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


def test_weather_verification_uses_open_meteo_parameters(monkeypatch):
    captured = {}

    def fake_forecast(latitude: float, longitude: float, start_date: date, end_date: date):
        captured["latitude"] = latitude
        captured["longitude"] = longitude
        captured["start_date"] = start_date.isoformat()
        captured["end_date"] = end_date.isoformat()
        return {
            "latitude": latitude,
            "longitude": longitude,
            "hourly": {"temperature_2m": [21.1, 21.4]},
            "hourly_units": {"temperature_2m": "C"},
        }

    monkeypatch.setattr(claims_main, "fetch_open_meteo_forecast", fake_forecast)

    client = TestClient(app)
    token = client.post("/api/auth/login", json={"username": "admin.demo"}).json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}
    response = client.get(
        "/api/integrations/weather",
        headers=headers,
        params={
            "latitude": 52.52,
            "longitude": 13.41,
            "start_date": "2026-09-23",
            "end_date": "2026-09-30",
        },
    )

    assert response.status_code == 200
    body = response.json()
    assert body["provider"] == "open-meteo"
    assert body["query"] == {
        "latitude": 52.52,
        "longitude": 13.41,
        "start_date": "2026-09-23",
        "end_date": "2026-09-30",
        "hourly": "temperature_2m",
    }
    assert captured == {
        "latitude": 52.52,
        "longitude": 13.41,
        "start_date": "2026-09-23",
        "end_date": "2026-09-30",
    }


def test_geocode_uses_zipcodebase_api_key_and_codes(monkeypatch):
    captured = {}

    def fake_geocode(pincode: str):
        captured["codes"] = pincode
        return {
            "results": {pincode: [{"latitude": 19.12, "longitude": 72.85}]},
        }

    monkeypatch.setattr(claims_main, "fetch_zipcodebase_geocode", fake_geocode)

    client = TestClient(app)
    token = client.post("/api/auth/login", json={"username": "admin.demo"}).json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}
    response = client.get("/api/integrations/geocode/pincode/400051", headers=headers)

    assert response.status_code == 200
    body = response.json()
    assert body["provider"] == "zipcodebase"
    assert body["query"] == {"codes": "400051"}
    assert captured == {"codes": "400051"}


def test_bank_verification_uses_ifsc_code(monkeypatch):
    captured = {}

    def fake_ifsc_lookup(ifsc_code: str):
        captured["ifsc_code"] = ifsc_code
        return {
            "IFSC": ifsc_code,
            "BANK": "Delhi Nagrik Sehkari Bank",
            "BRANCH": "Delhi Nagrik Sehkari Bank IMPS",
            "CITY": "MUMBAI",
            "STATE": "MAHARASHTRA",
            "IMPS": True,
            "UPI": True,
        }

    monkeypatch.setattr(claims_main, "fetch_razorpay_ifsc", fake_ifsc_lookup)

    client = TestClient(app)
    token = client.post("/api/auth/login", json={"username": "admin.demo"}).json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}
    response = client.post(
        "/api/integrations/bank/verify",
        headers=headers,
        json={"ifsc_code": "yesb0dnb002", "fictional": True},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["provider"] == "razorpay_ifsc"
    assert body["query"] == {"ifsc_code": "YESB0DNB002"}
    assert body["verification"]["IFSC"] == "YESB0DNB002"
    assert captured == {"ifsc_code": "YESB0DNB002"}


def test_razorpay_payout_returns_simulated_success():
    client = TestClient(app)
    token = client.post("/api/auth/login", json={"username": "admin.demo"}).json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}
    response = client.post("/api/integrations/razorpay/payout", headers=headers, json={
        "bankaccount": "123456789012",
        "amount": 1000,
        "currency": "INR",
        "fictional": True,
    })

    assert response.status_code == 200
    body = response.json()
    assert body["provider"] == "razorpay_simulated"
    assert body["status"] == "success"
    assert body["bankaccount"] == "123456789012"
    assert body["amount"] == 1000
    assert body["currency"] == "INR"
    assert body["payout_id"].startswith("RPAY-DEMO-")
