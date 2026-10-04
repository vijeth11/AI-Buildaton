from __future__ import annotations

POLICY_SOURCE_METADATA = {
    "DIC-PC-0091273-coverage.pdf": {
        "kind": "policy",
        "document_name": "DIC-PC-0091273 coverage and benefits",
        "covered_loss_types": ["collision", "flood", "engine_water_ingress"],
        "excluded_loss_types": [],
        "clauses": [
            {"clause_id": "4.1", "title": "Comprehensive accidental damage", "summary": "Sudden accidental collision and flood damage are covered subject to exclusions, deductible and policy limit."},
            {"clause_id": "4.2", "title": "Engine Protector add-on", "summary": "Internal engine water-ingress damage is covered when Engine Protector is active."},
            {"clause_id": "7.1", "title": "Compulsory deductible", "summary": "Subtract the INR 1,000 compulsory deductible."},
            {"clause_id": "7.2", "title": "Depreciation", "summary": "Apply the synthetic demonstration depreciation rate before the coverage limit."},
            {"clause_id": "8.1", "title": "Per-incident limit", "summary": "Maximum synthetic coverage is INR 500,000 per incident."},
        ],
    },
    "DIC-PC-0091273-exclusions.pdf": {
        "kind": "policy",
        "document_name": "DIC-PC-0091273 exclusions",
        "covered_loss_types": [],
        "excluded_loss_types": ["wear_and_tear", "intentional_damage", "racing"],
        "clauses": [
            {"clause_id": "5.1", "title": "Excluded loss types", "summary": "Wear and tear, gradual deterioration, unsupported mechanical breakdown, intentional damage and racing are excluded."},
        ],
    },
    "DIC-PC-0091273-claims-evidence.pdf": {
        "kind": "policy",
        "document_name": "DIC-PC-0091273 evidence and settlement workflow",
        "covered_loss_types": [],
        "excluded_loss_types": [],
        "clauses": [
            {"clause_id": "INTAKE", "title": "Required claim evidence", "summary": "Policy, loss facts, incident date/location/PIN, garage estimate and up to three vehicle photos are required."},
            {"clause_id": "AUTO-SETTLEMENT", "title": "Automatic settlement eligibility", "summary": "All deterministic rules must pass, estimate <= INR 50,000, scores below thresholds and positive payable amount."},
        ],
    },
}
