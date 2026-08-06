"""Revision-exact translation selection for immutable Phase 6 releases."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

from .content_objects import ContentObject
from .translation_validation import TranslationSelection, validate_translation_variant
from .translations import TranslationVariant


_PLACEHOLDER_RE = re.compile(r"\{\{([A-Za-z0-9_.:-]+)\}\}")


class ReleaseTranslationError(ValueError):
    def __init__(self, findings: list[dict[str, Any]]) -> None:
        super().__init__("Release translation selection is invalid")
        self.findings = findings


@dataclass(frozen=True)
class ReleaseTranslationPlan:
    selections: tuple[TranslationSelection, ...] = field(default_factory=tuple)
    rendered_block_overrides: dict[int, str] = field(default_factory=dict)


def _segment_value(segment: Any, name: str, default: Any = None) -> Any:
    if isinstance(segment, dict):
        return segment.get(name, default)
    return getattr(segment, name, default)


def _materialize_translated_template(
    template: str,
    source_segments: list[Any],
    target_segments: list[Any],
) -> tuple[str | None, str | None]:
    """Replace exact source segments while preserving all separators/layout text."""
    ordered = sorted(
        zip(source_segments, target_segments),
        key=lambda pair: (_segment_value(pair[0], "order", 0), _segment_value(pair[0], "segment_id", "")),
    )
    cursor = 0
    output: list[str] = []
    for source, target in ordered:
        source_text = str(_segment_value(source, "source_text", ""))
        translated_text = str(_segment_value(target, "translated_text", ""))
        if not source_text:
            return None, "Source segment text is empty and cannot be materialized deterministically"
        position = template.find(source_text, cursor)
        if position < 0:
            return None, f"Source segment {source_text!r} is not present in the resolved template"
        output.append(template[cursor:position])
        output.append(translated_text)
        cursor = position + len(source_text)
    output.append(template[cursor:])
    return "".join(output), None


def _render_slots(template: str, values: dict[str, Any]) -> tuple[str, list[str]]:
    missing: list[str] = []

    def replace(match: re.Match[str]) -> str:
        slot_id = match.group(1)
        if slot_id not in values:
            missing.append(slot_id)
            return match.group(0)
        value = values[slot_id]
        return "" if value is None else str(value)

    return _PLACEHOLDER_RE.sub(replace, template), sorted(set(missing))


def build_release_translation_plan(
    *,
    release_id: str,
    release_language: str,
    objects: dict[str, ContentObject],
    resolved_tree: Any,
    variants: list[TranslationVariant],
    selection_rows: list[dict[str, Any]],
    selected_by: str,
) -> ReleaseTranslationPlan:
    """Validate explicit translation pins and materialize target-language blocks.

    Canonical-language blocks need no translation selection. Every resolved block
    whose canonical language differs from the release language requires exactly
    one explicit approved variant pinned by variant id and variant revision.
    """
    findings: list[dict[str, Any]] = []
    variant_index = {(item.id, item.revision): item for item in variants}
    selections_by_object: dict[str, dict[str, Any]] = {}

    for row in selection_rows:
        object_id = str(row.get("content_object_id", "")).strip()
        variant_id = str(row.get("variant_id", "")).strip()
        revision = row.get("revision")
        if not object_id or not variant_id or not isinstance(revision, int) or revision < 1:
            findings.append({
                "code": "invalid-translation-selection",
                "message": "Translation selection requires content_object_id, variant_id and positive revision",
                "object_id": object_id,
            })
            continue
        if object_id in selections_by_object:
            findings.append({
                "code": "duplicate-translation-selection",
                "message": f"Several translation selections were provided for {object_id}",
                "object_id": object_id,
            })
            continue
        selections_by_object[object_id] = row

    resolved_pairs = sorted({(block.source_object_id, block.source_revision) for block in resolved_tree.blocks})
    selection_by_pair: dict[tuple[str, int], tuple[TranslationSelection, TranslationVariant]] = {}
    results: list[TranslationSelection] = []
    now = datetime.now(timezone.utc).isoformat()

    for object_id, canonical_revision in resolved_pairs:
        obj = objects.get(object_id)
        if obj is None:
            findings.append({
                "code": "translation-source-object-missing",
                "message": f"Resolved content object {object_id} is unavailable for translation validation",
                "object_id": object_id,
            })
            continue
        if obj.canonical_language == release_language:
            continue

        row = selections_by_object.get(object_id)
        if row is None:
            findings.append({
                "code": "translation-selection-required",
                "message": f"Release language {release_language} requires a translation selection for {object_id}@{canonical_revision}",
                "object_id": object_id,
                "canonical_revision": canonical_revision,
            })
            continue

        variant = variant_index.get((str(row.get("variant_id", "")), int(row.get("revision", 0))))
        if variant is None:
            findings.append({
                "code": "translation-variant-not-found",
                "message": f"Selected translation variant {row.get('variant_id')}@{row.get('revision')} was not provided",
                "object_id": object_id,
            })
            continue
        before = len(findings)
        if variant.content_object_id != object_id:
            findings.append({
                "code": "translation-object-mismatch",
                "message": f"Variant {variant.id}@{variant.revision} belongs to {variant.content_object_id}, not {object_id}",
                "object_id": object_id,
            })
        if variant.canonical_revision != canonical_revision:
            findings.append({
                "code": "translation-canonical-revision-mismatch",
                "message": f"Variant {variant.id}@{variant.revision} targets canonical revision {variant.canonical_revision}, expected {canonical_revision}",
                "object_id": object_id,
                "canonical_revision": canonical_revision,
            })
        if variant.target_language != release_language:
            findings.append({
                "code": "translation-language-mismatch",
                "message": f"Variant {variant.id}@{variant.revision} targets {variant.target_language}, expected {release_language}",
                "object_id": object_id,
            })
        if variant.status != "approved":
            findings.append({
                "code": "translation-not-approved",
                "message": f"Variant {variant.id}@{variant.revision} has status {variant.status!r}; approved is required",
                "object_id": object_id,
            })

        source_revision = obj.get_revision(canonical_revision)
        if source_revision is None:
            findings.append({
                "code": "translation-source-revision-missing",
                "message": f"Canonical revision {object_id}@{canonical_revision} is missing",
                "object_id": object_id,
            })
            continue
        validation_findings = validate_translation_variant(
            variant,
            list(source_revision.sentence_segments),
            source_revision_status=source_revision.approval_status,
        )
        findings.extend({
            "code": item.code,
            "message": item.message,
            "object_id": object_id,
            "segment_id": item.segment_id,
            "index": item.index,
        } for item in validation_findings)

        if len(findings) != before:
            continue
        selection = TranslationSelection(
            working_version_id=release_id,
            content_object_id=object_id,
            canonical_revision=canonical_revision,
            target_language=release_language,
            translation_variant_id=variant.id,
            translation_revision=variant.revision,
            selected_by=selected_by,
            selected_at=now,
        )
        results.append(selection)
        selection_by_pair[(object_id, canonical_revision)] = (selection, variant)

    unexpected = sorted(set(selections_by_object) - {object_id for object_id, _ in resolved_pairs})
    for object_id in unexpected:
        findings.append({
            "code": "translation-selection-not-in-release",
            "message": f"Translation selection for {object_id} is not part of the resolved release",
            "object_id": object_id,
        })

    rendered_overrides: dict[int, str] = {}
    if not findings:
        for index, block in enumerate(resolved_tree.blocks):
            obj = objects.get(block.source_object_id)
            if obj is None or obj.canonical_language == release_language:
                continue
            selected = selection_by_pair.get((block.source_object_id, block.source_revision))
            if selected is None:
                findings.append({
                    "code": "translation-selection-required",
                    "message": f"No validated translation selection exists for {block.source_object_id}@{block.source_revision}",
                    "object_id": block.source_object_id,
                })
                continue
            _, variant = selected
            source_revision = obj.get_revision(block.source_revision)
            translated_template, materialization_error = _materialize_translated_template(
                block.source_template_content,
                list(source_revision.sentence_segments) if source_revision else [],
                list(variant.segment_translations),
            )
            if materialization_error or translated_template is None:
                findings.append({
                    "code": "translation-materialization-failed",
                    "message": materialization_error or "Translation materialization failed",
                    "object_id": block.source_object_id,
                    "canonical_revision": block.source_revision,
                })
                continue
            rendered, missing_slots = _render_slots(translated_template, dict(block.slot_values))
            if missing_slots:
                findings.append({
                    "code": "translation-unresolved-slot",
                    "message": f"Translated block contains unresolved slots: {', '.join(missing_slots)}",
                    "object_id": block.source_object_id,
                    "canonical_revision": block.source_revision,
                })
                continue
            rendered_overrides[index] = rendered

    if findings:
        raise ReleaseTranslationError(findings)
    return ReleaseTranslationPlan(
        selections=tuple(sorted(results, key=lambda item: (item.content_object_id, item.target_language, item.translation_variant_id, item.translation_revision))),
        rendered_block_overrides=rendered_overrides,
    )
