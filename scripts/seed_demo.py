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
        ("400051", "Andheri West, Mumbai"),
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
        claim_data.update({
            "loss_description": scenario["description"],
            "incident_date": (date(2026, 8, 1) + timedelta(days=(index - 1) % 28)).isoformat(),
            "incident_pincode": pincode,
            "incident_location": location,
            "vehicle_make": "Hyundai",
            "vehicle_model": "i20",
            "vehicle_registration": "MH00 XX 0001",
            "coverage_summary": "Comprehensive cover with Engine Protector",
            "deductible": 1000,
            "coverage_limit": 500000,
            "depreciation_amount": round(claim_data["requested_amount"] * 0.19, 2),
            "currency": "INR",
        })
        for evidence in claim_data["evidence"]:
            evidence["text"] = f"{evidence['text']} Synthetic batch reference {scenario_name}-{index:02d}."
        result = service.submit(claim_data)
        print(f"{scenario_name} {index:02d}/30: {result['claim_id']} -> {result['status']}")
