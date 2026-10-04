from __future__ import annotations

import asyncio

import httpx
from fastapi.testclient import TestClient

from services.api.claims_api.main import app
from services.mcp_server import server as mcp_module


def test_mcp_http_client_logs_in_and_calls_local_api(monkeypatch):
    original_async_client = httpx.AsyncClient

    class InProcessApiClient(original_async_client):
        def __init__(self, *args, **kwargs):
            kwargs["transport"] = httpx.ASGITransport(app=app)
            super().__init__(*args, **kwargs)

    client = TestClient(app)
    client.__enter__()
    monkeypatch.setattr(mcp_module, "API_BASE_URL", "http://claims-api.test")
    monkeypatch.setattr(mcp_module.httpx, "AsyncClient", InProcessApiClient)
    monkeypatch.setattr(mcp_module, "_access_token", None)

    try:
        result = asyncio.run(mcp_module._request("GET", "/api/policies/DIC-PC-0091273"))
        assert result["policy_number"] == "DIC-PC-0091273"
        assert result["vehicle_model"] == "i20"
        assert mcp_module._access_token
    finally:
        client.__exit__(None, None, None)


def test_mcp_exposes_local_tools_and_named_external_todos():
    tools = asyncio.run(mcp_module.server.list_tools())
    names = {tool.name for tool in tools}

    assert {"lookup_policy", "get_claim_history", "upload_claim_photo", "get_policy_rag_health", "get_synthetic_repair_estimate"} <= names
    assert {"verify_weather_third_party", "geocode_pincode_third_party", "verify_bank_details_third_party", "razorpay_payout_third_party"} <= names
