"""Strict 1:1 validation and selection for translation variants."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

from .translations import TranslationSegment, TranslationVariant


_PLACEHOLDER_RE = re.compile(r"\{\{([A-Za-z0-9_.:-]+)\}\}")


@dataclass(frozen=True)
class TranslationApplicability:
    markets: tuple[str, ...] = field(default_factory=tuple)
    countries: tuple[str, ...] = field(default_factory=tuple)
    technologies: tuple[str, ...] = field(default_factory=tuple)
    product_families: tuple[str, ...] = field(default_factory=tuple)
    products: tuple[str, ...] = field(default_factory=tuple)
    document_types: tuple[str, ...] = field(default_factory=tuple)
    section_types: tuple[str, ...] = field(default_factory=tuple)
    terminology_profile: str = ""

    @classmethod
    def from_mapping(cls, value: dict[str, Any] | None) -> "TranslationApplicability":
        value = value or {}
        return cls(
            markets=tuple(value.get("markets", ())), countries=tuple(value.get("countries", ())),
            technologies=tuple(value.get("technologies", ())),
            product_families=tuple(value.get("product_families", ())),
            products=tuple(value.get("products", ())), document_types=tuple(value.get("document_types", ())),
            section_types=tuple(value.get("section_types", ())),
            terminology_profile=value.get("terminology_profile", ""),
        )


@dataclass(frozen=True)
class TranslationSelection:
    working_version_id: str
    content_object_id: str
    canonical_revision: int
    target_language: str
    translation_variant_id: str
    translation_revision: int
    selected_by: str
    selected_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())


@dataclass(frozen=True)
class TranslationJobDefinition:
    job_id: str
    source_language: str
    target_language: str
    ordered_block_ids: tuple[str, ...]
    ordered_segment_ids: tuple[str, ...]
    provider_config_reference: str = ""
    prompt_profile_revision: str = ""
    terminology_profile_revision: str = ""
    neighboring_context_ids: tuple[str, ...] = field(default_factory=tuple)
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())


@dataclass(frozen=True)
class TranslationFinding:
    code: str
    message: str
    segment_id: str = ""
    index: int | None = None


def _segment_value(segment: Any, name: str, default: Any = None) -> Any:
    if isinstance(segment, dict):
        return segment.get(name, default)
    return getattr(segment, name, default)


def validate_translation_variant(
    variant: TranslationVariant,
    source_segments: list[Any],
    *,
    source_revision_status: str = "approved",
) -> list[TranslationFinding]:
    """Validate exact IDs/order/types/placeholders; no inferred correspondence."""
    findings: list[TranslationFinding] = []
    targets = variant.segment_translations
    if len(targets) != len(source_segments):
        findings.append(TranslationFinding(
            "translation-segment-count-mismatch",
            f"Expected {len(source_segments)} target segments, got {len(targets)}",
        ))

    if variant.status == "approved" and source_revision_status != "approved":
        findings.append(TranslationFinding(
            "translation-approved-against-draft-source",
            "Approved translation cannot reference an unapproved content revision",
        ))

    source_ids = [_segment_value(item, "segment_id", "") for item in source_segments]
    target_ids = [_segment_value(item, "segment_id", "") for item in targets]
    for duplicate_id in sorted({item for item in target_ids if item and target_ids.count(item) > 1}):
        findings.append(TranslationFinding("translation-duplicate-segment-id", f"Duplicate target segment ID {duplicate_id}", duplicate_id))

    for index, source in enumerate(source_segments):
        if index >= len(targets):
            break
        target = targets[index]
        source_id = _segment_value(source, "segment_id", "")
        target_id = _segment_value(target, "segment_id", "")
        if not target_id:
            findings.append(TranslationFinding("translation-missing-segment-id", "Target segment ID is required", index=index))
        elif source_id != target_id:
            findings.append(TranslationFinding("translation-segment-id-mismatch", f"Expected {source_id}, got {target_id}", target_id, index))

        source_order = _segment_value(source, "order", index)
        target_order = _segment_value(target, "order", index)
        if source_order != target_order:
            findings.append(TranslationFinding("translation-segment-order-mismatch", f"Expected order {source_order}, got {target_order}", target_id, index))

        source_type = _segment_value(source, "segment_type", "sentence")
        target_type = _segment_value(target, "segment_type", source_type)
        if source_type != target_type:
            findings.append(TranslationFinding("translation-segment-type-mismatch", f"Expected type {source_type}, got {target_type}", target_id, index))

        translated_text = _segment_value(target, "translated_text", "")
        if variant.status in {"reviewed", "approved"} and not str(translated_text).strip():
            findings.append(TranslationFinding("translation-empty-approved-segment", "Reviewed/approved target text must not be empty", target_id, index))

        source_text = _segment_value(source, "source_text", "")
        required_placeholders = set(_PLACEHOLDER_RE.findall(str(source_text)))
        target_placeholders = set(_PLACEHOLDER_RE.findall(str(translated_text)))
        if required_placeholders != target_placeholders:
            findings.append(TranslationFinding(
                "translation-placeholder-mismatch",
                f"Expected placeholders {sorted(required_placeholders)}, got {sorted(target_placeholders)}",
                target_id,
                index,
            ))

    if variant.canonical_revision < 1:
        findings.append(TranslationFinding("translation-invalid-canonical-revision", "canonical_revision must be positive"))
    return findings


def select_translation_variant(
    variants: list[TranslationVariant],
    *,
    content_object_id: str,
    canonical_revision: int,
    target_language: str,
    context: dict[str, str],
) -> tuple[TranslationVariant | None, list[TranslationFinding]]:
    """Select only an unambiguous approved exact-context variant."""
    matches: list[TranslationVariant] = []
    for variant in variants:
        if variant.status != "approved" or variant.content_object_id != content_object_id:
            continue
        if variant.canonical_revision != canonical_revision or variant.target_language != target_language:
            continue
        applicability = TranslationApplicability.from_mapping(variant.applicability)
        checks = {
            "market": applicability.markets,
            "country": applicability.countries,
            "technology": applicability.technologies,
            "product_family": applicability.product_families,
            "product": applicability.products,
            "document_type": applicability.document_types,
            "section_type": applicability.section_types,
        }
        if all(not allowed or context.get(key) in allowed for key, allowed in checks.items()):
            if not applicability.terminology_profile or context.get("terminology_profile") == applicability.terminology_profile:
                matches.append(variant)
    matches.sort(key=lambda item: (item.id, item.revision))
    if len(matches) == 1:
        return matches[0], []
    if not matches:
        return None, [TranslationFinding("translation-variant-not-found", "No approved translation variant matches the context")]
    return None, [TranslationFinding("translation-variant-ambiguous", "Several approved translation variants match equally; explicit selection is required")]
