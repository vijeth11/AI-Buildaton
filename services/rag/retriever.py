from __future__ import annotations

import hashlib
import json
import math
import os
import re
from functools import lru_cache
from pathlib import Path

import chromadb
from pypdf import PdfReader

from services.rag.policy_data import POLICY_SOURCE_METADATA

ROOT = Path(__file__).resolve().parents[2]
POLICY_PDF_DIR = Path(os.getenv("POLICY_PDF_DIR", str(ROOT / "data" / "policies-pdf")))
HISTORY_SOURCES = [
    {
        "source_id": "HIST-SYNTH-001",
        "kind": "historical_example",
        "text": "Synthetic example: a low-risk collision with a repair estimate and incident report passed deterministic checks and was recommended for approval after reviewer confirmation. Historical similarity is not proof of coverage.",
    },
    {
        "source_id": "HIST-SYNTH-002",
        "kind": "historical_example",
        "text": "Synthetic example: conflicting incident dates and amounts were routed to human review. Historical similarity is not evidence of coverage.",
    },
]
COLLECTION_NAME = "claims-policy-kb-v2"
EMBEDDING_DIMENSIONS = 384


def _local_embedding(text: str) -> list[float]:
    """Deterministic local feature hashing; no external embedding service or model download."""
    normalized = re.findall(r"[a-z0-9]+", text.lower())
    features = list(normalized)
    features.extend(f"{left}_{right}" for left, right in zip(normalized, normalized[1:]))
    vector = [0.0] * EMBEDDING_DIMENSIONS
    for feature in features:
        digest = hashlib.blake2b(feature.encode("utf-8"), digest_size=8).digest()
        value = int.from_bytes(digest[:4], "big") % EMBEDDING_DIMENSIONS
        sign = 1.0 if digest[4] & 1 else -1.0
        vector[value] += sign
    norm = math.sqrt(sum(component * component for component in vector))
    if norm:
        vector = [component / norm for component in vector]
    return vector


def _policy_pdf_records() -> list[dict]:
    if not POLICY_PDF_DIR.is_dir():
        raise RuntimeError(f"Required policy PDF directory not found: {POLICY_PDF_DIR}")
    records = []
    for path in sorted(POLICY_PDF_DIR.glob("*.pdf")):
        source_id = path.stem.upper()
        metadata = POLICY_SOURCE_METADATA.get(path.name)
        if metadata is None:
            raise RuntimeError(f"Policy PDF has no approved synthetic metadata entry: {path.name}")
        reader = PdfReader(str(path))
        text = "\n".join(page.extract_text() or "" for page in reader.pages).strip()
        if not text:
            raise RuntimeError(f"No extractable text found in required policy PDF: {path.name}")
        records.append({"source_id": source_id, "text": text, **metadata})
    if not records:
        raise RuntimeError(f"No synthetic policy PDFs found in {POLICY_PDF_DIR}")
    return records


def _corpus() -> list[dict]:
    policies = _policy_pdf_records()
    return policies + [
        {**source, "kind": "historical_example", "covered_loss_types": [], "excluded_loss_types": [], "clauses": []}
        for source in HISTORY_SOURCES
    ]


def _collection():
    configured_path = Path(os.getenv("CHROMA_PATH", ".chroma"))
    configured_path.mkdir(parents=True, exist_ok=True)
    client = chromadb.PersistentClient(path=str(configured_path))
    return client.get_or_create_collection(
        COLLECTION_NAME,
        metadata={"hnsw:space": "cosine", "embedding_model": "local-feature-hash-v1"},
    )


def _index_documents(collection, corpus: list[dict]) -> None:
    collection.upsert(
        ids=[source["source_id"] for source in corpus],
        documents=[source["text"] for source in corpus],
        embeddings=[_local_embedding(source["text"]) for source in corpus],
        metadatas=[
            {
                "source_id": source["source_id"],
                "kind": source["kind"],
                "covered_loss_types": json.dumps(source.get("covered_loss_types", [])),
                "excluded_loss_types": json.dumps(source.get("excluded_loss_types", [])),
                "clauses": json.dumps(source.get("clauses", [])),
                "document_name": source.get("document_name", source["source_id"]),
            }
            for source in corpus
        ],
    )


def retrieve_sources(claim: dict, top_k: int | None = None) -> list[dict]:
    """Index local authored PDFs and query mandatory persistent ChromaDB on every adjudication."""
    corpus = _corpus()
    collection = _collection()
    _index_documents(collection, corpus)
    count = collection.count()
    if count < len(corpus):
        raise RuntimeError(f"ChromaDB index is incomplete: expected {len(corpus)} documents, found {count}")
    query = " ".join(
        str(claim.get(key, ""))
        for key in ("loss_type", "loss_description", "coverage_summary", "policy_number")
    ).strip()
    result_count = min(top_k or len(corpus), count)
    result = collection.query(
        query_embeddings=[_local_embedding(query)],
        n_results=result_count,
        include=["documents", "metadatas", "distances"],
    )
    documents = result.get("documents", [[]])[0]
    metadatas = result.get("metadatas", [[]])[0]
    distances = result.get("distances", [[]])[0]
    sources = []
    for document, metadata, distance in zip(documents, metadatas, distances):
        sources.append({
            "source_id": metadata["source_id"],
            "kind": metadata["kind"],
            "text": document,
            "covered_loss_types": json.loads(metadata.get("covered_loss_types", "[]")),
            "excluded_loss_types": json.loads(metadata.get("excluded_loss_types", "[]")),
            "clauses": json.loads(metadata.get("clauses", "[]")),
            "document_name": metadata.get("document_name"),
            "distance": float(distance),
        })
    if not sources:
        raise RuntimeError("ChromaDB returned no policy/history evidence for adjudication")
    return sources


def chroma_health() -> dict:
    corpus = _corpus()
    collection = _collection()
    _index_documents(collection, corpus)
    return {
        "status": "healthy",
        "collection": COLLECTION_NAME,
        "documents_indexed": collection.count(),
        "policy_pdfs": len(list(POLICY_PDF_DIR.glob("*.pdf"))),
        "embedding_model": "local-feature-hash-v1",
    }
