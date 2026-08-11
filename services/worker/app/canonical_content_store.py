"""Immutable approved canonical source snapshots for translation control.

The store is deliberately narrow: it records approved ContentObject revisions as
trusted translation source material. A snapshot cannot be overwritten. The
payload checksum is verified on every read so translations are never reviewed
against silently modified source text.
"""

from __future__ import annotations

import hashlib
import json
import os
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .content_objects import ContentObjectRevision
from .content_segment import ContentSegment, validate_segments


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _canonical_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _checksum(payload: dict[str, Any]) -> str:
    return hashlib.sha256(_canonical_json(payload).encode("utf-8")).hexdigest()


def _validate_source_revision(revision: ContentObjectRevision) -> None:
    try:
        segments = [
            item if isinstance(item, ContentSegment) else ContentSegment.from_dict(item)
            for item in revision.sentence_segments
        ]
    except (TypeError, ValueError, KeyError) as exc:
        raise ValueError(f"Invalid canonical source segment: {exc}") from exc

    errors = validate_segments(segments)
    for index, segment in enumerate(segments):
        if segment.source_revision != revision.revision:
            errors.append(
                f"segments[{index}]: source_revision {segment.source_revision} does not match canonical revision {revision.revision}"
            )
        if not segment.source_text:
            errors.append(f"segments[{index}]: source_text is required")

    cursor = 0
    for index, segment in sorted(enumerate(segments), key=lambda item: (item[1].order, item[0])):
        position = revision.canonical_content.find(segment.source_text, cursor)
        if position < 0:
            errors.append(
                f"segments[{index}]: source_text is not present in canonical_content in deterministic order"
            )
            continue
        cursor = position + len(segment.source_text)

    if errors:
        raise ValueError("Invalid canonical source snapshot: " + "; ".join(errors))


class CanonicalContentStore:
    def __init__(self, database: str | Path | None = None) -> None:
        if database is None:
            storage = Path(os.getenv("STORAGE_DIR", ".storage"))
            storage.mkdir(parents=True, exist_ok=True)
            database = storage / "phase6-canonical-content.sqlite3"
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
                CREATE TABLE IF NOT EXISTS canonical_content_revisions (
                    object_id TEXT NOT NULL,
                    revision INTEGER NOT NULL,
                    canonical_language TEXT NOT NULL,
                    approval_status TEXT NOT NULL,
                    payload_json TEXT NOT NULL,
                    payload_checksum TEXT NOT NULL,
                    registered_at TEXT NOT NULL,
                    registered_by TEXT NOT NULL,
                    PRIMARY KEY (object_id, revision)
                )
                """
            )

    def add(
        self,
        *,
        object_id: str,
        canonical_language: str,
        revision: ContentObjectRevision,
        registered_by: str,
    ) -> dict[str, Any]:
        object_id = object_id.strip()
        canonical_language = canonical_language.strip()
        registered_by = registered_by.strip()
        if not object_id or not canonical_language or not registered_by:
            raise ValueError("object_id, canonical_language and registered_by are required")
        if revision.object_id != object_id:
            raise ValueError("Content revision object_id does not match snapshot object_id")
        if revision.revision < 1:
            raise ValueError("Canonical revision must be positive")
        if revision.approval_status != "approved":
            raise ValueError("Only approved canonical revisions may be registered")
        if not revision.canonical_content.strip():
            raise ValueError("Approved canonical revision must contain canonical_content")
        if not revision.sentence_segments:
            raise ValueError("Approved canonical revision must contain sentence_segments")
        _validate_source_revision(revision)

        payload = revision.to_dict()
        checksum = _checksum(payload)
        registered_at = _now()
        try:
            with self._connect() as connection:
                connection.execute(
                    """
                    INSERT INTO canonical_content_revisions (
                        object_id, revision, canonical_language, approval_status,
                        payload_json, payload_checksum, registered_at, registered_by
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        object_id,
                        revision.revision,
                        canonical_language,
                        revision.approval_status,
                        _canonical_json(payload),
                        checksum,
                        registered_at,
                        registered_by,
                    ),
                )
        except sqlite3.IntegrityError as exc:
            raise ValueError(f"Canonical source {object_id}@{revision.revision} already exists") from exc
        return self.get(object_id, revision.revision) or {}

    def get(self, object_id: str, revision: int) -> dict[str, Any] | None:
        with self._connect() as connection:
            row = connection.execute(
                """
                SELECT object_id, revision, canonical_language, approval_status,
                       payload_json, payload_checksum, registered_at, registered_by
                FROM canonical_content_revisions
                WHERE object_id = ? AND revision = ?
                """,
                (object_id, revision),
            ).fetchone()
        if row is None:
            return None
        payload = json.loads(row["payload_json"])
        actual = _checksum(payload)
        if actual != row["payload_checksum"]:
            raise ValueError(f"Canonical source {object_id}@{revision} failed checksum verification")
        return {
            "object_id": row["object_id"],
            "revision": row["revision"],
            "canonical_language": row["canonical_language"],
            "approval_status": row["approval_status"],
            "revision_payload": payload,
            "payload_checksum": row["payload_checksum"],
            "registered_at": row["registered_at"],
            "registered_by": row["registered_by"],
        }

    def list(self) -> list[dict[str, Any]]:
        with self._connect() as connection:
            keys = connection.execute(
                "SELECT object_id, revision FROM canonical_content_revisions ORDER BY object_id, revision"
            ).fetchall()
        return [item for item in (self.get(row["object_id"], row["revision"]) for row in keys) if item is not None]
