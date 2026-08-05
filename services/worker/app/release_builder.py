"""Build immutable IFU language releases from validated resolver output."""

from __future__ import annotations

from typing import Any

from .configuration import ConfigurationCatalog, ConfigurationValue
from .ifu_release import (
    ContentRevisionBinding,
    IFULanguageReleaseSnapshot,
    ResolvedBlockSnapshot,
    TranslationRevisionBinding,
)
from .translation_validation import TranslationSelection


class ReleaseBuildError(ValueError):
    def __init__(self, findings: list[dict[str, Any]]) -> None:
        super().__init__("Release snapshot cannot be created")
        self.findings = findings


def build_language_release_snapshot(
    *,
    release_id: str,
    product_id: str,
    language: str,
    version: int,
    resolved_tree: Any,
    configuration_catalog: ConfigurationCatalog,
    configuration_values: list[ConfigurationValue],
    translation_selections: list[TranslationSelection] | None = None,
    ruleset_revision: str = "",
    terminology_profile_revision: str = "",
    source_release_id: str = "",
    created_at: str = "",
    created_by: str = "",
) -> IFULanguageReleaseSnapshot:
    findings: list[dict[str, Any]] = []
    if getattr(resolved_tree.provenance, "mode", "") != "pinned":
        findings.append({"code": "release-requires-pinned-resolution", "message": "Release creation requires revision_mode='pinned'"})
    if not resolved_tree.is_valid():
        findings.extend(
            item.to_dict() if hasattr(item, "to_dict") else {"code": "resolution-error", "message": str(item)}
            for item in getattr(resolved_tree, "findings", [])
            if getattr(item, "severity", "ERROR") in {"ERROR", "FATAL"}
        )
        if not findings:
            findings.append({"code": "invalid-resolution", "message": "Resolver output contains blocking errors"})

    configuration_snapshot, configuration_errors = configuration_catalog.snapshot(
        configuration_values,
        require_approved=True,
    )
    findings.extend({"code": "invalid-configuration-snapshot", "message": error} for error in configuration_errors)

    if findings:
        raise ReleaseBuildError(findings)

    content_pairs = sorted({(block.source_object_id, block.source_revision) for block in resolved_tree.blocks})
    content_bindings = tuple(ContentRevisionBinding(object_id, revision) for object_id, revision in content_pairs)
    resolved_blocks = tuple(
        ResolvedBlockSnapshot(
            block_id=block.block_id,
            source_object_id=block.source_object_id,
            source_revision=block.source_revision,
            rendered_content=block.rendered_content,
            block_type=block.block_type,
        )
        for block in resolved_tree.blocks
    )

    selections = sorted(
        translation_selections or [],
        key=lambda item: (
            item.content_object_id,
            item.target_language,
            item.translation_variant_id,
            item.translation_revision,
        ),
    )
    translation_bindings = tuple(
        TranslationRevisionBinding(
            content_object_id=item.content_object_id,
            target_language=item.target_language,
            variant_id=item.translation_variant_id,
            revision=item.translation_revision,
            canonical_revision=item.canonical_revision,
        )
        for item in selections
    )

    provenance = {
        "resolution_checksum": resolved_tree.checksum,
        "graph_checksum": getattr(resolved_tree.provenance, "graph_checksum", ""),
        "configuration_hash": resolved_tree.config_hash,
        "resolution_mode": getattr(resolved_tree.provenance, "mode", ""),
        "object_revisions_read": getattr(resolved_tree.provenance, "object_revisions_read", []),
        "aliases_followed": getattr(resolved_tree.provenance, "aliases_followed", []),
    }

    return IFULanguageReleaseSnapshot(
        release_id=release_id,
        product_id=product_id,
        language=language,
        version=version,
        content_bindings=content_bindings,
        translation_bindings=translation_bindings,
        configuration_snapshot=configuration_snapshot,
        resolved_blocks=resolved_blocks,
        ruleset_revision=ruleset_revision,
        terminology_profile_revision=terminology_profile_revision,
        provenance=provenance,
        source_release_id=source_release_id,
        created_at=created_at,
        created_by=created_by,
    )
