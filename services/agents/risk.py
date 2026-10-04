from __future__ import annotations


def calculate_risk_scores(claim: dict) -> dict:
    """Calculate demo scores from structured claim facts, never from UI score fields."""
    if claim.get("risk_score") is not None and claim.get("fraud_score") is not None:
        return {
            "risk_score": float(claim["risk_score"]),
            "fraud_score": float(claim["fraud_score"]),
            "score_origin": "synthetic_fixture",
        }

    amount = float(claim.get("requested_amount", 0))
    photo_count = int(claim.get("photo_count", 0))
    risk_score = 8 + (25 if amount > 50_000 else 0) + (12 if photo_count == 0 else 0)
    fraud_score = 5 + (28 if amount > 50_000 else 0)
    if claim.get("inconsistency_flag", False):
        fraud_score += 30
    return {
        "risk_score": float(min(risk_score, 100)),
        "fraud_score": float(min(fraud_score, 100)),
        "score_origin": "deterministic_demo_rules",
    }