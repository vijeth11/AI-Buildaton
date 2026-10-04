from __future__ import annotations

from fastapi import HTTPException


def third_party_todo(provider: str, purpose: str) -> None:
    """Explicit integration boundary: never fabricate third-party verification."""
    raise HTTPException(
        status_code=501,
        detail=f"TODO: integrate an approved {provider} service for {purpose}; no external request was made.",
    )
