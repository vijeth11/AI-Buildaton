from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
import secrets
import time


DEMO_IDENTITIES = {
    "claims.agent": "claims_agent",
    "adjuster.demo": "adjuster",
    "supervisor.demo": "supervisor",
    "admin.demo": "admin",
}

_secret_value = os.getenv("AUTH_SIGNING_SECRET", "").strip()
if not _secret_value and os.getenv("APP_ENV", "local") != "local":
    raise RuntimeError("AUTH_SIGNING_SECRET must be supplied through the approved production secret store")
_SIGNING_SECRET = _secret_value.encode("utf-8") if _secret_value else secrets.token_bytes(32)
TOKEN_LIFETIME_SECONDS = int(os.getenv("AUTH_TOKEN_LIFETIME_SECONDS", "14400"))


def issue_demo_token(username: str) -> dict:
    role = DEMO_IDENTITIES.get(username)
    if role is None:
        raise ValueError("Unknown development identity")
    now = int(time.time())
    payload = {"sub": username, "role": role, "iat": now, "exp": now + TOKEN_LIFETIME_SECONDS}
    encoded = base64.urlsafe_b64encode(json.dumps(payload, separators=(",", ":")).encode()).decode().rstrip("=")
    signature = hmac.new(_SIGNING_SECRET, encoded.encode(), hashlib.sha256).hexdigest()
    return {"access_token": f"{encoded}.{signature}", "token_type": "bearer", "expires_in": TOKEN_LIFETIME_SECONDS, "username": username, "role": role}


def verify_demo_token(token: str) -> dict | None:
    try:
        encoded, supplied_signature = token.split(".", 1)
        expected_signature = hmac.new(_SIGNING_SECRET, encoded.encode(), hashlib.sha256).hexdigest()
        if not hmac.compare_digest(expected_signature, supplied_signature):
            return None
        padded = encoded + "=" * (-len(encoded) % 4)
        payload = json.loads(base64.urlsafe_b64decode(padded))
        if int(payload.get("exp", 0)) <= int(time.time()):
            return None
        if DEMO_IDENTITIES.get(payload.get("sub")) != payload.get("role"):
            return None
        return payload
    except (ValueError, TypeError, json.JSONDecodeError):
        return None
