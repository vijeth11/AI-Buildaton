from __future__ import annotations

import json
import random
from datetime import date, timedelta
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

from services.api.claims_api.repository import ClaimsRepository
from services.application.claims import ClaimsService


root = Path(__file__).resolve().parents[1]
scenarios = json.loads((root / "data" / "demo_claims.json").read_text(encoding="utf-8"))
service = ClaimsService(ClaimsRepository())
existing = service.repository.list_claims()

for scenario in scenarios:
    scenario_name = scenario["scenario"]
    saved_indices = {
        claim.get("scenario_index")
        for claim in existing
        if claim.get("scenario_name") == scenario_name
    }
    randomizer = random.Random(f"claims-demo:{scenario_name}:20261004")
    locations = [
        ("400053", "Andheri West, Mumbai"),
        ("600028", "Alwarpet, Chennai"),
        ("560034", "Koramangala, Bengaluru"),
        ("380015", "Satellite, Ahmedabad"),
        ("500081", "Madhapur, Hyderabad"),
    ]
    for index in range(1, 31):
        if index in saved_indices:
            continue
        claim_data = dict(scenario["claim"])
        claim_data["scenario_name"] = scenario_name
        claim_data["scenario_index"] = index
        claim_data["claimant_name"] = f"Fictional Policyholder {index:02d}"
        claim_data["requested_amount"] = round(randomizer.uniform(900, 4800), 2)
        if scenario_name == "high-fraud-inconsistency":
            claim_data["requested_amount"] = round(randomizer.uniform(5000, 9500), 2)
            claim_data["risk_score"] = randomizer.randint(65, 95)
            claim_data["fraud_score"] = randomizer.randint(55, 95)
        elif scenario_name == "excluded-wear-and-tear":
            claim_data["risk_score"] = randomizer.randint(0, 20)
            claim_data["fraud_score"] = randomizer.randint(0, 20)
        else:
            claim_data["risk_score"] = randomizer.randint(0, 25)
            claim_data["fraud_score"] = randomizer.randint(0, 20)
        claim_data["evidence"] = [dict(item) for item in scenario["claim"]["evidence"]]
        pincode, location = locations[(index - 1) % len(locations)]
        incident_date = (date(2026, 8, 1) + timedelta(days=(index - 1) % 28)).isoformat()
        incident_time = f"{8 + ((index - 1) % 10):02d}:{15 + ((index - 1) % 40):02d}"
        requested_amount = float(claim_data["requested_amount"])
        claim_data.update({
            "loss_description": (
                f"{scenario['description']} Incident occurred on {incident_date} at {incident_time} in {location}. "
                f"Driver remained at scene, exchanged details, and submitted complete synthetic evidence bundle."
            ),
            "incident_date": incident_date,
            "incident_time": incident_time,
            "incident_pincode": pincode,
            "incident_location": location,
            "vehicle_make": "Hyundai",
            "vehicle_model": "i20",
            "vehicle_year": 2023,
            "vehicle_registration": "MH00 XX 0001",
            "vehicle_vin": f"SYNTHVIN{index:08d}",
            "driver_name": claim_data["claimant_name"],
            "driver_license_number": f"MH14{index:06d}",
            "witness_information": "No independent witness; CCTV footage available with local security desk.",
            "police_report_number": f"SYN-FIR-{incident_date.replace('-', '')}-{index:02d}",
            "policy_active_on_loss_date": True,
            "coverage_summary": "Comprehensive cover with Engine Protector",
            "deductible": 1000,
            "coverage_limit": 500000,
            "depreciation_amount": round(requested_amount * 0.19, 2),
            "currency": "INR",
        })

        evidence_overrides: dict[str, str] = {
            "incident_report": (
                f"Fictional incident report confirms a low-speed collision on {incident_date} at {incident_time} "
                f"in {location} (PIN {pincode})."
            ),
            "repair_estimate": f"Fictional authorized garage estimate confirms repair total INR {requested_amount:,.2f}.",
            "policy_document": f"Fictional policy schedule confirms active comprehensive cover on {incident_date}.",
            "vehicle_photo": "Fictional photo bundle includes front, side, and rear damage views.",
        }
        for evidence in claim_data["evidence"]:
            kind = evidence.get("kind", "")
            base_text = evidence_overrides.get(kind, evidence.get("text", ""))
            if scenario_name == "fast-track-collision-complete":
                evidence["text"] = base_text
            else:
                evidence["text"] = f"{base_text} Synthetic batch reference {scenario_name}-{index:02d}."

        if scenario_name == "missing-estimate":
            claim_data["witness_information"] = "Witness unavailable; claimant provided self-declaration only."
        if scenario_name == "fast-track-collision-complete":
            claim_data["fictional"] = False
            claim_data["loss_description"] = (
                f"Minor collision on {incident_date} at {incident_time} in {location}. "
                f"Complete documents provided, no injuries, no third-party damage, and policy active confirmation attached."
            )
            claim_data["risk_score"] = randomizer.randint(0, 12)
            claim_data["fraud_score"] = randomizer.randint(0, 10)
            claim_data["requested_amount"] = round(randomizer.uniform(1400, 3600), 2)
            claim_data["depreciation_amount"] = round(float(claim_data["requested_amount"]) * 0.19, 2)
            claim_data["third_party_involvement"] = "None"
            claim_data["injuries_reported"] = "None"
            claim_data["repair_facility_name"] = "FastFix Garage"
            claim_data["repair_facility_address"] = f"SV Road, {location}"
            claim_data["repair_facility_contact"] = "9999999999"
            claim_data["vehicle_condition"] = "Drivable"
            claim_data["payment_disbursement_preference"] = "Synthetic UPI test profile"
            claim_data["records_authorization"] = "Provided"
            for evidence in claim_data["evidence"]:
                if evidence.get("kind") == "repair_estimate":
                    evidence["text"] = f"Authorized garage estimate confirms repair total INR {float(claim_data['requested_amount']):,.2f}."

        result = service.submit(claim_data)
        if scenario_name == "fast-track-collision-complete":
            result = service.settle(result["claim_id"], authorized_by="reviewer-demo")
        print(f"{scenario_name} {index:02d}/30: {result['claim_id']} -> {result['status']}")
