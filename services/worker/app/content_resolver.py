"""Content resolver — deterministically resolves a ContentObject tree.

Pipeline:
  1. Resolve alias
  2. Pin revision
  3. Resolve base-template chain
  4. Inherit content
  5. Apply slot overrides and defaults
  6. Evaluate applicability rules
  7. Resolve variant groups
  8. Resolve recursive composition
  9. Apply multiplicity rules
  10. Select translations
  11. Final block ordering
  12. Build provenance and checksums
"""

from __future__ import annotations

import hashlib
import json
from typing import Any

from .content_objects import (
    ContentObject, ContentObjectRevision, ContentSlot, ApplicabilityRule,
    CompositionBinding, VariantGroup, ContentObjectAlias,
    validate_inheritance_chain, validate_composition_chain,
)
from .rule_evaluator import evaluate_rule


class ResolutionProvenance:
    """Tracks the source of each resolved block."""

    def __init__(self) -> None:
        self.inheritance_paths: list[list[str]] = []
        self.composition_paths: list[list[str]] = []
        self.aliases_followed: list[str] = []
        self.slot_values: dict[str, str] = {}
        self.rules_evaluated: list[dict[str, Any]] = []
        self.variant_decisions: list[dict[str, Any]] = []

    def to_dict(self) -> dict[str, Any]:
        return {
            "inheritance_paths": self.inheritance_paths,
            "composition_paths": self.composition_paths,
            "aliases_followed": self.aliases_followed,
            "slot_values": self.slot_values,
            "rules_evaluated": self.rules_evaluated,
            "variant_decisions": self.variant_decisions,
        }


class ResolvedContentBlock:
    """A single resolved block within the final tree."""

    def __init__(self, block_id: str = "", content: str = "", source_object_id: str = "",
                 source_revision: int = 1, block_type: str = "text",
                 inheritance_path: list[str] | None = None,
                 composition_path: list[str] | None = None,
                 slot_values: dict[str, str] | None = None) -> None:
        self.block_id = block_id
        self.content = content
        self.source_object_id = source_object_id
        self.source_revision = source_revision
        self.block_type = block_type
        self.inheritance_path = inheritance_path or []
        self.composition_path = composition_path or []
        self.slot_values = slot_values or {}

    def to_dict(self) -> dict[str, Any]:
        return {
            "block_id": self.block_id,
            "content": self.content,
            "source_object_id": self.source_object_id,
            "source_revision": self.source_revision,
            "block_type": self.block_type,
            "inheritance_path": self.inheritance_path,
            "composition_path": self.composition_path,
        }


class ResolvedContentTree:
    """The complete deterministic result of content resolution."""

    def __init__(
        self,
        blocks: list[ResolvedContentBlock] | None = None,
        provenance: ResolutionProvenance | None = None,
        translation_selections: list[dict[str, Any]] | None = None,
        config_hash: str = "",
        checksum: str = "",
        warnings: list[str] | None = None,
        errors: list[str] | None = None,
    ) -> None:
        self.blocks = blocks or []
        self.provenance = provenance or ResolutionProvenance()
        self.translation_selections = translation_selections or []
        self.config_hash = config_hash
        self.checksum = checksum
        self.warnings = warnings or []
        self.errors = errors or []

    def to_dict(self) -> dict[str, Any]:
        return {
            "blocks": [b.to_dict() for b in self.blocks],
            "provenance": self.provenance.to_dict(),
            "translation_selections": self.translation_selections,
            "config_hash": self.config_hash,
            "checksum": self.checksum,
            "warnings": self.warnings,
            "errors": self.errors,
        }

    def is_valid(self) -> bool:
        return len(self.errors) == 0

    def compute_checksum(self) -> str:
        raw = json.dumps(self.to_dict(), sort_keys=True, ensure_ascii=False)
        return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def resolve_alias(obj_id: str, aliases: dict[str, str]) -> str:
    """Resolve an object ID through its alias chain. Detects cycles."""
    visited: set[str] = set()
    current = obj_id
    while current in aliases:
        if current in visited:
            raise ValueError(f"Alias cycle detected: {obj_id}")
        visited.add(current)
        current = aliases[current]
    return current


