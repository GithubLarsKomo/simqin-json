"""Immutable trusted Phase 6 multiplicity rulesets."""

from __future__ import annotations

import hashlib
import json
import os
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .content_objects import MULTIPLICITY_MODES, MultiplicityRule


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _canonical_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _checksum(value: Any) -> str:
    return hashlib.sha256(_canonical_json(value).encode("utf-8")).hexdigest()


def _validated_rules(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    normalized: list[dict[str, Any]] = []
    seen: set[str] = set()
    for raw in rows:
        rule = MultiplicityRule.from_dict(raw)
        if not rule.object_id.strip():
            raise ValueError("Multiplicity rule object_id is required")
        if rule.object_id in seen:
            raise ValueError(f"Duplicate multiplicity rule for {rule.object_id}")
        seen.add(rule.object_id)
        if rule.mode not in MULTIPLICITY_MODES:
            raise ValueError(f"Invalid multiplicity mode {rule.mode!r}")
        if rule.revision < 1:
            raise ValueError("Multiplicity rule revision must be positive")
        if rule.status != "approved":
            raise ValueError("Trusted multiplicity rules must be approved")
        if rule.max_occurrences < 1:
            raise ValueError("max_occurrences must be positive")
        if rule.mode == "single" and rule.max_occurrences != 1:
            raise ValueError("single multiplicity rules must have max_occurrences = 1")
        normalized.append(rule.to_dict())
    normalized.sort(key=lambda row: row["object_id"])
    return normalized


class RulesetStore:
    def __init__(self, database: str | Path | None = None) -> None:
        if database is None:
            storage = Path(os.getenv("STORAGE_DIR", ".storage"))
            storage.mkdir(parents=True, exist_ok=True)
            database = storage / "phase6-rulesets.sqlite3"
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
                CREATE TABLE IF NOT EXISTS rulesets (
                    ruleset_revision TEXT PRIMARY KEY,
                    payload_json TEXT NOT NULL,
                    payload_checksum TEXT NOT NULL,
                    registered_at TEXT NOT NULL,
                    registered_by TEXT NOT NULL
                )
                """
            )

    def add(self, ruleset_revision: str, rules: list[dict[str, Any]], *, registered_by: str) -> dict[str, Any]:
        revision = ruleset_revision.strip()
        actor = registered_by.strip()
        if not revision:
            raise ValueError("ruleset_revision is required")
        if not actor:
            raise ValueError("registered_by is required")
        payload = {"rules": _validated_rules(rules)}
        checksum = _checksum(payload)
        registered_at = _now()
        try:
            with self._connect() as connection:
                connection.execute(
                    """
                    INSERT INTO rulesets (
                        ruleset_revision, payload_json, payload_checksum,
                        registered_at, registered_by
                    ) VALUES (?, ?, ?, ?, ?)
                    """,
                    (revision, _canonical_json(payload), checksum, registered_at, actor),
                )
        except sqlite3.IntegrityError as exc:
            raise ValueError(f"Ruleset {revision} already exists") from exc
        return self.get(revision) or {}

    def get(self, ruleset_revision: str) -> dict[str, Any] | None:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT * FROM rulesets WHERE ruleset_revision = ?",
                (ruleset_revision,),
            ).fetchone()
        if row is None:
            return None
        payload = json.loads(row["payload_json"])
        if _checksum(payload) != row["payload_checksum"]:
            raise ValueError(f"Ruleset {ruleset_revision} failed checksum verification")
        return {
            "ruleset_revision": row["ruleset_revision"],
            "rules": list(payload.get("rules", [])),
            "payload_checksum": row["payload_checksum"],
            "registered_at": row["registered_at"],
            "registered_by": row["registered_by"],
        }

    def list(self) -> list[dict[str, Any]]:
        with self._connect() as connection:
            revisions = [row["ruleset_revision"] for row in connection.execute(
                "SELECT ruleset_revision FROM rulesets ORDER BY registered_at, ruleset_revision"
            )]
        return [item for item in (self.get(revision) for revision in revisions) if item is not None]
