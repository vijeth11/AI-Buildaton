from __future__ import annotations

import json
from pathlib import Path


class PolicyRepository:
    def __init__(self, policies_path: str | None = None):
        self.policies_path = Path(policies_path) if policies_path else Path(__file__).resolve().parents[3] / "data" / "policies.json"

    def get(self, policy_number: str) -> dict | None:
        policies = json.loads(self.policies_path.read_text(encoding="utf-8"))
        policy = next((item for item in policies if item["policy_number"] == policy_number), None)
        return dict(policy) if policy else None
