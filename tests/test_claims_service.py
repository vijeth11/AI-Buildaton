from __future__ import annotations

import asyncio
from io import BytesIO
from pathlib import Path
from tempfile import TemporaryDirectory

from fastapi import UploadFile

from services.api.claims_api.attachments import ClaimPhotoStorage
from services.api.claims_api.repository import ClaimsRepository
from services.api.claims_api.schemas import ClaimSubmission
from services.application.claims import ClaimsService


def sample_claim(**overrides):
    claim = {
        "policy_number": "POL-AUTO-100",
        "claimant_name": "Fictional Demo Claimant",
        "loss_type": "collision",
        "requested_amount": 2400,
        "deductible": 500,
        "coverage_limit": 10000,
        "payment_token_valid": True,
        "risk_score": 5,
        "fraud_score": 4,
        "inconsistency_flag": False,
        "evidence": [
            {"kind": "repair_estimate", "text": "Fictional repair estimate"},
            {"kind": "incident_report", "text": "Fictional incident report"},
        ],
        "fictional": True,
    }
    claim.update(overrides)
    return claim


def build_service(database_path: Path) -> ClaimsService:
    return ClaimsService(ClaimsRepository(str(database_path)))


def test_eligible_low_score_claim_is_paid_and_audited():
    with TemporaryDirectory() as directory:
        service = build_service(Path(directory) / "claims.sqlite3")
        claim = service.submit(sample_claim())

        assert claim["status"] == "paid"
        assert claim["payment"]["status"] == "succeeded"
        assert claim["payment"]["amount"] == 1900
        assert claim["payment"]["adapter"] == "synthetic_local"
        assert claim["adjudication"]["checks"]
        assert any(event["event_type"] == "payment_succeeded" for event in claim["audit_events"])


def test_re_adjudicating_paid_claim_preserves_payment_record():
    with TemporaryDirectory() as directory:
        service = build_service(Path(directory) / "claims.sqlite3")
        paid = service.submit(sample_claim())
        payment_id = paid["payment"]["payment_id"]

        refreshed = service.adjudicate(paid["claim_id"])

        assert refreshed["status"] == "paid"
        assert refreshed["route_category"] == "fast_tracked"
        assert refreshed["payment"]["payment_id"] == payment_id


def test_langgraph_failure_fails_closed_and_records_audit_event():
    with TemporaryDirectory() as directory:
        service = build_service(Path(directory) / "claims.sqlite3")
        service.workflow.invoke = lambda state: (_ for _ in ()).throw(RuntimeError("synthetic vector-store outage"))
        claim = service.submit(sample_claim())

        assert claim["status"] == "human_review"
        assert claim["adjudication"]["automatic_payment_authorized"] is False
        assert claim["payment"] is None
        assert claim["agent_steps"][-1]["status"] == "error"
        failure = next(event for event in claim["audit_events"] if event["event_type"] == "adjudication_failed")
        assert failure["details"]["error_type"] == "RuntimeError"
        assert "synthetic vector-store outage" not in str(claim["audit_events"])


def test_high_risk_and_fraud_route_to_supervisor_review():
    with TemporaryDirectory() as directory:
        service = build_service(Path(directory) / "claims.sqlite3")
        claim = service.submit(sample_claim(risk_score=85, fraud_score=75))

        assert claim["status"] == "human_review"
        assert claim["route_category"] == "supervisor_review"
        assert claim["payment"] is None


def test_reviewer_modification_updates_estimate_and_reruns_rules():
    with TemporaryDirectory() as directory:
        service = build_service(Path(directory) / "claims.sqlite3")
        claim = service.submit(sample_claim(requested_amount=60000, risk_score=5, fraud_score=5))
        assert claim["status"] == "human_review"

        modified = service.record_decision(
            claim["claim_id"],
            "modify",
            "reviewer-demo",
            "Garage sent a corrected synthetic estimate.",
            modified_amount=30000,
        )

        assert modified["status"] == "paid"
        assert modified["requested_amount"] == 30000
        assert modified["payment"]["amount"] > 0
        assert any(event["event_type"] == "claim_modified" for event in modified["audit_events"])


def test_request_info_accepts_additional_evidence_and_reruns_workflow():
    with TemporaryDirectory() as directory:
        service = build_service(Path(directory) / "claims.sqlite3")
        claim = service.submit(sample_claim(evidence=[]))
        requested = service.record_decision(
            claim["claim_id"], "request_evidence", "reviewer-demo", "Please provide a repair estimate."
        )
        assert requested["status"] == "awaiting_evidence"

        updated = service.add_evidence(
            claim["claim_id"], "repair_estimate", "Fictional revised garage estimate 2400 INR.", "claimant.demo"
        )

        assert updated["status"] == "paid"
        assert any(item["kind"] == "repair_estimate" for item in updated["evidence"])
        assert any(event["event_type"] == "additional_evidence_received" for event in updated["audit_events"])


