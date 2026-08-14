"""Immutable persistence for revisioned Phase 6 translation variants.

Variant payloads are checksum protected. Workflow status changes are append-only
and linked into a SHA-256 audit chain. Existing SQLite databases are migrated
without re-sealing already chained or partially chained histories.
"""

from __future__ import annotations

import hashlib
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


def _canonical_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _checksum(value: Any) -> str:
    return hashlib.sha256(_canonical_json(value).encode("utf-8")).hexdigest()


def _event_checksum(
    *,
    variant_id: str,
    revision: int,
    payload_checksum: str,
    sequence_no: int,
    status: str,
    changed_at: str,
    changed_by: str,
    comment: str,
    previous_event_checksum: str,
) -> str:
    return _checksum(
        {
            "variant_id": variant_id,
            "revision": revision,
            "payload_checksum": payload_checksum,
            "sequence_no": sequence_no,
            "status": status,
            "changed_at": changed_at,
            "changed_by": changed_by,
            "comment": comment,
            "previous_event_checksum": previous_event_checksum,
        }
    )


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
        connection.execute("PRAGMA foreign_keys = ON")
        return connection

    @staticmethod
    def _columns(connection: sqlite3.Connection, table: str) -> set[str]:
        return {str(row["name"]) for row in connection.execute(f"PRAGMA table_info({table})")}

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
                    payload_checksum TEXT,
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
                    sequence_no INTEGER,
                    status TEXT NOT NULL,
                    changed_at TEXT NOT NULL,
                    changed_by TEXT NOT NULL,
                    comment TEXT NOT NULL DEFAULT '',
                    previous_event_checksum TEXT,
                    event_checksum TEXT,
                    FOREIGN KEY (variant_id, revision)
                        REFERENCES translation_variants(variant_id, revision)
                )
                """
            )
            variant_columns = self._columns(connection, "translation_variants")
            if "payload_checksum" not in variant_columns:
                connection.execute("ALTER TABLE translation_variants ADD COLUMN payload_checksum TEXT")
            event_columns = self._columns(connection, "translation_status_events")
            for name, sql_type in (
                ("sequence_no", "INTEGER"),
                ("previous_event_checksum", "TEXT"),
                ("event_checksum", "TEXT"),
            ):
                if name not in event_columns:
                    connection.execute(f"ALTER TABLE translation_status_events ADD COLUMN {name} {sql_type}")
            self._backfill_payload_checksums(connection)
            self._backfill_event_chains(connection)
            connection.execute(
                "CREATE INDEX IF NOT EXISTS idx_translation_lookup "
                "ON translation_variants(content_object_id, canonical_revision, target_language)"
            )
            connection.execute(
                "CREATE UNIQUE INDEX IF NOT EXISTS idx_translation_status_sequence "
                "ON translation_status_events(variant_id, revision, sequence_no)"
            )

    def _backfill_payload_checksums(self, connection: sqlite3.Connection) -> None:
        rows = connection.execute(
            "SELECT variant_id, revision, payload_json, payload_checksum FROM translation_variants"
        ).fetchall()
        for row in rows:
            if row["payload_checksum"] is not None:
                continue
            payload = json.loads(row["payload_json"])
            connection.execute(
                "UPDATE translation_variants SET payload_checksum = ? WHERE variant_id = ? AND revision = ?",
                (_checksum(payload), row["variant_id"], row["revision"]),
            )

    def _backfill_event_chains(self, connection: sqlite3.Connection) -> None:
        variants = connection.execute(
            "SELECT variant_id, revision, payload_checksum FROM translation_variants ORDER BY variant_id, revision"
        ).fetchall()
        for variant in variants:
            rows = connection.execute(
                """
                SELECT event_id, sequence_no, status, changed_at, changed_by, comment,
                       previous_event_checksum, event_checksum
                FROM translation_status_events
                WHERE variant_id = ? AND revision = ? ORDER BY event_id
                """,
                (variant["variant_id"], variant["revision"]),
            ).fetchall()
            if not rows:
                continue
            is_legacy = all(
                row["sequence_no"] is None
                and row["previous_event_checksum"] is None
                and row["event_checksum"] is None
                for row in rows
            )
            if not is_legacy:
                continue
            previous = ""
            for sequence_no, row in enumerate(rows, start=1):
                checksum = _event_checksum(
                    variant_id=variant["variant_id"],
                    revision=int(variant["revision"]),
                    payload_checksum=str(variant["payload_checksum"]),
                    sequence_no=sequence_no,
                    status=row["status"],
                    changed_at=row["changed_at"],
                    changed_by=row["changed_by"],
                    comment=row["comment"],
                    previous_event_checksum=previous,
                )
                connection.execute(
                    """
                    UPDATE translation_status_events
                    SET sequence_no = ?, previous_event_checksum = ?, event_checksum = ?
                    WHERE event_id = ?
                    """,
                    (sequence_no, previous, checksum, row["event_id"]),
                )
                previous = checksum

    def _append_event(
        self,
        connection: sqlite3.Connection,
        *,
        variant_id: str,
        revision: int,
        payload_checksum: str,
        status: str,
        changed_by: str,
        comment: str = "",
        changed_at: str | None = None,
    ) -> None:
        previous = connection.execute(
            """
            SELECT sequence_no, event_checksum FROM translation_status_events
            WHERE variant_id = ? AND revision = ? ORDER BY sequence_no DESC LIMIT 1
            """,
            (variant_id, revision),
        ).fetchone()
        sequence_no = int(previous["sequence_no"]) + 1 if previous else 1
        previous_checksum = str(previous["event_checksum"] or "") if previous else ""
        timestamp = changed_at or _now()
        event_checksum = _event_checksum(
            variant_id=variant_id,
            revision=revision,
            payload_checksum=payload_checksum,
            sequence_no=sequence_no,
            status=status,
            changed_at=timestamp,
            changed_by=changed_by,
            comment=comment,
            previous_event_checksum=previous_checksum,
        )
        connection.execute(
            """
            INSERT INTO translation_status_events (
                variant_id, revision, sequence_no, status, changed_at, changed_by,
                comment, previous_event_checksum, event_checksum
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                variant_id,
                revision,
                sequence_no,
                status,
                timestamp,
                changed_by,
                comment,
                previous_checksum,
                event_checksum,
            ),
        )

    def _verified_history(
        self,
        connection: sqlite3.Connection,
        *,
        variant_id: str,
        revision: int,
        payload_checksum: str,
    ) -> list[dict[str, Any]]:
        rows = connection.execute(
            """
            SELECT event_id, sequence_no, status, changed_at, changed_by, comment,
                   previous_event_checksum, event_checksum
            FROM translation_status_events
            WHERE variant_id = ? AND revision = ? ORDER BY sequence_no
            """,
            (variant_id, revision),
        ).fetchall()
        previous = ""
        history: list[dict[str, Any]] = []
        for expected_sequence, row in enumerate(rows, start=1):
            if row["sequence_no"] != expected_sequence:
                raise ValueError(
                    f"Translation variant {variant_id}@{revision} audit sequence is invalid at event {row['event_id']}"
                )
            if str(row["previous_event_checksum"] or "") != previous:
                raise ValueError(
                    f"Translation variant {variant_id}@{revision} audit chain is broken at sequence {expected_sequence}"
                )
            expected_checksum = _event_checksum(
                variant_id=variant_id,
                revision=revision,
                payload_checksum=payload_checksum,
                sequence_no=expected_sequence,
                status=row["status"],
                changed_at=row["changed_at"],
                changed_by=row["changed_by"],
                comment=row["comment"],
                previous_event_checksum=previous,
            )
            if row["event_checksum"] != expected_checksum:
                raise ValueError(
                    f"Translation variant {variant_id}@{revision} audit event {expected_sequence} failed checksum verification"
                )
            history.append(dict(row))
            previous = expected_checksum
        if not history:
            raise ValueError(f"Translation variant {variant_id}@{revision} has no audit history")
        return history

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
        payload_checksum = _checksum(payload)
        try:
            with self._connect() as connection:
                connection.execute(
                    """
                    INSERT INTO translation_variants (
                        variant_id, revision, content_object_id, canonical_revision,
                        target_language, created_at, created_by, payload_json, payload_checksum
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        variant.id,
                        variant.revision,
                        variant.content_object_id,
                        variant.canonical_revision,
                        variant.target_language,
                        payload["created_at"],
                        created_by,
                        _canonical_json(payload),
                        payload_checksum,
                    ),
                )
                self._append_event(
                    connection,
                    variant_id=variant.id,
                    revision=variant.revision,
                    payload_checksum=payload_checksum,
                    status=_INITIAL_STATUS,
                    changed_by=created_by,
                    changed_at=payload["created_at"],
                )
        except sqlite3.IntegrityError as exc:
            raise ValueError(f"Translation variant {variant.id}@{variant.revision} already exists") from exc
        return self.get(variant.id, variant.revision) or payload

    def get(self, variant_id: str, revision: int) -> dict[str, Any] | None:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT payload_json, payload_checksum FROM translation_variants WHERE variant_id = ? AND revision = ?",
                (variant_id, revision),
            ).fetchone()
            if row is None:
                return None
            payload = json.loads(row["payload_json"])
            payload_checksum = str(row["payload_checksum"] or "")
            if not payload_checksum or _checksum(payload) != payload_checksum:
                raise ValueError(f"Translation variant {variant_id}@{revision} failed checksum verification")
            history = self._verified_history(
                connection,
                variant_id=variant_id,
                revision=revision,
                payload_checksum=payload_checksum,
            )
            status = history[-1]
        payload["status"] = status["status"]
        payload["status_changed_at"] = status["changed_at"]
        payload["status_changed_by"] = status["changed_by"]
        payload["status_comment"] = status["comment"]
        payload["payload_checksum"] = payload_checksum
        payload["audit_sequence"] = status["sequence_no"]
        payload["audit_checksum"] = status["event_checksum"]
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
            row = connection.execute(
                "SELECT payload_checksum FROM translation_variants WHERE variant_id = ? AND revision = ?",
                (variant_id, revision),
            ).fetchone()
            if row is None:
                return []
            return self._verified_history(
                connection,
                variant_id=variant_id,
                revision=revision,
                payload_checksum=str(row["payload_checksum"] or ""),
            )

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
            self._append_event(
                connection,
                variant_id=variant_id,
                revision=revision,
                payload_checksum=str(current["payload_checksum"]),
                status=status,
                changed_by=changed_by,
                comment=comment.strip(),
            )
        return self.get(variant_id, revision) or current
