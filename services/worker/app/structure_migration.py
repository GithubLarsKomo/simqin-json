"""Structure migration for sentence segments — four-eyes principle."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _new_id() -> str:
    return str(uuid.uuid4())


MIGRATION_STATUSES = {"draft", "pending_approval", "approved", "rejected", "changes_requested"}
MIGRATION_TYPES = {"split", "merge", "resegment"}

_VALID_TRANSITIONS = {
    "draft": {"pending_approval"},
    "pending_approval": {"approved", "rejected", "changes_requested"},
}


class SentenceStructureMigration:
    """A proposed change to sentence segment boundaries."""

    def __init__(
        self,
        migration_id: str = "",
        object_id: str = "",
        source_revision: int = 1,
        source_segment_ids: list[str] | None = None,
        proposed_segments: list[dict[str, Any]] | None = None,
        migration_type: str = "split",
        reason: str = "",
        created_by: str = "",
        created_at: str = "",
        approved_by: str = "",
        approved_at: str = "",
        decision_comment: str = "",
        status: str = "draft",
        impact_summary: str = "",
    ) -> None:
        self.migration_id = migration_id or _new_id()
        self.object_id = object_id
        self.source_revision = source_revision
        self.source_segment_ids = source_segment_ids or []
        self.proposed_segments = proposed_segments or []
        self.migration_type = migration_type
        self.reason = reason
        self.created_by = created_by
        self.created_at = created_at or _now()
        self.approved_by = approved_by
        self.approved_at = approved_at
        self.decision_comment = decision_comment
        self.status = status
        self.impact_summary = impact_summary

    def to_dict(self) -> dict[str, Any]:
        return {
            "migration_id": self.migration_id,
            "object_id": self.object_id,
            "source_revision": self.source_revision,
            "source_segment_ids": self.source_segment_ids,
            "proposed_segments": self.proposed_segments,
            "migration_type": self.migration_type,
            "reason": self.reason,
            "created_by": self.created_by,
            "created_at": self.created_at,
            "approved_by": self.approved_by,
            "approved_at": self.approved_at,
            "decision_comment": self.decision_comment,
            "status": self.status,
            "impact_summary": self.impact_summary,
        }

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "SentenceStructureMigration":
        return cls(
            migration_id=d.get("migration_id", ""),
            object_id=d.get("object_id", ""),
            source_revision=d.get("source_revision", 1),
            source_segment_ids=d.get("source_segment_ids", []),
            proposed_segments=d.get("proposed_segments", []),
            migration_type=d.get("migration_type", "split"),
            reason=d.get("reason", ""),
            created_by=d.get("created_by", ""),
            created_at=d.get("created_at", ""),
            approved_by=d.get("approved_by", ""),
            approved_at=d.get("approved_at", ""),
            decision_comment=d.get("decision_comment", ""),
            status=d.get("status", "draft"),
            impact_summary=d.get("impact_summary", ""),
        )


def _check_self_approval(migration: SentenceStructureMigration, actor: str) -> None:
    if migration.created_by == actor:
        raise ValueError("Creator may not approve, reject or request changes on their own migration")


def _check_transition(migration: SentenceStructureMigration, target: str) -> None:
    allowed = _VALID_TRANSITIONS.get(migration.status, set())
    if target not in allowed:
        raise ValueError(
            f"Cannot transition from {migration.status!r} to {target!r}. "
            f"Allowed targets from {migration.status!r}: {sorted(allowed)}"
        )


def submit_migration(migration: SentenceStructureMigration) -> None:
    """Submit a draft migration for approval."""
    _check_transition(migration, "pending_approval")
    migration.status = "pending_approval"


def approve_migration(migration: SentenceStructureMigration, approver: str, comment: str = "") -> None:
    """Approve a migration. Comment is optional. Creator may not approve."""
    _check_self_approval(migration, approver)
    _check_transition(migration, "approved")
    migration.decision_comment = comment
    migration.approved_by = approver
    migration.approved_at = _now()
    migration.status = "approved"


def reject_migration(migration: SentenceStructureMigration, approver: str, comment: str) -> None:
    """Reject a migration. Non-empty comment required. Creator may not reject."""
    _check_self_approval(migration, approver)
    _check_transition(migration, "rejected")
    if not comment.strip():
        raise ValueError("Rejection comment is required")
    migration.decision_comment = comment
    migration.approved_by = approver
    migration.approved_at = _now()
    migration.status = "rejected"


def request_migration_changes(migration: SentenceStructureMigration, requester: str, comment: str) -> None:
    """Request changes to a migration. Non-empty comment required. Creator may not request changes."""
    _check_self_approval(migration, requester)
    _check_transition(migration, "changes_requested")
    if not comment.strip():
        raise ValueError("Changes-requested comment is required")
    migration.decision_comment = comment
    migration.approved_by = requester
    migration.approved_at = _now()
    migration.status = "changes_requested"