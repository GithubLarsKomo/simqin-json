"""Immutable server-side release candidates for four-eyes IFU publication."""

from __future__ import annotations

import hashlib
import json
import os
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _canonical_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _checksum(payload: dict[str, Any]) -> str:
    return hashlib.sha256(_canonical_json(payload).encode("utf-8")).hexdigest()


class ReleaseCandidateStore:
    def __init__(self, database: str | Path | None = None) -> None:
        if database is None:
            storage = Path(os.getenv("STORAGE_DIR", ".storage"))
            storage.mkdir(parents=True, exist_ok=True)
            database = storage / "phase6-release-candidates.sqlite3"
        self.database = Path(database)
        self.database.parent.mkdir(parents=True, exist_ok=True)
        self._initialize()

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.database)
        connection.row_factory = sqlite3.Row
        return connection

    def _initialize(self) -> None:
        with self._connect() as connection:
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS release_candidates (
                    candidate_id TEXT PRIMARY KEY,
                    product_id TEXT NOT NULL,
                    language TEXT NOT NULL,
                    payload_json TEXT NOT NULL,
                    payload_checksum TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    created_by TEXT NOT NULL
                )
                """
            )
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS release_candidate_events (
                    event_id INTEGER PRIMARY KEY AUTOINCREMENT,
                    candidate_id TEXT NOT NULL,
                    status TEXT NOT NULL,
                    changed_at TEXT NOT NULL,
                    changed_by TEXT NOT NULL,
                    comment TEXT NOT NULL DEFAULT '',
                    FOREIGN KEY (candidate_id) REFERENCES release_candidates(candidate_id)
                )
                """
            )

    def add(self, candidate_id: str, payload: dict[str, Any], *, created_by: str) -> dict[str, Any]:
        candidate_id = candidate_id.strip()
        created_by = created_by.strip()
        product_id = str(payload.get("product_id", "")).strip()
        language = str(payload.get("language", "")).strip()
        if not candidate_id or not created_by or not product_id or not language:
            raise ValueError("candidate_id, created_by, product_id and language are required")
        frozen = dict(payload)
        frozen.pop("candidate_id", None)
        frozen.pop("release_id", None)
        frozen.pop("version", None)
        checksum = _checksum(frozen)
        created_at = _now()
        try:
            with self._connect() as connection:
                connection.execute(
                    """
                    INSERT INTO release_candidates (
                        candidate_id, product_id, language, payload_json,
                        payload_checksum, created_at, created_by
                    ) VALUES (?, ?, ?, ?, ?, ?, ?)
                    """,
                    (candidate_id, product_id, language, _canonical_json(frozen), checksum, created_at, created_by),
                )
                connection.execute(
                    """
                    INSERT INTO release_candidate_events (
                        candidate_id, status, changed_at, changed_by, comment
                    ) VALUES (?, 'candidate', ?, ?, '')
                    """,
                    (candidate_id, created_at, created_by),
                )
        except sqlite3.IntegrityError as exc:
            raise ValueError(f"Release candidate {candidate_id} already exists") from exc
        return self.get(candidate_id) or {}

    def _status(self, connection: sqlite3.Connection, candidate_id: str) -> sqlite3.Row | None:
        return connection.execute(
            """
            SELECT status, changed_at, changed_by, comment
            FROM release_candidate_events
            WHERE candidate_id = ? ORDER BY event_id DESC LIMIT 1
            """,
            (candidate_id,),
        ).fetchone()

    def get(self, candidate_id: str) -> dict[str, Any] | None:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT * FROM release_candidates WHERE candidate_id = ?",
                (candidate_id,),
            ).fetchone()
            if row is None:
                return None
            payload = json.loads(row["payload_json"])
            if _checksum(payload) != row["payload_checksum"]:
                raise ValueError(f"Release candidate {candidate_id} failed checksum verification")
            status = self._status(connection, candidate_id)
        return {
            "candidate_id": row["candidate_id"],
            "product_id": row["product_id"],
            "language": row["language"],
            "payload": payload,
            "payload_checksum": row["payload_checksum"],
            "created_at": row["created_at"],
            "created_by": row["created_by"],
            "status": status["status"] if status else "candidate",
            "status_changed_at": status["changed_at"] if status else row["created_at"],
            "status_changed_by": status["changed_by"] if status else row["created_by"],
            "status_comment": status["comment"] if status else "",
        }

    def list(self) -> list[dict[str, Any]]:
        with self._connect() as connection:
            ids = [row["candidate_id"] for row in connection.execute("SELECT candidate_id FROM release_candidates ORDER BY created_at, candidate_id")]
        return [item for item in (self.get(candidate_id) for candidate_id in ids) if item is not None]

    def transition(self, candidate_id: str, *, status: str, changed_by: str, comment: str = "") -> dict[str, Any]:
        current = self.get(candidate_id)
        if current is None:
            raise ValueError(f"Release candidate {candidate_id} not found")
        current_status = current["status"]
        allowed = {
            "candidate": {"approved", "rejected"},
            "approved": {"released"},
            "rejected": set(),
            "released": set(),
        }
        if status not in allowed.get(current_status, set()):
            raise ValueError(f"Invalid release candidate transition {current_status!r} -> {status!r}")
        if status == "rejected" and not comment.strip():
            raise ValueError("Comment is required when rejecting a release candidate")
        with self._connect() as connection:
            connection.execute(
                "INSERT INTO release_candidate_events (candidate_id, status, changed_at, changed_by, comment) VALUES (?, ?, ?, ?, ?)",
                (candidate_id, status, _now(), changed_by.strip(), comment.strip()),
            )
        return self.get(candidate_id) or current

    def history(self, candidate_id: str) -> list[dict[str, Any]]:
        with self._connect() as connection:
            rows = connection.execute(
                "SELECT event_id, status, changed_at, changed_by, comment FROM release_candidate_events WHERE candidate_id = ? ORDER BY event_id",
                (candidate_id,),
            ).fetchall()
        return [dict(row) for row in rows]
