"""Append-only persistence for revisioned Phase 6 translation variants.

Variant payloads are immutable per ``(variant_id, revision)``. Workflow status
changes are separate append-only events so approval history remains auditable.
"""

from __future__ import annotations

import json
import os
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .translations import TRANSLATION_STATUSES, TranslationVariant


_INITIAL_STATUS = "generated"
_ALLOWED_TRANSITIONS = {
    "generated": {"reviewed", "rejected"},
    "reviewed": {"approved", "rejected"},
    "approved": {"superseded"},
    "rejected": set(),
    "superseded": set(),
}


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


class TranslationVariantStore:
    def __init__(self, database: str | Path | None = None) -> None:
        if database is None:
            storage = Path(os.getenv("STORAGE_DIR", ".storage"))
            storage.mkdir(parents=True, exist_ok=True)
            database = storage / "phase6-translations.sqlite3"
        self.database = Path(database)
        self.database.parent.mkdir(parents=True, exist_ok=True)
        self._init_schema()

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.database)
        connection.row_factory = sqlite3.Row
        return connection

    def _init_schema(self) -> None:
        with self._connect() as connection:
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS translation_variants (
                    variant_id TEXT NOT NULL,
                    revision INTEGER NOT NULL,
                    content_object_id TEXT NOT NULL,
                    canonical_revision INTEGER NOT NULL,
                    target_language TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    created_by TEXT NOT NULL,
                    payload_json TEXT NOT NULL,
                    PRIMARY KEY (variant_id, revision)
                )
                """
            )
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS translation_status_events (
                    event_id INTEGER PRIMARY KEY AUTOINCREMENT,
                    variant_id TEXT NOT NULL,
                    revision INTEGER NOT NULL,
                    status TEXT NOT NULL,
                    changed_at TEXT NOT NULL,
                    changed_by TEXT NOT NULL,
                    comment TEXT NOT NULL DEFAULT '',
                    FOREIGN KEY (variant_id, revision)
                        REFERENCES translation_variants(variant_id, revision)
                )
                """
            )
            connection.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_translation_lookup
                ON translation_variants(content_object_id, canonical_revision, target_language)
                """
            )
            connection.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_translation_status_history
                ON translation_status_events(variant_id, revision, event_id)
                """
            )

    def add_variant(self, variant: TranslationVariant, *, created_by: str) -> dict[str, Any]:
        if variant.revision < 1:
            raise ValueError("Translation revision must be positive")
        if variant.canonical_revision < 1:
            raise ValueError("Canonical revision must be positive")
        if not variant.id.strip() or not variant.content_object_id.strip() or not variant.target_language.strip():
            raise ValueError("variant id, content_object_id and target_language are required")
        if variant.status != _INITIAL_STATUS:
            raise ValueError("New translation variants must start with status 'generated'")
        created_by = created_by.strip()
        if not created_by:
            raise ValueError("created_by is required")

        payload = variant.to_dict()
        payload["status"] = _INITIAL_STATUS
        payload["created_by"] = created_by
        payload["created_at"] = payload.get("created_at") or _now()
        try:
            with self._connect() as connection:
                connection.execute(
                    """
                    INSERT INTO translation_variants (
                        variant_id, revision, content_object_id, canonical_revision,
                        target_language, created_at, created_by, payload_json
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        variant.id,
                        variant.revision,
                        variant.content_object_id,
                        variant.canonical_revision,
                        variant.target_language,
                        payload["created_at"],
                        created_by,
                        json.dumps(payload, ensure_ascii=False, sort_keys=True),
                    ),
                )
                connection.execute(
                    """
                    INSERT INTO translation_status_events (
                        variant_id, revision, status, changed_at, changed_by, comment
                    ) VALUES (?, ?, ?, ?, ?, '')
                    """,
                    (variant.id, variant.revision, _INITIAL_STATUS, payload["created_at"], created_by),
                )
        except sqlite3.IntegrityError as exc:
            raise ValueError(f"Translation variant {variant.id}@{variant.revision} already exists") from exc
        return self.get(variant.id, variant.revision) or payload

    def _status(self, connection: sqlite3.Connection, variant_id: str, revision: int) -> sqlite3.Row | None:
        return connection.execute(
            """
            SELECT status, changed_at, changed_by, comment
            FROM translation_status_events
            WHERE variant_id = ? AND revision = ?
            ORDER BY event_id DESC
            LIMIT 1
            """,
            (variant_id, revision),
        ).fetchone()

    def get(self, variant_id: str, revision: int) -> dict[str, Any] | None:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT payload_json FROM translation_variants WHERE variant_id = ? AND revision = ?",
                (variant_id, revision),
            ).fetchone()
            if row is None:
                return None
            payload = json.loads(row["payload_json"])
            status = self._status(connection, variant_id, revision)
        if status:
            payload["status"] = status["status"]
            payload["status_changed_at"] = status["changed_at"]
            payload["status_changed_by"] = status["changed_by"]
            payload["status_comment"] = status["comment"]
        return payload

    def list(
        self,
        *,
        content_object_id: str = "",
        canonical_revision: int | None = None,
        target_language: str = "",
        status: str = "",
    ) -> list[dict[str, Any]]:
        clauses: list[str] = []
        params: list[Any] = []
        if content_object_id:
            clauses.append("content_object_id = ?")
            params.append(content_object_id)
        if canonical_revision is not None:
            clauses.append("canonical_revision = ?")
            params.append(canonical_revision)
        if target_language:
            clauses.append("target_language = ?")
            params.append(target_language)
        sql = "SELECT variant_id, revision FROM translation_variants"
        if clauses:
            sql += " WHERE " + " AND ".join(clauses)
        sql += " ORDER BY content_object_id, canonical_revision, target_language, variant_id, revision"
        with self._connect() as connection:
            keys = connection.execute(sql, params).fetchall()
        rows = [self.get(row["variant_id"], row["revision"]) for row in keys]
        materialized = [row for row in rows if row is not None]
        if status:
            materialized = [row for row in materialized if row.get("status") == status]
        return materialized

    def history(self, variant_id: str, revision: int) -> list[dict[str, Any]]:
        with self._connect() as connection:
            rows = connection.execute(
                """
                SELECT event_id, status, changed_at, changed_by, comment
                FROM translation_status_events
                WHERE variant_id = ? AND revision = ?
                ORDER BY event_id ASC
                """,
                (variant_id, revision),
            ).fetchall()
        return [dict(row) for row in rows]

    def transition(
        self,
        variant_id: str,
        revision: int,
        *,
        status: str,
        changed_by: str,
        comment: str = "",
    ) -> dict[str, Any]:
        if status not in TRANSLATION_STATUSES:
            raise ValueError(f"Unsupported translation status {status!r}")
        current = self.get(variant_id, revision)
        if current is None:
            raise ValueError(f"Translation variant {variant_id}@{revision} not found")
        current_status = str(current.get("status", ""))
        if status not in _ALLOWED_TRANSITIONS.get(current_status, set()):
            raise ValueError(f"Invalid translation status transition {current_status!r} -> {status!r}")
        changed_by = changed_by.strip()
        if not changed_by:
            raise ValueError("changed_by is required")
        if status in {"rejected", "superseded"} and not comment.strip():
            raise ValueError(f"Comment is required when marking a translation {status}")
        with self._connect() as connection:
            connection.execute(
                """
                INSERT INTO translation_status_events (
                    variant_id, revision, status, changed_at, changed_by, comment
                ) VALUES (?, ?, ?, ?, ?, ?)
                """,
                (variant_id, revision, status, _now(), changed_by, comment.strip()),
            )
        return self.get(variant_id, revision) or current
