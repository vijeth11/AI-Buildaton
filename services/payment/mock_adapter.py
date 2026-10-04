from __future__ import annotations

from datetime import datetime, timezone
from uuid import uuid4


def create_mock_payment(claim_id: str, amount: float, currency: str = "INR") -> dict:
    """Create a local synthetic payment record; this adapter performs no network I/O."""
    return {
        "payment_id": f"PAY-DEMO-{uuid4().hex[:12].upper()}",
        "claim_id": claim_id,
        "amount": round(amount, 2),
        "currency": currency,
        "status": "succeeded",
        "created_at": datetime.now(timezone.utc).isoformat(),
        "adapter": "synthetic_local",
    }
