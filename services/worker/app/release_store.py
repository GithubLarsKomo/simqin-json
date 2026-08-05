"""Append-only SQLite store for immutable IFU language releases."""

from __future__ import annotations

import json
import os
import sqlite3
from pathlib import Path
from typing import Any

from .ifu_release import IFULanguageReleaseSnapshot


class ReleaseStore:
    def __init__(self, database: str | Path | None = None) -> None:
        if database is None:
            storage = Path(os.getenv("STORAGE_DIR", ".storage"))
            storage.mkdir(parents=True, exist_ok=True)
            database = storage / "phase6-releases.sqlite3"
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
                CREATE TABLE IF NOT EXISTS ifu_language_releases (
                    release_id TEXT PRIMARY KEY,
                    product_id TEXT NOT NULL,
                    language TEXT NOT NULL,
                    version INTEGER NOT NULL,
                    release_checksum TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    created_by TEXT NOT NULL,
                    payload_json TEXT NOT NULL
                )
                """
            )
            connection.execute(
                "CREATE UNIQUE INDEX IF NOT EXISTS ux_release_product_language_version "
                "ON ifu_language_releases(product_id, language, version)"
            )

    def add(self, release: IFULanguageReleaseSnapshot) -> dict[str, Any]:
        payload = release.to_dict()
        if not release.verify_checksum():
            raise ValueError("Release checksum is invalid")
        try:
            with self._connect() as connection:
                connection.execute(
                    "INSERT INTO ifu_language_releases "
                    "(release_id, product_id, language, version, release_checksum, created_at, created_by, payload_json) "
                    "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                    (
                        release.release_id,
                        release.product_id,
                        release.language,
                        release.version,
                        release.release_checksum,
                        release.created_at,
                        release.created_by,
                        json.dumps(payload, ensure_ascii=False, sort_keys=True),
                    ),
                )
        except sqlite3.IntegrityError as exc:
            raise ValueError("Release id or product/language/version already exists") from exc
        return payload

    def get(self, release_id: str) -> dict[str, Any] | None:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT payload_json FROM ifu_language_releases WHERE release_id = ?",
                (release_id,),
            ).fetchone()
        return json.loads(row["payload_json"]) if row else None

    def list(self) -> list[dict[str, Any]]:
        with self._connect() as connection:
            rows = connection.execute(
                "SELECT payload_json FROM ifu_language_releases ORDER BY product_id, language, version"
            ).fetchall()
        return [json.loads(row["payload_json"]) for row in rows]
