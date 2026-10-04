from __future__ import annotations

import json
import os
import re
import shutil
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

from fastapi import HTTPException, UploadFile
from pypdf import PdfReader

MAX_DOCUMENT_BYTES = 10 * 1024 * 1024
ALLOWED_DOCUMENT_TYPES = {
    "application/pdf": ".pdf",
    "image/jpeg": ".jpg",
    "image/png": ".png",
    "image/webp": ".webp",
}


class ClaimDocumentStorage:
    def __init__(self, root: str | None = None):
        self.root = Path(root or os.getenv("CLAIM_DOCUMENT_DIR", ".local/claim-documents"))
        self.root.mkdir(parents=True, exist_ok=True)

    async def store(self, upload: UploadFile, claim_id: str) -> dict:
        content_type = upload.content_type or ""
        extension = ALLOWED_DOCUMENT_TYPES.get(content_type)
        if extension is None:
            raise HTTPException(status_code=415, detail="Only PDF, JPEG, PNG, or WebP documents are supported")
        content = await upload.read(MAX_DOCUMENT_BYTES + 1)
        if not content or len(content) > MAX_DOCUMENT_BYTES:
            raise HTTPException(status_code=413, detail="Each supporting document must be between 1 byte and 10 MB")
        if not self._matches_signature(content_type, content):
            raise HTTPException(status_code=415, detail="Uploaded file does not match its declared document type")

        document_id = f"DOC-{uuid4().hex[:12].upper()}"
        target = self.root / f"{document_id}{extension}"
        target.write_bytes(content)
        text, extraction_status = self._extract_text(target, content_type)
        safe_name = Path(upload.filename or f"claim-document{extension}").name[:180]
        document_type = self._classify(safe_name, text)
        return {
            "document_id": document_id,
            "claim_id": claim_id,
            "file_name": safe_name,
            "content_type": content_type,
            "size_bytes": len(content),
            "storage_path": str(target.resolve()),
            "created_at": datetime.now(timezone.utc).isoformat(),
            "extraction_status": extraction_status,
            "document_type": document_type,
            "extracted_text": text[:20000],
            "extracted_fields": self._extract_fields(text),
        }

    @staticmethod
    def _matches_signature(content_type: str, content: bytes) -> bool:
        signatures = {
            "application/pdf": content.startswith(b"%PDF-"),
            "image/jpeg": content.startswith(b"\xff\xd8\xff"),
            "image/png": content.startswith(b"\x89PNG\r\n\x1a\n"),
            "image/webp": len(content) >= 12 and content.startswith(b"RIFF") and content[8:12] == b"WEBP",
        }
        return signatures.get(content_type, False)

    @classmethod
    def _extract_text(cls, path: Path, content_type: str) -> tuple[str, str]:
        if content_type == "application/pdf":
            text = "\n".join(page.extract_text() or "" for page in PdfReader(str(path)).pages).strip()
            if text:
                return text, "extracted"
            return cls._ocr_image(path)
        return cls._ocr_image(path)

    @staticmethod
    def _ocr_image(path: Path) -> tuple[str, str]:
        if shutil.which(os.getenv("TESSERACT_CMD", "tesseract")) is None:
            return "", "ocr_unavailable_requires_review"
        try:
            import pytesseract
            from PIL import Image

            configured_command = os.getenv("TESSERACT_CMD")
            if configured_command:
                pytesseract.pytesseract.tesseract_cmd = configured_command
            text = pytesseract.image_to_string(Image.open(path)).strip()
            return (text, "extracted") if text else ("", "ocr_empty_requires_review")
        except Exception as error:
            return "", f"ocr_error_{type(error).__name__}_requires_review"

    @staticmethod
    def _classify(file_name: str, text: str) -> str:
        content = f"{file_name} {text}".lower()
        if any(term in content for term in ("garage estimate", "repair estimate", "invoice", "repair bill")):
            return "repair_estimate"
        if any(term in content for term in ("registration certificate", "vehicle registration", "rc book")):
            return "vehicle_registration"
        if any(term in content for term in ("accident report", "incident report", "fir", "police report")):
            return "incident_report"
        if any(term in content for term in ("policy schedule", "policy number", "insurance policy")):
            return "policy_document"
        return "supporting_document"

    @staticmethod
    def _extract_fields(text: str) -> dict:
        fields: dict[str, object] = {}
        pin = re.search(r"\b([1-9][0-9]{5})\b", text)
        if pin:
            fields["pincode_candidate"] = pin.group(1)
        date_match = re.search(r"\b(20[0-9]{2}-[01][0-9]-[0-3][0-9]|[0-3][0-9][-/][01][0-9][-/]20[0-9]{2})\b", text)
        if date_match:
            fields["incident_date_candidate"] = date_match.group(1)
        amount = re.search(r"(?i)(?:INR|Rs\.?|₹)\s*([0-9][0-9,]*(?:\.[0-9]{1,2})?)", text)
        if amount:
            fields["amount_candidate_inr"] = float(amount.group(1).replace(",", ""))
        return fields
