"""Immutable trusted configuration parameter revisions for Phase 6 releases."""

from __future__ import annotations

import hashlib
import json
import os
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .configuration import ConfigurationCatalog, ConfigurationParameter


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _canonical_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _checksum(value: Any) -> str:
    return hashlib.sha256(_canonical_json(value).encode("utf-8")).hexdigest()


class ConfigurationParameterStore:
    def __init__(self, database: str | Path | None = None) -> None:
        if database is None:
            storage = Path(os.getenv("STORAGE_DIR", ".storage"))
            storage.mkdir(parents=True, exist_ok=True)
            database = storage / "phase6-configuration.sqlite3"
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
                CREATE TABLE IF NOT EXISTS configuration_parameter_revisions (
                    parameter_id TEXT NOT NULL,
                    revision INTEGER NOT NULL,
                    payload_json TEXT NOT NULL,
                    payload_checksum TEXT NOT NULL,
                    registered_at TEXT NOT NULL,
                    registered_by TEXT NOT NULL,
                    PRIMARY KEY (parameter_id, revision)
                )
                """
            )

    def add(self, parameter: ConfigurationParameter, *, registered_by: str) -> dict[str, Any]:
        actor = registered_by.strip()
        if not actor:
            raise ValueError("registered_by is required")
        catalog = ConfigurationCatalog()
        errors = catalog.validate_parameter(parameter)
        if errors:
            raise ValueError("; ".join(errors))
        if parameter.status != "approved":
            raise ValueError("Only approved configuration parameter revisions can be registered")
        payload = parameter.to_dict()
        checksum = _checksum(payload)
        registered_at = _now()
        try:
            with self._connect() as connection:
                connection.execute(
                    """
                    INSERT INTO configuration_parameter_revisions (
                        parameter_id, revision, payload_json, payload_checksum,
                        registered_at, registered_by
                    ) VALUES (?, ?, ?, ?, ?, ?)
                    """,
                    (
                        parameter.parameter_id,
                        parameter.revision,
                        _canonical_json(payload),
                        checksum,
                        registered_at,
                        actor,
                    ),
                )
        except sqlite3.IntegrityError as exc:
            raise ValueError(
                f"Configuration parameter {parameter.parameter_id}@{parameter.revision} already exists"
            ) from exc
        return self.get(parameter.parameter_id, parameter.revision) or {}

    def get(self, parameter_id: str, revision: int) -> dict[str, Any] | None:
        with self._connect() as connection:
            row = connection.execute(
                """
                SELECT parameter_id, revision, payload_json, payload_checksum,
                       registered_at, registered_by
                FROM configuration_parameter_revisions
                WHERE parameter_id = ? AND revision = ?
                """,
                (parameter_id, revision),
            ).fetchone()
        if row is None:
            return None
        payload = json.loads(row["payload_json"])
        if _checksum(payload) != row["payload_checksum"]:
            raise ValueError(
                f"Configuration parameter {parameter_id}@{revision} failed checksum verification"
            )
        return {
            "parameter_id": row["parameter_id"],
            "revision": row["revision"],
            "parameter": payload,
            "payload_checksum": row["payload_checksum"],
            "registered_at": row["registered_at"],
            "registered_by": row["registered_by"],
        }

    def list(self) -> list[dict[str, Any]]:
        with self._connect() as connection:
            keys = connection.execute(
                "SELECT parameter_id, revision FROM configuration_parameter_revisions ORDER BY parameter_id, revision"
            ).fetchall()
        return [
            item
            for item in (self.get(row["parameter_id"], row["revision"]) for row in keys)
            if item is not None
        ]
