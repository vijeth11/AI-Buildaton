from __future__ import annotations

import json
import os
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterator


class ClaimsRepository:
    """Small SQLite adapter for local demo claims, audit events, and payments."""

    def __init__(self, database_path: str | None = None):
        configured_path = database_path or os.getenv("CLAIMS_DB_PATH", ".local/claims.sqlite3")
        self.database_path = Path(configured_path)
        self.database_path.parent.mkdir(parents=True, exist_ok=True)
        self._initialize()

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.database_path)
        connection.row_factory = sqlite3.Row
        return connection

    @contextmanager
    def _connection(self) -> Iterator[sqlite3.Connection]:
        connection = self._connect()
        try:
            yield connection
            connection.commit()
        except Exception:
            connection.rollback()
            raise
        finally:
            connection.close()

    def _initialize(self) -> None:
        with self._connection() as connection:
            connection.executescript(
                """
                CREATE TABLE IF NOT EXISTS claims (
                    claim_id TEXT PRIMARY KEY,
                    status TEXT NOT NULL,
                    claim_json TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS audit_events (
                    event_id INTEGER PRIMARY KEY AUTOINCREMENT,
                    claim_id TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    event_json TEXT NOT NULL,
                    FOREIGN KEY(claim_id) REFERENCES claims(claim_id)
                );
                CREATE TABLE IF NOT EXISTS payments (
                    claim_id TEXT PRIMARY KEY,
                    payment_json TEXT NOT NULL,
                    FOREIGN KEY(claim_id) REFERENCES claims(claim_id)
                );
                CREATE TABLE IF NOT EXISTS claim_photos (
                    photo_id TEXT PRIMARY KEY,
                    claim_id TEXT NOT NULL,
                    file_name TEXT NOT NULL,
                    content_type TEXT NOT NULL,
                    size_bytes INTEGER NOT NULL,
                    storage_path TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    FOREIGN KEY(claim_id) REFERENCES claims(claim_id)
                );
                CREATE TABLE IF NOT EXISTS claim_documents (
                    document_id TEXT PRIMARY KEY,
                    claim_id TEXT NOT NULL,
                    file_name TEXT NOT NULL,
                    content_type TEXT NOT NULL,
                    size_bytes INTEGER NOT NULL,
                    storage_path TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    extraction_status TEXT NOT NULL,
                    document_type TEXT NOT NULL,
                    extracted_text TEXT NOT NULL,
                    extracted_fields_json TEXT NOT NULL,
                    FOREIGN KEY(claim_id) REFERENCES claims(claim_id)
                );
                """
            )

    def save_claim(self, claim: dict[str, Any]) -> None:
        with self._connection() as connection:
            connection.execute(
                "INSERT INTO claims(claim_id, status, claim_json) VALUES (?, ?, ?) "
                "ON CONFLICT(claim_id) DO UPDATE SET status=excluded.status, claim_json=excluded.claim_json",
                (claim["claim_id"], claim["status"], json.dumps(claim)),
            )

    def get_claim(self, claim_id: str) -> dict[str, Any] | None:
        with self._connection() as connection:
            row = connection.execute(
                "SELECT claim_json FROM claims WHERE claim_id = ?", (claim_id,)
            ).fetchone()
        return json.loads(row["claim_json"]) if row else None

    def list_claims(self, status: str | None = None) -> list[dict[str, Any]]:
        with self._connection() as connection:
            if status:
                rows = connection.execute(
                    "SELECT claim_json FROM claims WHERE status = ? ORDER BY rowid DESC", (status,)
                ).fetchall()
            else:
                rows = connection.execute(
                    "SELECT claim_json FROM claims ORDER BY rowid DESC"
                ).fetchall()
        return [json.loads(row["claim_json"]) for row in rows]

    def get_policy_history(self, policy_number: str, exclude_claim_id: str | None = None) -> list[dict[str, Any]]:
        history = []
        for claim in self.list_claims():
            if claim.get("policy_number") != policy_number or claim.get("claim_id") == exclude_claim_id:
                continue
            history.append({
                "claim_id": claim.get("claim_id"),
                "loss_type": claim.get("loss_type"),
                "incident_date": claim.get("incident_date"),
                "status": claim.get("status"),
                "requested_amount": claim.get("requested_amount"),
                "risk_score": claim.get("risk_score"),
                "fraud_score": claim.get("fraud_score"),
                "review_flags": claim.get("adjudication", {}).get("review_flags", []),
                "created_at": claim.get("created_at"),
            })
        return history

    def add_event(self, claim_id: str, event_type: str, actor: str, details: dict[str, Any]) -> dict[str, Any]:
        event = {
            "event_type": event_type,
            "actor": actor,
            "created_at": datetime.now(timezone.utc).isoformat(),
            "details": details,
        }
        with self._connection() as connection:
            connection.execute(
                "INSERT INTO audit_events(claim_id, created_at, event_json) VALUES (?, ?, ?)",
                (claim_id, event["created_at"], json.dumps(event)),
            )
        return event

    def get_events(self, claim_id: str) -> list[dict[str, Any]]:
        with self._connection() as connection:
            rows = connection.execute(
                "SELECT event_json FROM audit_events WHERE claim_id = ? ORDER BY event_id",
                (claim_id,),
            ).fetchall()
        return [json.loads(row["event_json"]) for row in rows]

    def save_payment(self, claim_id: str, payment: dict[str, Any]) -> None:
        with self._connection() as connection:
            connection.execute(
                "INSERT INTO payments(claim_id, payment_json) VALUES (?, ?) "
                "ON CONFLICT(claim_id) DO NOTHING",
                (claim_id, json.dumps(payment)),
            )

    def get_payment(self, claim_id: str) -> dict[str, Any] | None:
        with self._connection() as connection:
            row = connection.execute(
                "SELECT payment_json FROM payments WHERE claim_id = ?", (claim_id,)
            ).fetchone()
        return json.loads(row["payment_json"]) if row else None

    def save_photo(self, photo: dict[str, Any]) -> None:
        with self._connection() as connection:
            connection.execute(
                "INSERT INTO claim_photos(photo_id, claim_id, file_name, content_type, size_bytes, storage_path, created_at) "
                "VALUES (?, ?, ?, ?, ?, ?, ?)",
                (
                    photo["photo_id"], photo["claim_id"], photo["file_name"], photo["content_type"],
                    photo["size_bytes"], photo["storage_path"], photo["created_at"],
                ),
            )

    def get_photos(self, claim_id: str) -> list[dict[str, Any]]:
        with self._connection() as connection:
            rows = connection.execute(
                "SELECT photo_id, claim_id, file_name, content_type, size_bytes, created_at "
                "FROM claim_photos WHERE claim_id = ? ORDER BY created_at, photo_id",
                (claim_id,),
            ).fetchall()
        return [dict(row) for row in rows]

    def get_photo(self, claim_id: str, photo_id: str) -> dict[str, Any] | None:
        with self._connection() as connection:
            row = connection.execute(
                "SELECT * FROM claim_photos WHERE claim_id = ? AND photo_id = ?",
                (claim_id, photo_id),
            ).fetchone()
        return dict(row) if row else None

    def save_document(self, document: dict[str, Any]) -> None:
        with self._connection() as connection:
            connection.execute(
                "INSERT INTO claim_documents(document_id, claim_id, file_name, content_type, size_bytes, storage_path, "
                "created_at, extraction_status, document_type, extracted_text, extracted_fields_json) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    document["document_id"], document["claim_id"], document["file_name"],
                    document["content_type"], document["size_bytes"], document["storage_path"],
                    document["created_at"], document["extraction_status"], document["document_type"],
                    document["extracted_text"], json.dumps(document["extracted_fields"]),
                ),
            )

    def get_documents(self, claim_id: str) -> list[dict[str, Any]]:
        with self._connection() as connection:
            rows = connection.execute(
                "SELECT document_id, claim_id, file_name, content_type, size_bytes, created_at, "
                "extraction_status, document_type, extracted_text, extracted_fields_json "
                "FROM claim_documents WHERE claim_id = ? ORDER BY created_at, document_id",
                (claim_id,),
            ).fetchall()
        documents = []
        for row in rows:
            document = dict(row)
            document["extracted_fields"] = json.loads(document.pop("extracted_fields_json"))
            documents.append(document)
        return documents

    def get_document(self, claim_id: str, document_id: str) -> dict[str, Any] | None:
        with self._connection() as connection:
            row = connection.execute(
                "SELECT * FROM claim_documents WHERE claim_id = ? AND document_id = ?",
                (claim_id, document_id),
            ).fetchone()
        if row is None:
            return None
        document = dict(row)
        document["extracted_fields"] = json.loads(document.pop("extracted_fields_json"))
        return document
