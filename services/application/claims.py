from __future__ import annotations

import os
from datetime import datetime, timezone
from time import perf_counter
from uuid import uuid4

from services.agents.adjudication import (
    DEFAULT_AUTO_SETTLEMENT_AMOUNT_LIMIT,
    DEFAULT_FRAUD_THRESHOLD,
    DEFAULT_HIGH_FRAUD_SCORE_THRESHOLD,
    DEFAULT_HIGH_RISK_SCORE_THRESHOLD,
    DEFAULT_RISK_THRESHOLD,
    DEFAULT_SUPERVISOR_REVIEW_AMOUNT_LIMIT,
)
from services.api.claims_api.attachments import ClaimPhotoStorage
from services.api.claims_api.documents import ClaimDocumentStorage
from services.api.claims_api.policies import PolicyRepository
from services.api.claims_api.repository import ClaimsRepository
from services.application.orchestration import build_claim_workflow
from services.payment.mock_adapter import create_mock_payment


class ClaimsService:
    def __init__(
        self,
        repository: ClaimsRepository,
        policy_repository: PolicyRepository | None = None,
        photo_storage: ClaimPhotoStorage | None = None,
        document_storage: ClaimDocumentStorage | None = None,
    ):
        self.repository = repository
        self.policy_repository = policy_repository or PolicyRepository()
        self.photo_storage = photo_storage or ClaimPhotoStorage()
        self.document_storage = document_storage or ClaimDocumentStorage()
        self.risk_threshold = float(os.getenv("RISK_SCORE_THRESHOLD", DEFAULT_RISK_THRESHOLD))
        self.fraud_threshold = float(os.getenv("FRAUD_SCORE_THRESHOLD", DEFAULT_FRAUD_THRESHOLD))
        self.auto_settlement_amount_limit = float(
            os.getenv("AUTO_SETTLEMENT_AMOUNT_LIMIT", DEFAULT_AUTO_SETTLEMENT_AMOUNT_LIMIT)
        )
        self.supervisor_review_amount_limit = float(
            os.getenv("SUPERVISOR_REVIEW_AMOUNT_LIMIT", DEFAULT_SUPERVISOR_REVIEW_AMOUNT_LIMIT)
        )
        self.high_risk_score_threshold = float(
            os.getenv("HIGH_RISK_SCORE_THRESHOLD", DEFAULT_HIGH_RISK_SCORE_THRESHOLD)
        )
        self.high_fraud_score_threshold = float(
            os.getenv("HIGH_FRAUD_SCORE_THRESHOLD", DEFAULT_HIGH_FRAUD_SCORE_THRESHOLD)
        )
        self.workflow = build_claim_workflow(
            self.risk_threshold,
            self.fraud_threshold,
            self.auto_settlement_amount_limit,
            self.supervisor_review_amount_limit,
            self.high_risk_score_threshold,
            self.high_fraud_score_threshold,
        )

    def policy_summary(self, policy_number: str) -> dict:
        policy = self.policy_repository.get(policy_number)
        if policy is None or not policy.get("active", False):
            raise KeyError(policy_number)
        vehicle = policy["vehicle"]
        return {
            "policy_number": policy["policy_number"],
            "policyholder_name": policy["policyholder_name"],
            "vehicle_make": vehicle["make"],
            "vehicle_model": vehicle["model"],
            "vehicle_registration": vehicle["registration"],
            "coverage_summary": policy["coverage"],
            "deductible": policy["deductible"],
            "coverage_limit": policy["coverage_limit"],
            "active": True,
            "fictional": True,
        }

    def create_draft(self, claim_data: dict) -> dict:
        policy = self.policy_repository.get(claim_data["policy_number"])
        if policy is None or not policy.get("active", False):
            raise ValueError("An active policy could not be found")
        vehicle = policy["vehicle"]
        claim = {
            **claim_data,
            "claim_id": f"CLM-DEMO-{uuid4().hex[:10].upper()}",
            "claimant_name": policy["policyholder_name"],
            "vehicle_make": vehicle["make"],
            "vehicle_model": vehicle["model"],
            "vehicle_registration": vehicle["registration"],
            "coverage_summary": policy["coverage"],
            "deductible": policy["deductible"],
            "coverage_limit": policy["coverage_limit"],
            "currency": policy.get("currency", "INR"),
            "payment_token_valid": True,
            "depreciation_amount": round(
                float(claim_data["requested_amount"]) * float(policy.get("depreciation_rate", 0)), 2
            ),
            "depreciation_rate": float(policy.get("depreciation_rate", 0)),
            "evidence": [
                {"kind": "repair_estimate", "text": f"Fictional garage estimate: {claim_data['requested_amount']} INR."},
                {
                    "kind": "incident_report",
                    "text": f"{claim_data['loss_description']} Incident date {claim_data['incident_date']} at {claim_data['incident_location']}, PIN {claim_data['incident_pincode']}.",
                },
            ],
            "status": "draft",
            "created_at": datetime.now(timezone.utc).isoformat(),
            "photos": [],
            "photo_count": 0,
            "payment": None,
            "fictional": True,
        }
        self.repository.save_claim(claim)
        self.repository.add_event(claim["claim_id"], "claim_draft_created", "claimant", {
            "policy_number": claim["policy_number"],
            "fictional": True,
        })
        return self.detail(claim["claim_id"])

    async def add_photo(self, claim_id: str, upload) -> dict:
        claim = self._require_claim(claim_id)
        if claim["status"] != "draft":
            raise ValueError("Photos can only be added before claim submission")
        if len(self.repository.get_photos(claim_id)) >= 3:
            raise ValueError("A maximum of three photos is allowed")
        photo = await self.photo_storage.store(upload, claim_id)
        photo["created_at"] = datetime.now(timezone.utc).isoformat()
        self.repository.save_photo(photo)
        self.repository.add_event(claim_id, "claim_photo_added", "claimant", {
            "photo_id": photo["photo_id"],
            "file_name": photo["file_name"],
            "size_bytes": photo["size_bytes"],
        })
        return {key: value for key, value in photo.items() if key != "storage_path"}

    def submit_draft(self, claim_id: str) -> dict:
        claim = self._require_claim(claim_id)
        if claim["status"] != "draft":
            raise ValueError("Claim is not a draft")
        photos = self.repository.get_photos(claim_id)
        documents = self.repository.get_documents(claim_id)
        claim["photos"] = photos
        claim["documents"] = documents
        claim["photo_count"] = len(photos)
        claim["document_review_flags"] = [
            f"document_extraction_pending:{document['file_name']}"
            for document in documents
            if document["extraction_status"] != "extracted"
        ]
        claim["evidence"] = list(claim.get("evidence", [])) + [
            {"kind": "vehicle_photo", "text": photo["file_name"], "photo_id": photo["photo_id"]}
            for photo in photos
        ]
        claim["evidence"].extend(
            {
                "kind": document["document_type"],
                "text": document["extracted_text"] or f"Document {document['file_name']} awaits local OCR review.",
                "document_id": document["document_id"],
            }
            for document in documents
        )
        claim["evidence_checks"] = self._evidence_checks(claim)
        claim["submitted_at"] = datetime.now(timezone.utc).isoformat()
        claim["status"] = "submitted"
        self.repository.save_claim(claim)
        self.repository.add_event(claim_id, "claim_submitted", "claimant", {
            "photo_count": len(photos),
            "incident_date": claim["incident_date"],
            "incident_pincode": claim["incident_pincode"],
        })
        return self.adjudicate(claim_id)

    def submit(self, claim_data: dict) -> dict:
        claim = {
            **claim_data,
            "claim_id": f"CLM-DEMO-{uuid4().hex[:10].upper()}",
            "status": "submitted",
            "payment": None,
            "created_at": datetime.now(timezone.utc).isoformat(),
        }
        if claim.get("incident_pincode") and claim.get("incident_location"):
            claim["evidence_checks"] = self._evidence_checks(claim)
        self.repository.save_claim(claim)
        self.repository.add_event(claim["claim_id"], "claim_submitted", "claimant", {
            "fictional": True,
            "policy_number": claim["policy_number"],
        })
        return self.adjudicate(claim["claim_id"])

    def adjudicate(self, claim_id: str) -> dict:
        claim = self._require_claim(claim_id)
        history = self.repository.get_policy_history(claim["policy_number"], exclude_claim_id=claim_id)
        workflow_started = perf_counter()
        try:
            workflow_result = self.workflow.invoke({
                "claim": claim,
                "agent_steps": [],
                "historical_claims": history,
            })
        except Exception as error:
            failure_step = {
                "agent": "langgraph_workflow",
                "status": "error",
                "detail": "Workflow failed; claim held for human review. Error details are omitted from the claim view.",
                "duration_ms": round((perf_counter() - workflow_started) * 1000, 2),
                "input_tokens": 0,
                "output_tokens": 0,
                "tokens_used": 0,
                "error_count": 1,
                "error_type": type(error).__name__,
                "created_at": datetime.now(timezone.utc).isoformat(),
            }
            claim["agent_steps"] = [*claim.get("agent_steps", []), failure_step]
            claim["status"] = "human_review"
            claim["route_category"] = "human_queue"
            claim["adjudication"] = {
                "recommendation": "hold",
                "rationale": "Automated evaluation did not complete. A reviewer must inspect the claim before any payment.",
                "confidence": "Low",
                "review_flags": ["workflow_execution_failed"],
                "automatic_payment_authorized": False,
                "estimated_settlement": 0,
                "checks": [{"check": "workflow_execution", "passed": False, "reason": "Agent workflow failed; no automated settlement is permitted."}],
                "citations": [],
                "settlement_calculations": [],
                "policy_clauses": [],
                "evidence_checks": claim.get("evidence_checks", []),
                "agent_assessments": {},
            }
            self.repository.save_claim(claim)
            self.repository.add_event(claim_id, "adjudication_failed", "langgraph", {
                "error_type": type(error).__name__,
                "route": "human_review",
            })
            return self.detail(claim_id)
        claim.update(workflow_result.get("claim", {}))
        result = workflow_result["adjudication"]
        claim["adjudication"] = result
        claim["agent_steps"] = workflow_result.get("agent_steps", [])
        claim["evidence_checks"] = result.get("evidence_checks", claim.get("evidence_checks", []))
        existing_payment = self.repository.get_payment(claim_id)
        if existing_payment:
            claim["payment"] = existing_payment
            claim["status"] = "paid"
            claim["route_category"] = "fast_tracked"
        else:
            claim["status"] = "auto_settlement_ready" if result["automatic_payment_authorized"] else "human_review"
            claim["route_category"] = self._route_category(claim, result)
        self.repository.save_claim(claim)
        self.repository.add_event(claim_id, "adjudication_completed", "adjudication_agent", result)
        if result["automatic_payment_authorized"]:
            return self.settle(claim_id, authorized_by="adjudication_agent")
        return self.detail(claim_id)

    def settle(self, claim_id: str, authorized_by: str = "adjudication_agent") -> dict:
        claim = self._require_claim(claim_id)
        existing_payment = self.repository.get_payment(claim_id)
        if existing_payment:
            return self.detail(claim_id)
        if authorized_by == "adjudication_agent" and not claim.get("adjudication", {}).get("automatic_payment_authorized"):
            raise ValueError("Automatic settlement gate has not passed")
        if not claim.get("payment_token_valid"):
            raise ValueError("Payment details are not valid")
        if "policy_exclusion_requires_review" in claim.get("adjudication", {}).get("review_flags", []):
            raise ValueError("Excluded claims cannot be settled")
        amount = claim.get("adjudication", {}).get("estimated_settlement", 0)
        if authorized_by != "adjudication_agent":
            calculations = claim.get("adjudication", {}).get("settlement_calculations", [])
            amount = next((item["amount"] for item in calculations if item.get("operation") == "result"), None)
            if amount is None:
                amount = min(max(claim["requested_amount"] - claim["deductible"], 0), claim["coverage_limit"])
        if amount <= 0:
            raise ValueError("Settlement amount must be positive")
        payment = create_mock_payment(claim_id, amount, claim.get("currency", "INR"))
        self.repository.save_payment(claim_id, payment)
        claim["payment"] = payment
        claim["status"] = "paid"
        claim["route_category"] = "fast_tracked"
        self.repository.save_claim(claim)
        self.repository.add_event(claim_id, "payment_succeeded", authorized_by, payment)
        return self.detail(claim_id)

    def record_decision(
        self,
        claim_id: str,
        action: str,
        reviewer_id: str,
        reason: str,
        modified_amount: float | None = None,
    ) -> dict:
        claim = self._require_claim(claim_id)
        if claim["status"] != "human_review":
            raise ValueError("Claim is not awaiting human review")
        decision = {"action": action, "reviewer_id": reviewer_id, "reason": reason}
        if action == "modify":
            if modified_amount is None or modified_amount <= 0:
                raise ValueError("A positive modified amount is required")
            previous_amount = float(claim.get("requested_amount", 0))
            claim["requested_amount"] = float(modified_amount)
            claim["garage_estimate"] = float(modified_amount)
            depreciation_rate = float(claim.get("depreciation_rate", 0))
            if not depreciation_rate and previous_amount > 0:
                depreciation_rate = float(claim.get("depreciation_amount", 0)) / previous_amount
            claim["depreciation_amount"] = round(float(modified_amount) * depreciation_rate, 2)
            decision["previous_amount"] = previous_amount
            decision["modified_amount"] = float(modified_amount)
            for item in claim.get("evidence", []):
                if item.get("kind") == "repair_estimate":
                    item["text"] = f"Reviewer-modified synthetic garage estimate: {modified_amount} {claim.get('currency', 'INR')}."
            self.repository.add_event(claim_id, "reviewer_decision", reviewer_id, decision)
            claim["status"] = "submitted"
            self.repository.save_claim(claim)
            self.repository.add_event(claim_id, "claim_modified", reviewer_id, {
                "previous_amount": previous_amount,
                "modified_amount": float(modified_amount),
                "reason": reason,
            })
            return self.adjudicate(claim_id)
        self.repository.add_event(claim_id, "reviewer_decision", reviewer_id, decision)
        if action == "approve":
            claim["status"] = "reviewer_approved"
            self.repository.save_claim(claim)
            return self.settle(claim_id, authorized_by=reviewer_id)
        if action == "decline":
            claim["status"] = "declined"
        elif action == "investigate":
            claim["status"] = "investigation"
        else:
            claim["status"] = "awaiting_evidence"
            claim["route_category"] = "human_queue"
        self.repository.save_claim(claim)
        self.repository.add_event(claim_id, "claim_status_changed", reviewer_id, {"status": claim["status"]})
        return self.detail(claim_id)

    def detail(self, claim_id: str) -> dict:
        claim = self._require_claim(claim_id)
        claim["payment"] = self.repository.get_payment(claim_id)
        claim["audit_events"] = self.repository.get_events(claim_id)
        claim["photos"] = self.repository.get_photos(claim_id)
        claim["documents"] = self.repository.get_documents(claim_id)
        return claim

    async def add_document(self, claim_id: str, upload) -> dict:
        claim = self._require_claim(claim_id)
        if claim.get("status") != "draft":
            raise ValueError("Supporting documents can only be added before claim submission")
        if len(self.repository.get_documents(claim_id)) >= 10:
            raise ValueError("A maximum of ten supporting documents is allowed")
        document = await self.document_storage.store(upload, claim_id)
        self.repository.save_document(document)
        self.repository.add_event(claim_id, "claim_document_uploaded", "claimant", {
            "document_id": document["document_id"],
            "file_name": document["file_name"],
            "document_type": document["document_type"],
            "extraction_status": document["extraction_status"],
            "extracted_fields": document["extracted_fields"],
        })
        return {key: value for key, value in document.items() if key not in {"storage_path", "extracted_text"}}

    def add_evidence(self, claim_id: str, kind: str, text: str, actor: str) -> dict:
        claim = self._require_claim(claim_id)
        if claim.get("status") != "awaiting_evidence":
            raise ValueError("Claim is not awaiting requested evidence")
        claim.setdefault("evidence", []).append({"kind": kind, "text": text})
        claim["status"] = "submitted"
        claim["route_category"] = "human_queue"
        self.repository.save_claim(claim)
        self.repository.add_event(claim_id, "additional_evidence_received", actor, {"kind": kind, "text": text})
        return self.adjudicate(claim_id)

    def _evidence_checks(self, claim: dict) -> list[dict]:
        previous_claim_count = sum(
            1 for existing in self.repository.list_claims()
            if existing.get("policy_number") == claim["policy_number"]
            and existing.get("claim_id") != claim["claim_id"]
        )
        return [
            {"check": "weather_on_loss_date", "status": "not_configured", "detail": "External weather verification is not configured in local demo mode."},
            {"check": "address_and_pincode", "status": "format_valid", "detail": f"Incident location recorded for PIN {claim['incident_pincode']} ({claim['incident_location']})."},
            {"check": "payee_bank_details", "status": "synthetic_test_profile", "detail": "Synthetic payout profile only; no bank account or IFSC data is stored."},
            {"check": "claims_history", "status": "available", "previous_claim_count": previous_claim_count, "detail": f"{previous_claim_count} prior synthetic claim(s) for this policy."},
        ]

    def _route_category(self, claim: dict, adjudication: dict) -> str:
        if claim.get("status") == "paid":
            return "fast_tracked"
        if (
            claim.get("requested_amount", 0) > self.supervisor_review_amount_limit
            or (adjudication.get("risk_score") or 0) >= self.high_risk_score_threshold
            or (adjudication.get("fraud_score") or 0) >= self.high_fraud_score_threshold
            or (
                (adjudication.get("risk_score") or 0) >= self.risk_threshold
                and (adjudication.get("fraud_score") or 0) >= self.fraud_threshold
            )
        ):
            return "supervisor_review"
        if "amount_above_auto_settlement_limit" in adjudication.get("review_flags", []):
            return "needs_approval"
        if (adjudication.get("fraud_score") or 0) >= adjudication.get("fraud_threshold", 40):
            return "investigate"
        return "human_queue"

    def _require_claim(self, claim_id: str) -> dict:
        claim = self.repository.get_claim(claim_id)
        if claim is None:
            raise KeyError(claim_id)
        return claim
