"""Immutable trusted terminology profile revisions for Phase 6 releases."""

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


class TerminologyProfileStore:
    def __init__(self, database: str | Path | None = None) -> None:
        if database is None:
            storage = Path(os.getenv("STORAGE_DIR", ".storage"))
            storage.mkdir(parents=True, exist_ok=True)
            database = storage / "phase6-terminology-profiles.sqlite3"
        self.database = Path(database)
        self.database.parent.mkdir(parents=True, exist_ok=True)
        with self._connect() as connection:
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS terminology_profiles (
                    profile_revision TEXT PRIMARY KEY,
                    payload_json TEXT NOT NULL,
                    payload_checksum TEXT NOT NULL,
                    registered_at TEXT NOT NULL,
                    registered_by TEXT NOT NULL
                )
                """
            )

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.database)
        connection.row_factory = sqlite3.Row
        return connection

    def add(self, profile_revision: str, profile: dict[str, Any], *, registered_by: str) -> dict[str, Any]:
        revision = profile_revision.strip()
        actor = registered_by.strip()
        if not revision or not actor:
            raise ValueError("profile_revision and registered_by are required")
        frozen = dict(profile)
        status = str(frozen.get("status", "")).strip().lower()
        if status != "approved":
            raise ValueError("Only approved terminology profiles may be registered")
        checksum = _checksum(frozen)
        registered_at = _now()
        try:
            with self._connect() as connection:
                connection.execute(
                    """
                    INSERT INTO terminology_profiles (
                        profile_revision, payload_json, payload_checksum, registered_at, registered_by
                    ) VALUES (?, ?, ?, ?, ?)
                    """,
                    (revision, _canonical_json(frozen), checksum, registered_at, actor),
                )
        except sqlite3.IntegrityError as exc:
            raise ValueError(f"Terminology profile {revision} already exists") from exc
        return self.get(revision) or {}

    def get(self, profile_revision: str) -> dict[str, Any] | None:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT * FROM terminology_profiles WHERE profile_revision = ?",
                (profile_revision,),
            ).fetchone()
        if row is None:
            return None
        profile = json.loads(row["payload_json"])
        if _checksum(profile) != row["payload_checksum"]:
            raise ValueError(f"Terminology profile {profile_revision} failed checksum verification")
        return {
            "profile_revision": row["profile_revision"],
            "profile": profile,
            "payload_checksum": row["payload_checksum"],
            "registered_at": row["registered_at"],
            "registered_by": row["registered_by"],
        }

    def list(self) -> list[dict[str, Any]]:
        with self._connect() as connection:
            revisions = [row["profile_revision"] for row in connection.execute(
                "SELECT profile_revision FROM terminology_profiles ORDER BY profile_revision"
            )]
        return [item for item in (self.get(revision) for revision in revisions) if item is not None]
