"""Minimal persistent review-decision store for Phase 6.

The store is intentionally append-only: review decisions are never updated or
deleted. SQLite keeps the beta deployment self-contained while providing a
real persistence boundary for controlled evaluation.
"""

from __future__ import annotations

import os
import sqlite3
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

REVIEW_DECISIONS = {"approved", "rejected", "changes_requested"}


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def default_database_path() -> Path:
    storage_dir = Path(os.getenv("STORAGE_DIR", ".storage"))
    return storage_dir / "phase6-reviews.sqlite3"


class ReviewDecisionStore:
    def __init__(self, database_path: str | Path | None = None) -> None:
        self.database_path = Path(database_path) if database_path else default_database_path()
        self.database_path.parent.mkdir(parents=True, exist_ok=True)
        self._initialize()

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.database_path)
        connection.row_factory = sqlite3.Row
        return connection

    def _initialize(self) -> None:
        with self._connect() as connection:
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS phase6_review_decisions (
                    decision_id TEXT PRIMARY KEY,
                    migration_id TEXT NOT NULL,
                    created_by TEXT NOT NULL,
                    reviewer TEXT NOT NULL,
                    decision TEXT NOT NULL,
                    comment TEXT NOT NULL DEFAULT '',
                    decided_at TEXT NOT NULL
                )
                """
            )
            connection.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_phase6_review_migration
                ON phase6_review_decisions (migration_id, decided_at, decision_id)
                """
            )

    def add_decision(
        self,
        *,
        migration_id: str,
        created_by: str,
        reviewer: str,
        decision: str,
        comment: str = "",
    ) -> dict[str, Any]:
        migration_id = migration_id.strip()
        created_by = created_by.strip()
        reviewer = reviewer.strip()
        decision = decision.strip()
        comment = comment.strip()

        if not migration_id:
            raise ValueError("migration_id is required")
        if not created_by:
            raise ValueError("created_by is required")
        if not reviewer:
            raise ValueError("reviewer is required")
        if reviewer == created_by:
            raise ValueError("Four-eyes rule violation: reviewer must differ from creator")
        if decision not in REVIEW_DECISIONS:
            raise ValueError(f"Unsupported review decision: {decision}")
        if decision in {"rejected", "changes_requested"} and not comment:
            raise ValueError("Comment is required for rejected or changes_requested decisions")

        row = {
            "decision_id": str(uuid.uuid4()),
            "migration_id": migration_id,
            "created_by": created_by,
            "reviewer": reviewer,
            "decision": decision,
            "comment": comment,
            "decided_at": _now(),
        }
        with self._connect() as connection:
            connection.execute(
                """
                INSERT INTO phase6_review_decisions (
                    decision_id, migration_id, created_by, reviewer,
                    decision, comment, decided_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    row["decision_id"],
                    row["migration_id"],
                    row["created_by"],
                    row["reviewer"],
                    row["decision"],
                    row["comment"],
                    row["decided_at"],
                ),
            )
        return row

    def list_decisions(self, migration_id: str) -> list[dict[str, Any]]:
        migration_id = migration_id.strip()
        if not migration_id:
            raise ValueError("migration_id is required")
        with self._connect() as connection:
            rows = connection.execute(
                """
                SELECT decision_id, migration_id, created_by, reviewer,
                       decision, comment, decided_at
                FROM phase6_review_decisions
                WHERE migration_id = ?
                ORDER BY rowid ASC
                """,
                (migration_id,),
            ).fetchall()
        return [dict(row) for row in rows]
