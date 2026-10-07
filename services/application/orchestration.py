from __future__ import annotations

import os
from datetime import datetime, timezone
from time import perf_counter
from typing import Literal, TypedDict

from langgraph.graph import END, START, StateGraph

from services.agents.adjudication import (
    DEFAULT_HIGH_FRAUD_SCORE_THRESHOLD,
    DEFAULT_HIGH_RISK_SCORE_THRESHOLD,
    DEFAULT_SUPERVISOR_REVIEW_AMOUNT_LIMIT,
    adjudicate,
)
from services.agents.explanation import summarize_decision
from services.agents.intake import validate_claim
from services.agents.llm_agents import assess_coverage, assess_fraud_risk, assess_intake
from services.agents.risk import calculate_risk_scores
from services.rag.retriever import retrieve_sources


class ClaimWorkflowState(TypedDict, total=False):
    claim: dict
    sources: list[dict]
    adjudication: dict
    route: Literal["automatic_settlement", "human_review"]
    agent_steps: list[dict]
    agent_assessments: dict
    historical_claims: list[dict]


def _record_step(
    state: ClaimWorkflowState,
    agent: str,
    started: float,
    status: str,
    detail: str,
    input_tokens: int = 0,
    output_tokens: int = 0,
    error: str | None = None,
    reason_code: str | None = None,
) -> list[dict]:
    step = {
        "agent": agent,
        "status": status,
        "detail": detail,
        "duration_ms": round((perf_counter() - started) * 1000, 2),
        "input_tokens": input_tokens,
        "output_tokens": output_tokens,
        "tokens_used": input_tokens + output_tokens,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "error_count": 1 if status == "error" else 0,
        "error": error,
        "reason_code": reason_code,
    }
    return [*state.get("agent_steps", []), step]


