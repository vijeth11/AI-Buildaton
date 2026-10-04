from __future__ import annotations


def validate_claim(claim: dict, risk_threshold: float = 60) -> list[str]:
    """Return review flags from structured facts; evidence text is never executed."""
    flags: list[str] = []
    evidence_types = {item.get("kind") for item in claim.get("evidence", [])}

    if claim.get("loss_type") == "collision" and "repair_estimate" not in evidence_types:
        flags.append("missing_repair_estimate")
    if claim.get("requested_amount", 0) >= 5000 and "incident_report" not in evidence_types:
        flags.append("missing_incident_report")
    if not claim.get("payment_token_valid", False):
        flags.append("payment_details_unverified")
    if claim.get("inconsistency_flag", False):
        flags.append("conflicting_claim_information")
    if claim.get("photo_count") == 0:
        flags.append("missing_vehicle_photos")
    if claim.get("document_review_flags"):
        flags.append("supporting_document_extraction_requires_review")
    if claim.get("risk_score") is not None and claim.get("risk_score", 0) >= risk_threshold:
        flags.append("elevated_risk")

    return flags