def _compute_config_hash(config_values: dict[str, str]) -> str:
    raw = json.dumps(config_values, sort_keys=True, ensure_ascii=False)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:16]


def resolve_content_tree(
    root_object_ids: list[str],
    objects: dict[str, ContentObject],
    pinned_revisions: dict[str, int] | None = None,
    config_values: dict[str, str] | None = None,
    aliases: dict[str, str] | None = None,
    max_depth: int = 100,
) -> ResolvedContentTree:
    """Deterministically resolve a content tree from root object IDs.

    Args:
        root_object_ids: Ordered list of root content object IDs.
        objects: All available ContentObjects, keyed by ID.
        pinned_revisions: Optional dict of object_id -> revision number to pin.
        config_values: Configuration parameter values for rule evaluation.
        aliases: Dict of old_id -> new_id.
        max_depth: Maximum resolution depth.

    Returns:
        A ``ResolvedContentTree`` with ordered blocks and provenance.
    """
    if pinned_revisions is None:
        pinned_revisions = {}
    if config_values is None:
        config_values = {}
    if aliases is None:
        aliases = {}

    tree = ResolvedContentTree()
    tree.config_hash = _compute_config_hash(config_values)
    visited_composition: dict[str, int] = {}

    def _resolve_one(obj_id: str, depth: int, inh_path: list[str], comp_path: list[str]) -> None:
        if depth > max_depth:
            tree.errors.append(f"Max resolution depth ({max_depth}) exceeded for {obj_id}")
            return

        # Resolve alias
        actual_id = resolve_alias(obj_id, aliases)
        if actual_id != obj_id:
            tree.provenance.aliases_followed.append(f"{obj_id}->{actual_id}")

        obj = objects.get(actual_id)
        if not obj:
            tree.errors.append(f"ContentObject {actual_id} not found")
            return

        rev_num = pinned_revisions.get(actual_id, obj.current_revision)
        rev = obj.get_revision(rev_num) if obj.get_revision(rev_num) else obj.latest_revision()
        if not rev:
            tree.errors.append(f"No revision found for {actual_id}")
            return

        # Resolve base template chain
        if obj.base_template_id and obj.binding and obj.binding.mode in ("derived", "free"):
            base_inh_path = list(inh_path) + [actual_id]
            _resolve_one(obj.base_template_id, depth + 1, base_inh_path, comp_path)

        block = ResolvedContentBlock(
            block_id=actual_id,
            content=rev.canonical_content,
            source_object_id=actual_id,
            source_revision=rev_num,
            block_type=obj.type,
            inheritance_path=list(inh_path) + [actual_id],
            composition_path=list(comp_path),
        )

        # Apply slot values (default first, then override from config)
        for slot in rev.slots:
            val = config_values.get(slot.slot_id, slot.default_value)
            if slot.required and not val:
                tree.errors.append(f"Required slot {slot.slot_id} on {actual_id} has no value")
            block.slot_values[slot.slot_id] = val
            tree.provenance.slot_values[slot.slot_id] = val

        # Evaluate visibility rule
        if rev.visibility_rule:
            try:
                match = evaluate_rule(rev.visibility_rule, config_values)
                tree.provenance.rules_evaluated.append({
                    "rule_id": rev.visibility_rule.rule_id,
                    "result": match,
                })
                if not match:
                    return  # block is hidden
            except ValueError as exc:
                tree.errors.append(f"Rule evaluation error on {actual_id}: {exc}")
                return

        tree.blocks.append(block)

        # Resolve composition
        for comp in rev.composed_objects:
            if not comp.allow_multiple_override:
                count = visited_composition.get(comp.child_object_id, 0)
                if count >= 1:
                    tree.warnings.append(
                        f"Duplicate inclusion of {comp.child_object_id} without multiplicity override"
                    )
                    continue
            visited_composition[comp.child_object_id] = visited_composition.get(comp.child_object_id, 0) + 1

            new_comp_path = list(comp_path) + [comp.child_object_id]
            _resolve_one(comp.child_object_id, depth + 1, inh_path, new_comp_path)

    for root_id in root_object_ids:
        _resolve_one(root_id, 0, [], [])

    tree.checksum = tree.compute_checksum()
    return tree