def test_high_fraud_score_enters_review_with_full_decision_trace():
    with TemporaryDirectory() as directory:
        service = build_service(Path(directory) / "claims.sqlite3")
        claim = service.submit(sample_claim(fraud_score=40))

        assert claim["status"] == "human_review"
        assert claim["payment"] is None
        assert claim["adjudication"]["fraud_threshold"] == 40
        assert claim["adjudication"]["requires_human_review"] is True
        assert any(event["event_type"] == "adjudication_completed" for event in claim["audit_events"])


def test_reviewer_approval_of_flagged_claim_records_action_and_payment():
    with TemporaryDirectory() as directory:
        service = build_service(Path(directory) / "claims.sqlite3")
        claim = service.submit(sample_claim(risk_score=60))
        decided = service.record_decision(
            claim["claim_id"], "approve", "reviewer-demo", "Reviewed synthetic evidence and approved."
        )

        assert decided["status"] == "paid"
        assert decided["payment"]["status"] == "succeeded"
        assert any(event["event_type"] == "reviewer_decision" for event in decided["audit_events"])


def test_zero_payable_amount_is_not_auto_settled():
    with TemporaryDirectory() as directory:
        service = build_service(Path(directory) / "claims.sqlite3")
        claim = service.submit(sample_claim(requested_amount=200, deductible=500))

        assert claim["status"] == "human_review"
        assert claim["payment"] is None


def test_wireframe_intake_policy_photo_and_review_fields_are_persisted():
    with TemporaryDirectory() as directory:
        root = Path(directory)
        repository = ClaimsRepository(str(root / "claims.sqlite3"))
        service = ClaimsService(repository, photo_storage=ClaimPhotoStorage(str(root / "photos")))
        policy = service.policy_summary("DIC-PC-0091273")
        assert policy["vehicle_model"] == "i20"
        assert policy["coverage_summary"] == "Comprehensive cover with Engine Protector"

        submission = ClaimSubmission(
            policy_number="DIC-PC-0091273",
            loss_type="flood",
            loss_description="Car stalled in synthetic flood water; engine will not start.",
            incident_date="2026-08-14",
            incident_pincode="400051",
            incident_location="Andheri West, Mumbai",
            garage_estimate=140000,
            fictional=True,
        )
        draft = service.create_draft(submission.to_claim_data())
        assert draft["vehicle_registration"] == "MH01 AB 1234"
        assert draft["status"] == "draft"

        photo_upload = UploadFile(
            filename="front-view.png",
            file=BytesIO(b"\x89PNG\r\n\x1a\nsynthetic-demo-image"),
            headers={"content-type": "image/png"},
        )
        asyncio.run(service.add_photo(draft["claim_id"], photo_upload))
        claim = service.submit_draft(draft["claim_id"])

        assert claim["incident_date"] == "2026-08-14"
        assert claim["incident_pincode"] == "400051"
        assert claim["incident_location"] == "Andheri West, Mumbai"
        assert claim["requested_amount"] == 140000
        assert claim["status"] == "human_review"
        assert claim["photos"][0]["file_name"] == "front-view.png"
        assert claim["adjudication"]["settlement_calculations"][-1]["amount"] == 112400
        assert claim["adjudication"]["policy_clauses"]
        assert claim["adjudication"]["evidence_checks"]
        assert {step["agent"] for step in claim["agent_steps"]} >= {
            "intake_agent_llm",
            "fraud_risk_agent_llm",
            "adjudication_agent_llm",
            "deterministic_rules_engine",
            "langgraph_settlement_router",
        }
        assert {value["status"] for value in claim["adjudication"]["agent_assessments"].values()} == {"unavailable"}
        stored_photo = repository.get_photo(claim["claim_id"], claim["photos"][0]["photo_id"])
        assert Path(stored_photo["storage_path"]).is_file()


def test_public_intake_schema_does_not_accept_user_supplied_scores():
    try:
        ClaimSubmission(
            policy_number="DIC-PC-0091273",
            loss_type="collision",
            loss_description="Synthetic collision facts for validation.",
            incident_date="2026-08-14",
            incident_pincode="400051",
            incident_location="Andheri West, Mumbai",
            garage_estimate=20000,
            risk_score=0,
            fraud_score=0,
        )
    except Exception as error:
        assert "risk_score" in str(error)
    else:
        raise AssertionError("Claim intake must reject user-supplied risk and fraud scores")
