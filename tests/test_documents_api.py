from __future__ import annotations

from io import BytesIO
from pathlib import Path

from fastapi.testclient import TestClient
from reportlab.pdfgen import canvas

from services.api.claims_api import main as claims_api
from services.api.claims_api.attachments import ClaimPhotoStorage
from services.api.claims_api.documents import ClaimDocumentStorage
from services.api.claims_api.repository import ClaimsRepository
from services.application.claims import ClaimsService


def _synthetic_pdf() -> bytes:
    buffer = BytesIO()
    document = canvas.Canvas(buffer)
    document.drawString(48, 740, "Fictional Garage Repair Estimate")
    document.drawString(48, 720, "Repair estimate INR 12,500 for synthetic claim.")
    document.drawString(48, 700, "Incident date 2026-08-14 PIN 400051")
    document.save()
    return buffer.getvalue()


def _draft_payload() -> dict:
    return {
        "policy_number": "DIC-PC-0091273",
        "loss_type": "collision",
        "loss_description": "Synthetic collision for document extraction test.",
        "incident_date": "2026-08-14",
        "incident_pincode": "400051",
        "incident_location": "Andheri West, Mumbai",
        "garage_estimate": 12500,
        "fictional": True,
    }


def test_pdf_document_is_stored_extracted_classified_and_retrievable(tmp_path, monkeypatch):
    repository = ClaimsRepository(str(tmp_path / "claims.sqlite3"))
    storage = ClaimDocumentStorage(str(tmp_path / "documents"))
    service = ClaimsService(repository, photo_storage=ClaimPhotoStorage(str(tmp_path / "photos")), document_storage=storage)
    monkeypatch.setattr(claims_api, "repository", repository)
    monkeypatch.setattr(claims_api, "claims_service", service)
    client = TestClient(claims_api.app)
    token = client.post("/api/auth/login", json={"username": "adjuster.demo"}).json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}

    draft = client.post("/api/claims/drafts", headers=headers, json=_draft_payload()).json()
    upload = client.post(
        f"/api/claims/{draft['claim_id']}/documents",
        headers=headers,
        files=[("files", ("garage-estimate.pdf", _synthetic_pdf(), "application/pdf"))],
    )
    assert upload.status_code == 201
    document = upload.json()[0]
    assert document["document_type"] == "repair_estimate"
    assert document["extraction_status"] == "extracted"
    assert "amount_candidate_inr" in document["extracted_fields"]
    assert "storage_path" not in document

    listing = client.get(f"/api/claims/{draft['claim_id']}/documents", headers=headers)
    assert listing.status_code == 200
    assert listing.json()[0]["file_name"] == "garage-estimate.pdf"
    download = client.get(f"/api/claims/{draft['claim_id']}/documents/{document['document_id']}/file", headers=headers)
    assert download.status_code == 200
    assert download.content.startswith(b"%PDF-")


def test_image_document_without_local_ocr_is_marked_for_human_review(tmp_path):
    from starlette.datastructures import UploadFile

    storage = ClaimDocumentStorage(str(tmp_path / "documents"))
    image = UploadFile(filename="invoice.png", file=BytesIO(b"\x89PNG\r\n\x1a\nsynthetic-image"), headers={"content-type": "image/png"})
    import asyncio

    document = asyncio.run(storage.store(image, "CLM-DEMO-DOCUMENT"))
    assert document["extraction_status"].startswith("ocr_")
    assert document["extracted_text"] == ""
