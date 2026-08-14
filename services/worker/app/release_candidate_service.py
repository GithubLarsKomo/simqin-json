"""Validation/build service for frozen Phase 6 release candidates."""

from __future__ import annotations

from dataclasses import asdict
from datetime import datetime, timezone
from typing import Any

from .canonical_content_store import CanonicalContentStore
from .canonical_source_validation import revision_matches_snapshot
from .configuration import ConfigurationCatalog, ConfigurationParameter, ConfigurationValue
from .configuration_store import ConfigurationParameterStore
from .content_objects import ContentObject, MultiplicityRule
from .release_builder import ReleaseBuildError, build_language_release_snapshot
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


def _validate_trusted_sources(objects: dict[str, ContentObject], resolved_tree: Any) -> None:
    """Require every resolved revision to equal its immutable trusted source."""
    findings: list[dict[str, Any]] = []
    store = CanonicalContentStore()
    resolved_pairs = sorted({(block.source_object_id, block.source_revision) for block in resolved_tree.blocks})

    for object_id, revision in resolved_pairs:
        obj = objects.get(object_id)
        source_revision = obj.get_revision(revision) if obj is not None else None
        if source_revision is None:
            findings.append({
                "code": "canonical-source-revision-missing",
                "message": f"Resolved canonical revision {object_id}@{revision} is unavailable",
                "object_id": object_id,
                "revision": revision,
            })
            continue
        try:
            trusted = store.get(object_id, revision)
        except ValueError as exc:
            findings.append({
                "code": "canonical-source-integrity-failed",
                "message": str(exc),
                "object_id": object_id,
                "revision": revision,
            })
            continue
        if trusted is None:
            findings.append({
                "code": "canonical-source-not-registered",
                "message": f"Trusted canonical source {object_id}@{revision} is not registered",
                "object_id": object_id,
                "revision": revision,
            })
            continue
        if not revision_matches_snapshot(source_revision, trusted["revision_payload"]):
            findings.append({
                "code": "canonical-source-mismatch",
                "message": f"Candidate content {object_id}@{revision} differs from its trusted canonical source snapshot",
                "object_id": object_id,
                "revision": revision,
            })

    if findings:
        raise ReleaseBuildError(findings)


def _trusted_configuration_catalog(
    parameter_rows: list[dict[str, Any]],
    values: list[ConfigurationValue],
) -> tuple[ConfigurationCatalog, list[str]]:
    """Build a release catalog only from immutable server-side parameter revisions.

    Full parameter rows supplied by older clients are treated as assertions, not
    authority. If present they must exactly match the trusted stored revision.
    """
    supplied: dict[tuple[str, int], ConfigurationParameter] = {}
    for row in parameter_rows:
        parameter = ConfigurationParameter.from_dict(row)
        key = parameter.key()
        if key in supplied:
            raise ValueError(f"Duplicate configuration parameter {parameter.parameter_id}@{parameter.revision}")
        supplied[key] = parameter

    required = set(supplied)
    required.update((value.parameter_id, value.parameter_revision) for value in values)
    store = ConfigurationParameterStore()
    catalog = ConfigurationCatalog()
    checksums: list[str] = []
    findings: list[dict[str, Any]] = []

    for parameter_id, revision in sorted(required):
        if not parameter_id or revision < 1:
            findings.append({
                "code": "configuration-parameter-reference-invalid",
                "message": f"Invalid configuration parameter reference {parameter_id}@{revision}",
                "parameter_id": parameter_id,
                "revision": revision,
            })
            continue
        try:
            trusted = store.get(parameter_id, revision)
        except ValueError as exc:
            findings.append({
                "code": "configuration-parameter-integrity-failed",
                "message": str(exc),
                "parameter_id": parameter_id,
                "revision": revision,
            })
            continue
        if trusted is None:
            findings.append({
                "code": "configuration-parameter-not-registered",
                "message": f"Trusted configuration parameter {parameter_id}@{revision} is not registered",
                "parameter_id": parameter_id,
                "revision": revision,
            })
            continue
        trusted_parameter = ConfigurationParameter.from_dict(trusted["parameter"])
        asserted = supplied.get((parameter_id, revision))
        if asserted is not None and asserted.to_dict() != trusted_parameter.to_dict():
            findings.append({
                "code": "configuration-parameter-mismatch",
                "message": f"Candidate parameter {parameter_id}@{revision} differs from the trusted configuration catalog",
                "parameter_id": parameter_id,
                "revision": revision,
            })
            continue
        catalog.add(trusted_parameter)
        checksums.append(str(trusted["payload_checksum"]))

    if findings:
        raise ReleaseBuildError(findings)
    return catalog, checksums


def build_from_candidate_payload(
    payload: dict[str, Any],
    *,
    release_id: str,
    version: int,
    created_by: str,
    candidate_id: str = "",
    candidate_checksum: str = "",
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
    _validate_trusted_sources(objects, tree)

    values = [ConfigurationValue.from_dict(row) for row in payload.get("configuration_values", [])]
    catalog, configuration_checksums = _trusted_configuration_catalog(
        list(payload.get("configuration_parameters", [])), values
    )
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
    extra_provenance: dict[str, Any] = {}
    if candidate_id:
        extra_provenance["release_candidate_id"] = candidate_id
    if candidate_checksum:
        extra_provenance["release_candidate_checksum"] = candidate_checksum
    if configuration_checksums:
        extra_provenance["configuration_parameter_checksums"] = configuration_checksums
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
        extra_provenance=extra_provenance,
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
        "translation_bindings": [asdict(item) for item in probe.translation_bindings],
        "content_bindings": [asdict(item) for item in probe.content_bindings],
    }
