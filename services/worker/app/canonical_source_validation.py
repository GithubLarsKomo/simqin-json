"""Shared matching rules for trusted canonical source revisions.

Only fields that define releasable content semantics are compared. Audit metadata
such as created_at/created_by is intentionally excluded; content, segmentation,
slots, visibility, composition and approval state must match exactly.
"""

from __future__ import annotations

from typing import Any


def revision_matches_snapshot(source_revision: Any, snapshot_payload: dict[str, Any]) -> bool:
    visibility = source_revision.visibility_rule.to_dict() if source_revision.visibility_rule else None
    return (
        source_revision.canonical_content == snapshot_payload.get("canonical_content", "")
        and source_revision.sentence_segments == snapshot_payload.get("sentence_segments", [])
        and [slot.to_dict() for slot in source_revision.slots] == snapshot_payload.get("slots", [])
        and visibility == snapshot_payload.get("visibility_rule")
        and [binding.to_dict() for binding in source_revision.composed_objects]
        == snapshot_payload.get("composed_objects", [])
        and source_revision.approval_status == snapshot_payload.get("approval_status", "")
    )
