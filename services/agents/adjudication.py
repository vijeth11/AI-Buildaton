from __future__ import annotations

from services.agents.intake import validate_claim

DEFAULT_RISK_THRESHOLD = 60
DEFAULT_FRAUD_THRESHOLD = 40
DEFAULT_AUTO_SETTLEMENT_AMOUNT_LIMIT = 50000
DEFAULT_SUPERVISOR_REVIEW_AMOUNT_LIMIT = 200000
DEFAULT_HIGH_RISK_SCORE_THRESHOLD = 80
DEFAULT_HIGH_FRAUD_SCORE_THRESHOLD = 70


def adjudicate(
    claim: dict,
    sources: list[dict],
    risk_threshold: float = DEFAULT_RISK_THRESHOLD,
    fraud_threshold: float = DEFAULT_FRAUD_THRESHOLD,
    auto_settlement_amount_limit: float = DEFAULT_AUTO_SETTLEMENT_AMOUNT_LIMIT,
    supervisor_review_amount_limit: float = DEFAULT_SUPERVISOR_REVIEW_AMOUNT_LIMIT,
    high_risk_score_threshold: float = DEFAULT_HIGH_RISK_SCORE_THRESHOLD,
    high_fraud_score_threshold: float = DEFAULT_HIGH_FRAUD_SCORE_THRESHOLD,
    agent_assessments: dict | None = None,
) -> dict:
    flags = validate_claim(claim, risk_threshold=risk_threshold)
    agent_assessments = agent_assessments or {}
    intake_assessment = agent_assessments.get("intake_agent", {})
    if intake_assessment.get("status") == "completed":
        if intake_assessment.get("missing_or_ambiguous_fields"):
            flags.append("llm_intake_missing_or_ambiguous_fields")
        if intake_assessment.get("inconsistencies"):
            flags.append("llm_intake_inconsistency_requires_review")
    fraud_assessment = agent_assessments.get("fraud_risk_agent", {})
    if fraud_assessment.get("status") == "completed" and (
        fraud_assessment.get("recommended_review")
        or fraud_assessment.get("risk_indicators")
        or fraud_assessment.get("fraud_indicators")
        or fraud_assessment.get("inconsistencies")
    ):
        flags.append("llm_fraud_risk_review_required")
    loss_type = claim.get("loss_type", "unknown")
    policy_source = next((source for source in sources if source.get("kind") == "policy"), None)
    excluded = bool(policy_source and loss_type in policy_source.get("excluded_loss_types", []))
    covered_loss_types = {
        covered_type
        for source in sources
        if source.get("kind") == "policy"
        for covered_type in source.get("covered_loss_types", [])
    }
    coverage_confirmed = loss_type in covered_loss_types
    if not excluded and not coverage_confirmed:
        flags.append("coverage_unconfirmed")
    coverage_assessment = agent_assessments.get("adjudication_agent", {})
    llm_coverage_disagreement = (
        coverage_assessment.get("status") == "completed"
        and coverage_assessment.get("advisory_recommendation") == "potentially_excluded"
        and coverage_confirmed
        and not excluded
    )
    if llm_coverage_disagreement or (
        coverage_assessment.get("status") == "completed"
        and coverage_assessment.get("unresolved_questions")
    ):
        flags.append("llm_coverage_ambiguity_requires_review")
    risk_score = claim.get("risk_score")
    fraud_score = claim.get("fraud_score")
    if risk_score is None:
        flags.append("risk_score_unavailable")
    if fraud_score is None:
        flags.append("fraud_score_unavailable")
    requested_amount = float(claim.get("requested_amount", 0))
    if requested_amount > auto_settlement_amount_limit:
        flags.append("amount_above_auto_settlement_limit")

    if excluded:
        recommendation = "decline"
        rationale = "The reported loss type is listed in the retrieved policy exclusion."
        flags.append("policy_exclusion_requires_review")
    elif flags:
        recommendation = "hold"
        rationale = "One or more validation or risk checks require human review."
    else:
        recommendation = "approve"
        rationale = "Structured claim facts satisfy the configured coverage and evidence checks."

    deductible = float(claim.get("deductible", 0))
    depreciation = float(claim.get("depreciation_amount", 0))
    limit = float(claim.get("coverage_limit", 0))
    gross_after_deductions = max(requested_amount - deductible - depreciation, 0)
    settlement_estimate = min(gross_after_deductions, limit)
    recommended_payout = settlement_estimate if coverage_confirmed and not excluded else 0
    risk_below_threshold = risk_score is not None and risk_score < risk_threshold
    fraud_below_threshold = fraud_score is not None and fraud_score < fraud_threshold
    payable_amount_valid = recommended_payout > 0 and recommended_payout <= limit
    confidence = (
        "High"
        if coverage_confirmed
        and not any(flag.startswith("missing_") or flag == "conflicting_claim_information" for flag in flags)
        else "Moderate"
    )
    auto_settlement_authorized = (
        recommendation == "approve"
        and not flags
        and risk_below_threshold
        and fraud_below_threshold
        and payable_amount_valid
    )
    checks = [
        {
            "check": "policy_coverage",
            "passed": coverage_confirmed and not excluded,
            "reason": "Loss type is covered by the retrieved policy." if coverage_confirmed and not excluded else "Coverage is excluded or could not be established.",
        },
        {
            "check": "evidence_sufficiency",
            "passed": not any(flag.startswith("missing_") for flag in flags),
            "reason": "Required evidence is present." if not any(flag.startswith("missing_") for flag in flags) else "Required evidence is missing.",
        },
        {
            "check": "payment_details",
            "passed": "payment_details_unverified" not in flags,
            "reason": "Synthetic payment details are valid." if "payment_details_unverified" not in flags else "Synthetic payment details are unverified.",
        },
        {
            "check": "risk_threshold",
            "score": risk_score,
            "threshold": risk_threshold,
            "passed": risk_below_threshold,
            "reason": "Risk score is below threshold." if risk_below_threshold else "Risk score is missing or at/above threshold.",
        },
        {
            "check": "fraud_threshold",
            "score": fraud_score,
            "threshold": fraud_threshold,
            "passed": fraud_below_threshold,
            "reason": "Fraud score is below threshold." if fraud_below_threshold else "Fraud score is missing or at/above threshold.",
        },
        {
            "check": "settlement_amount",
            "passed": payable_amount_valid,
            "deductible": deductible,
            "coverage_limit": limit,
            "calculated_amount": settlement_estimate,
            "reason": "Settlement estimate is within the policy limit." if payable_amount_valid else "No payable amount remains after deductible and limit checks.",
        },
        {
            "check": "auto_settlement_amount_limit",
            "passed": requested_amount <= auto_settlement_amount_limit,
            "claimed_amount": requested_amount,
            "threshold": auto_settlement_amount_limit,
            "reason": "Claim amount is within the automatic settlement limit." if requested_amount <= auto_settlement_amount_limit else "Claim amount exceeds the automatic settlement limit and requires human review.",
        },
        {
            "check": "supervisor_review_amount_limit",
            "passed": requested_amount <= supervisor_review_amount_limit,
            "claimed_amount": requested_amount,
            "threshold": supervisor_review_amount_limit,
            "reason": "Claim amount is within the supervisor escalation limit." if requested_amount <= supervisor_review_amount_limit else "Claim amount exceeds the supervisor escalation limit.",
        },
    ]
    return {
        "recommendation": recommendation,
        "status": "auto_settlement_ready" if auto_settlement_authorized else "human_review",
        "rationale": rationale,
        "review_flags": sorted(set(flags)),
        "estimated_settlement": settlement_estimate if auto_settlement_authorized else 0,
        "settlement_calculations": [
            {"label": "Garage estimate", "amount": requested_amount, "operation": "base"},
            {"label": "Compulsory deductible", "amount": deductible, "operation": "subtract"},
            {"label": "Depreciation", "amount": depreciation, "operation": "subtract"},
            {"label": "Recommended payout", "amount": recommended_payout, "operation": "result"},
        ],
        "policy_clauses": [
            clause
            for source in sources
            for clause in source.get("clauses", [])
        ],
        "evidence_checks": claim.get("evidence_checks", []),
        "agent_assessments": agent_assessments,
        "confidence": confidence,
        "requires_human_review": not auto_settlement_authorized,
        "automatic_payment_authorized": auto_settlement_authorized,
        "risk_score": risk_score,
        "risk_threshold": risk_threshold,
        "fraud_score": fraud_score,
        "fraud_threshold": fraud_threshold,
        "checks": checks,
        "citations": [
            {
                "source_id": source["source_id"],
                "kind": source["kind"],
                "snippet": source["text"][:280],
            }
            for source in sources
        ],
    }
