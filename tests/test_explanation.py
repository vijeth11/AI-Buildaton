from __future__ import annotations

from types import SimpleNamespace

from services.agents import explanation


class StubExplanationModel:
    def __init__(self, content):
        self._content = content

    def invoke(self, _messages):
        return SimpleNamespace(
            content=self._content,
            usage_metadata={"input_tokens": 11, "output_tokens": 4},
        )


def test_summarize_decision_supports_string_content(monkeypatch):
    monkeypatch.setenv("GPT_EXPLANATIONS_ENABLED", "true")
    monkeypatch.setenv("OPENAI_API_KEY", "test-only-not-a-real-key")
    monkeypatch.setattr(explanation, "ChatOpenAI", lambda **_: StubExplanationModel("Synthetic summary"))

    summary, usage = explanation.summarize_decision({"recommendation": "approve"})

    assert summary == "Synthetic summary"
    assert usage == {"input_tokens": 11, "output_tokens": 4}


def test_summarize_decision_supports_block_content(monkeypatch):
    monkeypatch.setenv("GPT_EXPLANATIONS_ENABLED", "true")
    monkeypatch.setenv("OPENAI_API_KEY", "test-only-not-a-real-key")
    monkeypatch.setattr(
        explanation,
        "ChatOpenAI",
        lambda **_: StubExplanationModel([
            {"type": "output_text", "text": "Line one."},
            {"type": "output_text", "text": "Line two."},
        ]),
    )

    summary, usage = explanation.summarize_decision({"recommendation": "approve"})

    assert summary == "Line one.\nLine two."
    assert usage == {"input_tokens": 11, "output_tokens": 4}
