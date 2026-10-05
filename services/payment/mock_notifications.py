from __future__ import annotations

from datetime import datetime, timezone


def dispatch_mock_notifications(claim_id: str, event_type: str, payload: dict) -> dict:
    """Create a synthetic notification delivery record without external network calls."""
    template = "claim_update"
    if event_type == "payout_succeeded":
        template = "payout_confirmation"
    elif event_type == "claim_declined":
        template = "decline_notice"

    return {
        "provider": "synthetic_local_notifications",
        "claim_id": claim_id,
        "event_type": event_type,
        "template": template,
        "channels": [
            {
                "channel": "email",
                "recipient": "demo-claimant@example.invalid",
                "status": "sent",
            },
            {
                "channel": "sms",
                "recipient": "+910000000000",
                "status": "sent",
            },
        ],
        "payload": payload,
        "fictional": True,
        "sent_at": datetime.now(timezone.utc).isoformat(),
    }