def build_claim_workflow(
    risk_threshold: float,
    fraud_threshold: float,
    auto_settlement_amount_limit: float = 50000,
    supervisor_review_amount_limit: float = DEFAULT_SUPERVISOR_REVIEW_AMOUNT_LIMIT,
    high_risk_score_threshold: float = DEFAULT_HIGH_RISK_SCORE_THRESHOLD,
    high_fraud_score_threshold: float = DEFAULT_HIGH_FRAUD_SCORE_THRESHOLD,
):
    def intake_llm_node(state: ClaimWorkflowState) -> dict:
        started = perf_counter()
        result = assess_intake(state["claim"])
        assessments = dict(state.get("agent_assessments", {}))
        assessments["intake_agent"] = {"status": result.status, **result.output, "error": result.error, "reason_code": result.reason_code}
        output = result.output
        flags = []
        if result.status == "completed":
            flags = [f"intake_missing_or_ambiguous:{value}" for value in output.get("missing_or_ambiguous_fields", [])]
            flags += [f"intake_inconsistency:{value}" for value in output.get("inconsistencies", [])]
        claim = dict(state["claim"])
        claim["intake_agent_flags"] = flags
        detail = output.get("summary") if result.status == "completed" else result.error or "LLM intake validation unavailable."
        return {
            "claim": claim,
            "agent_assessments": assessments,
            "agent_steps": _record_step(
                state,
                "intake_agent_llm",
                started,
                result.status,
                detail,
                result.input_tokens,
                result.output_tokens,
                result.error,
                result.reason_code,
            ),
        }

    def retrieve_policy_history_node(state: ClaimWorkflowState) -> dict:
        started = perf_counter()
        sources = retrieve_sources(state["claim"])
        return {
            "sources": sources,
            "agent_steps": _record_step(
                state,
                "policy_rag",
                started,
                "completed",
                f"ChromaDB retrieved {len(sources)} policy and synthetic history passages.",
            ),
        }

    def fraud_risk_llm_node(state: ClaimWorkflowState) -> dict:
        started = perf_counter()
        claim = dict(state["claim"])
        claim.update(calculate_risk_scores(claim))
        history = [source for source in state["sources"] if source.get("kind") == "historical_example"]
        history.extend(state.get("historical_claims", []))
        result = assess_fraud_risk(claim, history)
        assessment = {"status": result.status, **result.output, "error": result.error, "reason_code": result.reason_code}
        assessments = dict(state.get("agent_assessments", {}))
        assessments["fraud_risk_agent"] = assessment
        claim["fraud_risk_agent_assessment"] = assessment
        detail = (
            result.output.get("rationale", "LLM triage completed.")
            if result.status == "completed"
            else result.error or "LLM risk assessment unavailable; deterministic score retained."
        )
        return {
            "claim": claim,
            "agent_assessments": assessments,
            "historical_claims": history,
            "agent_steps": _record_step(
                state,
                "fraud_risk_agent_llm",
                started,
                result.status,
                detail,
                result.input_tokens,
                result.output_tokens,
                result.error,
                result.reason_code,
            ),
        }

    def adjudication_llm_node(state: ClaimWorkflowState) -> dict:
        started = perf_counter()
        result = assess_coverage(state["claim"], state["sources"])
        assessment = {"status": result.status, **result.output, "error": result.error, "reason_code": result.reason_code}
        assessments = dict(state.get("agent_assessments", {}))
        assessments["adjudication_agent"] = assessment
        detail = (
            result.output.get("rationale", "Policy interpretation completed.")
            if result.status == "completed"
            else result.error or "LLM policy interpretation unavailable; deterministic rules remain active."
        )
        return {
            "agent_assessments": assessments,
            "agent_steps": _record_step(
                state,
                "adjudication_agent_llm",
                started,
                result.status,
                detail,
                result.input_tokens,
                result.output_tokens,
                result.error,
                result.reason_code,
            ),
        }

    def deterministic_rules_node(state: ClaimWorkflowState) -> dict:
        started = perf_counter()
        result = adjudicate(
            state["claim"],
            state["sources"],
            risk_threshold=risk_threshold,
            fraud_threshold=fraud_threshold,
            auto_settlement_amount_limit=auto_settlement_amount_limit,
            supervisor_review_amount_limit=supervisor_review_amount_limit,
            high_risk_score_threshold=high_risk_score_threshold,
            high_fraud_score_threshold=high_fraud_score_threshold,
            agent_assessments=state.get("agent_assessments", {}),
        )
        result["agent_assessments"] = state.get("agent_assessments", {})
        result["historical_claims_reviewed"] = state.get("historical_claims", [])
        return {
            "adjudication": result,
            "agent_steps": _record_step(
                state,
                "deterministic_rules_engine",
                started,
                "completed",
                f"Rules Engine returned {result['recommendation']}: {result['rationale']}",
            ),
        }

    def explanation_node(state: ClaimWorkflowState) -> dict:
        started = perf_counter()
        result = dict(state["adjudication"])
        try:
            result["reviewer_summary"], usage = summarize_decision(result)
            if result["reviewer_summary"]:
                detail = "LangChain GPT reviewer explanation generated."
                status = "completed"
            else:
                explanations_enabled = os.getenv("GPT_EXPLANATIONS_ENABLED", "true").lower() == "true"
                key_configured = bool(os.getenv("OPENAI_API_KEY", "").strip())
                if not explanations_enabled:
                    detail = "Explanation disabled by GPT_EXPLANATIONS_ENABLED=false."
                elif not key_configured:
                    detail = "Explanation unavailable because OPENAI_API_KEY is not configured."
                else:
                    detail = "Explanation model returned an empty response."
                status = "unavailable"
            input_tokens = usage["input_tokens"]
            output_tokens = usage["output_tokens"]
            error = None
        except Exception as exception:
            result["reviewer_summary"] = None
            detail = "Optional explanation failed; deterministic rules result retained."
            status = "error"
            input_tokens = 0
            output_tokens = 0
            error = f"{type(exception).__name__}: {exception}"
        return {
            "adjudication": result,
            "agent_steps": _record_step(
                state,
                "reviewer_explanation_llm",
                started,
                status,
                detail,
                input_tokens,
                output_tokens,
                error,
            ),
        }

    def settlement_routing_node(state: ClaimWorkflowState) -> dict:
        started = perf_counter()
        route = "automatic_settlement" if state["adjudication"]["automatic_payment_authorized"] else "human_review"
        result = dict(state["adjudication"])
        result["orchestration_route"] = route
        return {
            "adjudication": result,
            "route": route,
            "agent_steps": _record_step(
                state,
                "langgraph_settlement_router",
                started,
                "completed",
                f"Routed to {route}; only the Rules Engine decides eligibility.",
            ),
        }

    graph = StateGraph(ClaimWorkflowState)
    graph.add_node("intake_llm_agent", intake_llm_node)
    graph.add_node("policy_rag", retrieve_policy_history_node)
    graph.add_node("fraud_risk_llm_agent", fraud_risk_llm_node)
    graph.add_node("adjudication_llm_agent", adjudication_llm_node)
    graph.add_node("deterministic_rules_engine", deterministic_rules_node)
    graph.add_node("reviewer_explanation", explanation_node)
    graph.add_node("settlement_router", settlement_routing_node)
    graph.add_edge(START, "intake_llm_agent")
    graph.add_edge("intake_llm_agent", "policy_rag")
    graph.add_edge("policy_rag", "fraud_risk_llm_agent")
    graph.add_edge("fraud_risk_llm_agent", "adjudication_llm_agent")
    graph.add_edge("adjudication_llm_agent", "deterministic_rules_engine")
    graph.add_edge("deterministic_rules_engine", "reviewer_explanation")
    graph.add_edge("reviewer_explanation", "settlement_router")
    graph.add_conditional_edges(
        "settlement_router",
        lambda state: state["route"],
        {"automatic_settlement": END, "human_review": END},
    )
    return graph.compile()
