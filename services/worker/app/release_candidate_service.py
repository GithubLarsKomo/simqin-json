"""Validation/build service for frozen Phase 6 release candidates."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from .configuration import ConfigurationCatalog, ConfigurationParameter, ConfigurationValue
from .content_objects import ContentObject, MultiplicityRule
from .release_builder import build_language_release_snapshot
from .release_translation import build_release_translation_plan
from .scoped_content_resolver import resolve_content_tree
from .translation_store import TranslationVariantStore
from .translations import TranslationVariant


def _objects(rows: list[dict[str, Any]]) -> dict[str, ContentObject]:
    parsed: dict[str, ContentObject] = {}
    for row in rows:
        obj = ContentObject.from_dict(row)
        if obj.id in parsed:
            raise ValueError(f"Duplicate ContentObject id {obj.id}")
        parsed[obj.id] = obj
    return parsed


def _persistent_variants(selection_rows: list[dict[str, Any]]) -> list[TranslationVariant]:
    store = TranslationVariantStore()
    variants: list[TranslationVariant] = []
    seen: set[tuple[str, int]] = set()
    for row in selection_rows:
        variant_id = str(row.get("variant_id", "")).strip()
        revision = row.get("revision")
        if not variant_id or not isinstance(revision, int) or revision < 1:
            continue
        key = (variant_id, revision)
        if key in seen:
            continue
        seen.add(key)
        persisted = store.get(variant_id, revision)
        if persisted is not None:
            variants.append(TranslationVariant.from_dict(persisted))
    return variants


def build_from_candidate_payload(
    payload: dict[str, Any],
    *,
    release_id: str,
    version: int,
    created_by: str,
) -> Any:
    objects = _objects(list(payload.get("objects", [])))
    rules = [MultiplicityRule.from_dict(row) for row in payload.get("multiplicity_rules", [])]
    tree = resolve_content_tree(
        root_object_ids=list(payload.get("root_object_ids", [])),
        objects=objects,
        pinned_revisions=dict(payload.get("pinned_revisions", {})),
        config_values=dict(payload.get("slot_values", {})),
        aliases=dict(payload.get("aliases", {})),
        revision_mode="pinned",
        multiplicity_rules=rules,
    )
    catalog = ConfigurationCatalog()
    for row in payload.get("configuration_parameters", []):
        catalog.add(ConfigurationParameter.from_dict(row))
    values = [ConfigurationValue.from_dict(row) for row in payload.get("configuration_values", [])]
    selection_rows = list(payload.get("translation_selections", []))
    variants = _persistent_variants(selection_rows)
    translation_plan = build_release_translation_plan(
        release_id=release_id,
        release_language=str(payload.get("language", "")),
        objects=objects,
        resolved_tree=tree,
        variants=variants,
        selection_rows=selection_rows,
        selected_by=created_by,
    )
    return build_language_release_snapshot(
        release_id=release_id,
        product_id=str(payload.get("product_id", "")),
        language=str(payload.get("language", "")),
        version=version,
        resolved_tree=tree,
        configuration_catalog=catalog,
        configuration_values=values,
        translation_selections=translation_plan.selections,
        rendered_block_overrides=translation_plan.rendered_block_overrides,
        ruleset_revision=str(payload.get("ruleset_revision", "")),
        terminology_profile_revision=str(payload.get("terminology_profile_revision", "")),
        source_release_id=str(payload.get("source_release_id", "")),
        created_at=datetime.now(timezone.utc).isoformat(),
        created_by=created_by,
    )


def validate_candidate_payload(payload: dict[str, Any]) -> dict[str, Any]:
    probe = build_from_candidate_payload(
        payload,
        release_id="candidate-validation",
        version=1,
        created_by="candidate-validator",
    )
    return {
        "valid": True,
        "resolution_checksum": probe.provenance.get("resolution_checksum", ""),
        "graph_checksum": probe.provenance.get("graph_checksum", ""),
        "translation_bindings": [item.to_dict() for item in probe.translation_bindings],
        "content_bindings": [item.to_dict() for item in probe.content_bindings],
    }
