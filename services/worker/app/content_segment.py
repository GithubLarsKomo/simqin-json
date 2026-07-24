"""ContentSegment — stable sentence/segment model with immutable boundaries."""

from __future__ import annotations

from typing import Any


SEGMENT_TYPES = {"sentence", "heading", "list-item", "table-cell", "caption", "label"}


class ContentSegment:
    """A single segment within a ContentObjectRevision's content."""

    def __init__(
        self,
        segment_id: str = "",
        segment_type: str = "sentence",
        source_text: str = "",
        source_revision: int = 1,
        order: int = 0,
        immutable_boundary: bool = True,
        metadata: dict[str, Any] | None = None,
    ) -> None:
        if segment_type not in SEGMENT_TYPES:
            raise ValueError(f"Invalid segment type {segment_type!r}. Must be one of {SEGMENT_TYPES}")
        self.segment_id = segment_id
        self.segment_type = segment_type
        self.source_text = source_text
        self.source_revision = source_revision
        self.order = order
        self.immutable_boundary = immutable_boundary if segment_type != "sentence" else True
        self.metadata = metadata or {}

    def to_dict(self) -> dict[str, Any]:
        return {
            "segment_id": self.segment_id,
            "segment_type": self.segment_type,
            "source_text": self.source_text,
            "source_revision": self.source_revision,
            "order": self.order,
            "immutable_boundary": self.immutable_boundary,
            "metadata": self.metadata,
        }

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "ContentSegment":
        return cls(
            segment_id=d.get("segment_id", ""),
            segment_type=d.get("segment_type", "sentence"),
            source_text=d.get("source_text", ""),
            source_revision=d.get("source_revision", 1),
            order=d.get("order", 0),
            immutable_boundary=d.get("immutable_boundary", True),
            metadata=d.get("metadata", {}),
        )


def validate_segments(segments: list[ContentSegment]) -> list[str]:
    """Validate a list of ContentSegment objects. Returns validation errors."""
    errors: list[str] = []
    seen_ids: set[str] = set()
    seen_orders: set[int] = set()

    for i, seg in enumerate(segments):
        if not seg.segment_id:
            errors.append(f"segments[{i}]: segment_id is required")
        if seg.segment_id in seen_ids:
            errors.append(f"segments[{i}]: duplicate segment_id {seg.segment_id!r}")
        seen_ids.add(seg.segment_id)

        if seg.order < 0:
            errors.append(f"segments[{i}]: negative order {seg.order}")
        if seg.order in seen_orders:
            errors.append(f"segments[{i}]: duplicate order {seg.order}")
        seen_orders.add(seg.order)

        if seg.source_revision < 1:
            errors.append(f"segments[{i}]: source_revision must be positive")

        if seg.segment_type not in SEGMENT_TYPES:
            errors.append(f"segments[{i}]: invalid segment_type {seg.segment_type!r}")

        if seg.segment_type == "sentence" and not seg.immutable_boundary:
            errors.append(f"segments[{i}]: sentence segments must have immutable_boundary=True")

    return errors