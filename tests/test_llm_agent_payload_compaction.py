from __future__ import annotations

from services.agents import llm_agents


def test_assess_fraud_risk_compacts_large_payload_before_serialization(monkeypatch):
    captured_payload = {}

    def fake_run_structured(_agent_name, _schema, _system_text, payload):
        captured_payload.update(payload)
        return llm_agents.AgentResult(status="unavailable", output={})

    monkeypatch.setattr(llm_agents, "_run_structured", fake_run_structured)

    claim = {
        "policy_number": "DIC-PC-0091273",
        "loss_description": "x" * 5000,
        "evidence": [{"kind": "incident_report", "text": "y" * 5000}] * 40,
    }
    history = [{"claim_id": "CLM-1", "summary": "z" * 5000}] * 30

    llm_agents.assess_fraud_risk(claim, history)

    assert len(captured_payload["claim"]["loss_description"]) < 1200
    assert len(captured_payload["claim"]["evidence"]) == 20
    assert len(captured_payload["synthetic_history"]) == 12
    assert len(captured_payload["synthetic_history"][0]["summary"]) < 500
