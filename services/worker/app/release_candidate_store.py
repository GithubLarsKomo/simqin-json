"""Immutable server-side release candidates for four-eyes IFU publication.

Candidate payloads are checksum protected and every lifecycle event is linked into
an append-only SHA-256 audit chain. Existing SQLite databases are migrated and
backfilled deterministically on startup.
"""

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


def _event_checksum(
    *,
    candidate_id: str,
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
            "candidate_id": candidate_id,
            "payload_checksum": payload_checksum,
            "sequence_no": sequence_no,
            "status": status,
            "changed_at": changed_at,
            "changed_by": changed_by,
            "comment": comment,
            "previous_event_checksum": previous_event_checksum,
        }
    )


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
        connection.execute("PRAGMA foreign_keys = ON")
        return connection

    @staticmethod
    def _columns(connection: sqlite3.Connection, table: str) -> set[str]:
        return {str(row["name"]) for row in connection.execute(f"PRAGMA table_info({table})")}

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
                    sequence_no INTEGER,
                    status TEXT NOT NULL,
                    changed_at TEXT NOT NULL,
                    changed_by TEXT NOT NULL,
                    comment TEXT NOT NULL DEFAULT '',
                    previous_event_checksum TEXT,
                    event_checksum TEXT,
                    FOREIGN KEY (candidate_id) REFERENCES release_candidates(candidate_id)
                )
                """
            )
            columns = self._columns(connection, "release_candidate_events")
            for name, sql_type in (
                ("sequence_no", "INTEGER"),
                ("previous_event_checksum", "TEXT"),
                ("event_checksum", "TEXT"),
            ):
                if name not in columns:
                    connection.execute(f"ALTER TABLE release_candidate_events ADD COLUMN {name} {sql_type}")
            self._backfill_event_chain(connection)
            connection.execute(
                "CREATE UNIQUE INDEX IF NOT EXISTS idx_release_candidate_event_sequence "
                "ON release_candidate_events(candidate_id, sequence_no)"
            )

    def _backfill_event_chain(self, connection: sqlite3.Connection) -> None:
        candidates = connection.execute(
            "SELECT candidate_id, payload_checksum FROM release_candidates ORDER BY candidate_id"
        ).fetchall()
        for candidate in candidates:
            rows = connection.execute(
                """
                SELECT event_id, sequence_no, status, changed_at, changed_by, comment,
                       previous_event_checksum, event_checksum
                FROM release_candidate_events
                WHERE candidate_id = ? ORDER BY event_id
                """,
                (candidate["candidate_id"],),
            ).fetchall()
            if not rows:
                continue

            # Only a completely unchained history is a legacy history. Never
            # recalculate an already chained or partially chained history:
            # inconsistencies must remain visible to _verified_history().
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
                    candidate_id=candidate["candidate_id"],
                    payload_checksum=candidate["payload_checksum"],
                    sequence_no=sequence_no,
                    status=row["status"],
                    changed_at=row["changed_at"],
                    changed_by=row["changed_by"],
                    comment=row["comment"],
                    previous_event_checksum=previous,
                )
                connection.execute(
                    """
                    UPDATE release_candidate_events
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
        candidate_id: str,
        payload_checksum: str,
        status: str,
        changed_by: str,
        comment: str = "",
        changed_at: str | None = None,
    ) -> None:
        previous = connection.execute(
            """
            SELECT sequence_no, event_checksum
            FROM release_candidate_events
            WHERE candidate_id = ? ORDER BY sequence_no DESC LIMIT 1
            """,
            (candidate_id,),
        ).fetchone()
        sequence_no = (int(previous["sequence_no"]) + 1) if previous else 1
        previous_checksum = str(previous["event_checksum"] or "") if previous else ""
        timestamp = changed_at or _now()
        event_checksum = _event_checksum(
            candidate_id=candidate_id,
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
            INSERT INTO release_candidate_events (
                candidate_id, sequence_no, status, changed_at, changed_by, comment,
                previous_event_checksum, event_checksum
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                candidate_id,
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
        candidate_id: str,
        payload_checksum: str,
    ) -> list[dict[str, Any]]:
        rows = connection.execute(
            """
            SELECT event_id, sequence_no, status, changed_at, changed_by, comment,
                   previous_event_checksum, event_checksum
            FROM release_candidate_events
            WHERE candidate_id = ? ORDER BY sequence_no
            """,
            (candidate_id,),
        ).fetchall()
        previous = ""
        history: list[dict[str, Any]] = []
        for expected_sequence, row in enumerate(rows, start=1):
            if row["sequence_no"] != expected_sequence:
                raise ValueError(
                    f"Release candidate {candidate_id} audit sequence is invalid at event {row['event_id']}"
                )
            if str(row["previous_event_checksum"] or "") != previous:
                raise ValueError(
                    f"Release candidate {candidate_id} audit chain is broken at sequence {expected_sequence}"
                )
            expected_checksum = _event_checksum(
                candidate_id=candidate_id,
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
                    f"Release candidate {candidate_id} audit event {expected_sequence} failed checksum verification"
                )
            item = dict(row)
            history.append(item)
            previous = expected_checksum
        if not history:
            raise ValueError(f"Release candidate {candidate_id} has no audit history")
        return history

    def add(self, candidate_id: str, payload: dict[str, Any], *, created_by: str) -> dict[str, Any]:
        candidate_id = candidate_id.strip()
        created_by = created_by.strip()
        product_id = str(payload.get("product_id", "")).strip()
        language = str(payload.get("language", "")).strip()
        release_id = str(payload.get("release_id", "")).strip()
        version = payload.get("version")
        if not candidate_id or not created_by or not product_id or not language or not release_id:
            raise ValueError("candidate_id, created_by, product_id, language and release_id are required")
        if not isinstance(version, int) or version < 1:
            raise ValueError("release candidate version must be a positive integer")
        frozen = dict(payload)
        frozen.pop("candidate_id", None)
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
                self._append_event(
                    connection,
                    candidate_id=candidate_id,
                    payload_checksum=checksum,
                    status="candidate",
                    changed_by=created_by,
                    changed_at=created_at,
                )
        except sqlite3.IntegrityError as exc:
            raise ValueError(f"Release candidate {candidate_id} already exists") from exc
        return self.get(candidate_id) or {}

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
            history = self._verified_history(
                connection,
                candidate_id=candidate_id,
                payload_checksum=row["payload_checksum"],
            )
            status = history[-1]
        return {
            "candidate_id": row["candidate_id"],
            "product_id": row["product_id"],
            "language": row["language"],
            "release_id": payload.get("release_id", ""),
            "version": payload.get("version", 0),
            "payload": payload,
            "payload_checksum": row["payload_checksum"],
            "created_at": row["created_at"],
            "created_by": row["created_by"],
            "status": status["status"],
            "status_changed_at": status["changed_at"],
            "status_changed_by": status["changed_by"],
            "status_comment": status["comment"],
            "audit_sequence": status["sequence_no"],
            "audit_checksum": status["event_checksum"],
        }

    def list(self) -> list[dict[str, Any]]:
        with self._connect() as connection:
            ids = [
                row["candidate_id"]
                for row in connection.execute(
                    "SELECT candidate_id FROM release_candidates ORDER BY created_at, candidate_id"
                )
            ]
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
        actor = changed_by.strip()
        if not actor:
            raise ValueError("changed_by is required")
        with self._connect() as connection:
            self._append_event(
                connection,
                candidate_id=candidate_id,
                payload_checksum=current["payload_checksum"],
                status=status,
                changed_by=actor,
                comment=comment.strip(),
            )
        return self.get(candidate_id) or current

    def history(self, candidate_id: str) -> list[dict[str, Any]]:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT payload_checksum FROM release_candidates WHERE candidate_id = ?",
                (candidate_id,),
            ).fetchone()
            if row is None:
                return []
            return self._verified_history(
                connection,
                candidate_id=candidate_id,
                payload_checksum=row["payload_checksum"],
            )
