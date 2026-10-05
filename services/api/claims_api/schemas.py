from __future__ import annotations

from datetime import date
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


class EvidenceInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    kind: str = Field(min_length=1, max_length=64)
    text: str = Field(min_length=1, max_length=10000)


class ClaimSubmission(BaseModel):
    model_config = ConfigDict(extra="forbid")

    policy_number: str = Field(default="POL-AUTO-100", min_length=1, max_length=64)
    loss_type: str = Field(min_length=1, max_length=64)
    loss_description: str = Field(min_length=10, max_length=4000)
    incident_date: date
    incident_pincode: str = Field(pattern=r"^\d{6}$")
    incident_location: str = Field(min_length=2, max_length=160)
    garage_estimate: float = Field(gt=0, le=10_000_000)
    currency: Literal["INR"] = "INR"
    evidence: list[EvidenceInput] = Field(default_factory=list, max_length=30)
    fictional: Literal[True] = True

    def to_claim_data(self) -> dict:
        data = self.model_dump(mode="json")
        data["requested_amount"] = data.pop("garage_estimate")
        return data


class PolicySummary(BaseModel):
    policy_number: str
    policyholder_name: str
    vehicle_make: str
    vehicle_model: str
    vehicle_registration: str
    coverage_summary: str
    deductible: float
    coverage_limit: float
    active: bool
    fictional: Literal[True]


class ReviewerDecision(BaseModel):
    model_config = ConfigDict(extra="forbid")

    action: Literal["approve", "decline", "request_evidence", "investigate", "modify"]
    reviewer_id: str = Field(min_length=1, max_length=100)
    reason: str = Field(min_length=3, max_length=2000)
    modified_amount: float | None = Field(default=None, gt=0, le=10_000_000)

    @model_validator(mode="after")
    def validate_modified_amount(self):
        if self.action == "modify" and self.modified_amount is None:
            raise ValueError("modified_amount is required for a modify action")
        if self.action != "modify" and self.modified_amount is not None:
            raise ValueError("modified_amount is only allowed for a modify action")
        return self


class RepairEstimateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    vehicle_make: str = Field(min_length=1, max_length=60)
    vehicle_model: str = Field(min_length=1, max_length=60)
    damage_type: Literal["collision", "flood", "engine_water_ingress", "glass", "bodywork"]
    severity: Literal["low", "medium", "high"]
    fictional: Literal[True] = True


class BankVerificationRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    ifsc_code: str = Field(pattern=r"^[A-Za-z]{4}0[A-Za-z0-9]{6}$")
    fictional: Literal[True] = True


class EvidenceSubmission(BaseModel):
    model_config = ConfigDict(extra="forbid")

    kind: str = Field(min_length=1, max_length=64)
    text: str = Field(min_length=5, max_length=10000)


class SimulatedProviderPayoutRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    bankaccount: str = Field(pattern=r"^[0-9]{6,20}$")
    amount: float = Field(gt=0, le=10_000_000)
    currency: Literal["INR"] = "INR"
    fictional: Literal[True] = True
