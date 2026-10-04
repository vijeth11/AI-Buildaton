from __future__ import annotations

import pytest


@pytest.fixture(autouse=True)
def disable_external_llm_calls_for_tests(monkeypatch):
    """Keep routine tests synthetic and offline; LLM behavior is tested with a stub client."""
    monkeypatch.setenv("LLM_AGENTS_ENABLED", "false")
    monkeypatch.setenv("GPT_EXPLANATIONS_ENABLED", "false")
