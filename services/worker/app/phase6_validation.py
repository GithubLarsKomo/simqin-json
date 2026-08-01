"""Centralized structured validation for Phase 6 content models."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from .content_build_graph import build_content_graph
from .content_objects import ContentObject, SLOT_TYPES
from .content_segment import ContentSegment, validate_segments
from .slot_validation import validate_slot_definition, validate_slot_value
from .strict_translations import StrictTranslationVariant, validate_translation_variant


@dataclass(frozen=True)
class Phase6ValidationIssue:
    level: str
    code: str
    message: str
    object_id: str = ""
    revision: int = 0
    path: tuple[str, ...] = field(default_factory=tuple)
    details: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "level": self.level,
            "code": self.code,
            "message": self.message,
            "object_id": self.object_id,
            "revision": self.revision,
            "path": list(self.path),
            "details": dict(self.details),
        }


class Phase6ValidationResult:
    def __init__(self) -> None:
        self.issues: list[Phase6ValidationIssue] = []

    def add(self, issue: Phase6ValidationIssue) -> None:
        self.issues.append(issue)

    @property
    def valid(self) -> bool:
        return all(issue.level not in {"ERROR", "FATAL"} for issue in self.issues)

    def to_dict(self) -> dict[str, Any]:
        ordered = sorted(
            self.issues,
            key=lambda issue: (issue.level, issue.code, issue.object_id, issue.revision, issue.path),
        )
        return {
            "valid": self.valid,
            "issues": [issue.to_dict() for issue in ordered],
            "error_count": sum(issue.level in {"ERROR", "FATAL"} for issue in ordered),
            "warning_count": sum(issue.level == "WARNING" for issue in ordered),
            "info_count": sum(issue.level == "INFO" for issue in ordered),
        }


def _add_messages(
    result: Phase6ValidationResult,
    messages: list[str],
    code: str,
    object_id: str,
    revision: int,
) -> None:
    for message in messages:
        result.add(Phase6ValidationIssue("ERROR", code, message, object_id, revision))


def validate_content_domain(
    objects: dict[str, ContentObject],
    *,
    pinned_revisions: dict[str, int] | None = None,
    slot_values: dict[str, Any] | None = None,
    translations: list[tuple[StrictTranslationVariant, list[ContentSegment]]] | None = None,
) -> Phase6ValidationResult:
    """Validate content objects, graph cycles, segments, slots and translations."""
    pinned_revisions = pinned_revisions or {}
    slot_values = slot_values or {}
    translations = translations or []
    result = Phase6ValidationResult()

    graph = build_content_graph(objects, pinned_revisions)
    for cycle in graph.find_cycles():
        result.add(Phase6ValidationIssue(
            "FATAL",
            cycle.cycle_type,
            f"Content cycle detected: {' -> '.join(node.key for node in cycle.nodes)}",
            path=tuple(node.key for node in cycle.nodes),
        ))

    for object_id in sorted(objects):
        obj = objects[object_id]
        if obj.current_revision < 1 or obj.get_revision(obj.current_revision) is None:
            result.add(Phase6ValidationIssue(
                "ERROR", "invalid-current-revision",
                f"Current revision {obj.current_revision} is missing", object_id, obj.current_revision,
            ))
        for revision in sorted(obj.revisions, key=lambda item: item.revision):
            typed_segments: list[ContentSegment] = []
            for raw in revision.sentence_segments:
                typed_segments.append(raw if isinstance(raw, ContentSegment) else ContentSegment.from_dict(raw))
            _add_messages(result, validate_segments(typed_segments), "invalid-content-segment", object_id, revision.revision)

            seen_slots: set[str] = set()
            for slot in revision.slots:
                if slot.slot_id in seen_slots:
                    result.add(Phase6ValidationIssue(
                        "ERROR", "duplicate-slot-id",
                        f"Duplicate slot id {slot.slot_id}", object_id, revision.revision,
                    ))
                seen_slots.add(slot.slot_id)
                _add_messages(
                    result,
                    validate_slot_definition(slot),
                    "invalid-slot-type" if slot.type not in SLOT_TYPES else "invalid-slot-definition",
                    object_id,
                    revision.revision,
                )
                if slot.slot_id in slot_values:
                    _add_messages(
                        result,
                        validate_slot_value(slot, slot_values[slot.slot_id]),
                        "invalid-slot-value",
                        object_id,
                        revision.revision,
                    )
                elif slot.required and slot.default_value in (None, "", []):
                    result.add(Phase6ValidationIssue(
                        "ERROR", "unresolved-slot",
                        f"Required slot {slot.slot_id} has no value", object_id, revision.revision,
                    ))

            for binding in revision.composed_objects:
                child = objects.get(binding.child_object_id)
                if child is None:
                    result.add(Phase6ValidationIssue(
                        "ERROR", "missing-content-object",
                        f"Composed object {binding.child_object_id} is missing", object_id, revision.revision,
                    ))
                elif child.get_revision(binding.pinned_revision) is None:
                    result.add(Phase6ValidationIssue(
                        "ERROR", "missing-content-revision",
                        f"Composed revision {binding.child_object_id}@{binding.pinned_revision} is missing",
                        object_id, revision.revision,
                    ))

    for variant, source_segments in translations:
        for finding in validate_translation_variant(variant, source_segments):
            result.add(Phase6ValidationIssue(
                finding.level,
                finding.code,
                finding.message,
                variant.content_object_id,
                variant.canonical_revision,
                details=finding.details,
            ))

    return result
