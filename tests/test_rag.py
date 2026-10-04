from __future__ import annotations


def test_required_chroma_indexes_policy_pdfs_and_returns_policy_and_history(monkeypatch, tmp_path):
    monkeypatch.setenv("CHROMA_PATH", str(tmp_path / "chroma"))
    from services.rag.retriever import chroma_health, retrieve_sources

    health = chroma_health()
    sources = retrieve_sources({
        "policy_number": "DIC-PC-0091273",
        "loss_type": "flood",
        "loss_description": "engine water ingress and Engine Protector",
    })

    assert health["status"] == "healthy"
    assert health["policy_pdfs"] == 3
    assert health["documents_indexed"] == 5
    assert any(source["kind"] == "policy" and "Engine Protector" in source["text"] for source in sources)
    assert any(source["kind"] == "historical_example" for source in sources)
    assert all(source.get("distance") is not None for source in sources)


def test_chroma_collection_is_persistent_between_retrieval_calls(monkeypatch, tmp_path):
    monkeypatch.setenv("CHROMA_PATH", str(tmp_path / "chroma"))
    from services.rag.retriever import chroma_health, retrieve_sources

    retrieve_sources({"loss_type": "collision", "loss_description": "synthetic collision"})
    second = chroma_health()
    assert second["documents_indexed"] == 5
