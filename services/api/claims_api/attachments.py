from __future__ import annotations

import os
from pathlib import Path
from uuid import uuid4

from fastapi import HTTPException, UploadFile


MAX_PHOTO_BYTES = 5 * 1024 * 1024
ALLOWED_IMAGE_TYPES = {"image/jpeg": ".jpg", "image/png": ".png", "image/webp": ".webp"}


class ClaimPhotoStorage:
    def __init__(self, root: str | None = None):
        self.root = Path(root or os.getenv("CLAIM_PHOTO_DIR", ".local/claim-photos"))
        self.root.mkdir(parents=True, exist_ok=True)

    async def store(self, upload: UploadFile, claim_id: str) -> dict:
        content_type = upload.content_type or ""
        extension = ALLOWED_IMAGE_TYPES.get(content_type)
        if not extension:
            raise HTTPException(status_code=415, detail="Only JPEG, PNG, or WebP claim photos are supported")
        content = await upload.read(MAX_PHOTO_BYTES + 1)
        if not content or len(content) > MAX_PHOTO_BYTES:
            raise HTTPException(status_code=413, detail="Each photo must be between 1 byte and 5 MB")
        if not self._matches_signature(content_type, content):
            raise HTTPException(status_code=415, detail="Uploaded file does not match its image type")
        photo_id = f"PHOTO-{uuid4().hex[:12].upper()}"
        target = self.root / f"{photo_id}{extension}"
        target.write_bytes(content)
        return {
            "photo_id": photo_id,
            "claim_id": claim_id,
            "file_name": Path(upload.filename or f"claim-photo{extension}").name[:180],
            "content_type": content_type,
            "size_bytes": len(content),
            "storage_path": str(target.resolve()),
        }

    @staticmethod
    def _matches_signature(content_type: str, content: bytes) -> bool:
        if content_type == "image/jpeg":
            return content.startswith(b"\xff\xd8\xff")
        if content_type == "image/png":
            return content.startswith(b"\x89PNG\r\n\x1a\n")
        if content_type == "image/webp":
            return len(content) >= 12 and content.startswith(b"RIFF") and content[8:12] == b"WEBP"
        return False
