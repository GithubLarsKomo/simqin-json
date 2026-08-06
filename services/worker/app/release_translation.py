"""Revision-exact translation selection for immutable Phase 6 releases."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from .content_objects import ContentObject
from .translation_validation import TranslationSelection, validate_translation_variant
from .translations import TranslationVariant


class ReleaseTranslationError(ValueError):
    def __init__(self, findings: list[dict[str, Any]]) -> None:
        super().__init__("Release translation selection is invalid")
        self.findings = findings


def build_release_translation_selections(
    *,
    release_id: str,
    release_language: str,
    objects: dict[str, ContentObject],
    resolved_tree: Any,
    variants: list[TranslationVariant],
    selection_rows: list[dict[str, Any]],
    selected_by: str,
) -> list[TranslationSelection]:
    """Validate explicit translation pins against resolved content revisions.

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

        object_errors = [item for item in findings if item.get("object_id") == object_id]
        if object_errors:
            continue
        results.append(TranslationSelection(
            working_version_id=release_id,
            content_object_id=object_id,
            canonical_revision=canonical_revision,
            target_language=release_language,
            translation_variant_id=variant.id,
            translation_revision=variant.revision,
            selected_by=selected_by,
            selected_at=now,
        ))

    unexpected = sorted(set(selections_by_object) - {object_id for object_id, _ in resolved_pairs})
    for object_id in unexpected:
        findings.append({
            "code": "translation-selection-not-in-release",
            "message": f"Translation selection for {object_id} is not part of the resolved release",
            "object_id": object_id,
        })

    if findings:
        raise ReleaseTranslationError(findings)
    return sorted(results, key=lambda item: (item.content_object_id, item.target_language, item.translation_variant_id, item.translation_revision))
