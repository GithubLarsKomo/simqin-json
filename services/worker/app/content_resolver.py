"""Deterministic, revision-safe content resolver for IFU content objects.

This module intentionally focuses on Phase 6c.1 concerns: exact revision
selection, graph-cycle detection, inheritance merging, composition ordering,
slot rendering, multiplicity enforcement, provenance and verifiable checksums.
Translation selection and approved configuration-catalog validation remain
extension points for later phases.
"""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass, field
from typing import Any

from .content_graph import ContentGraph, ContentGraphEdge, ContentGraphNode
from .content_objects import (
    CompositionBinding,
    ContentObject,
    ContentObjectRevision,
    ContentSlot,
    MultiplicityRule,
)
from .rule_evaluator import evaluate_rule

REVISION_MODES = {"pinned", "working", "preview"}
MAX_RESOLUTION_DEPTH = 20
_PLACEHOLDER = re.compile(r"\{\{([A-Za-z0-9_.:-]+)\}\}")


def canonical_json(data: Any) -> str:
    return json.dumps(
        data, sort_keys=True, ensure_ascii=False, separators=(",", ":")
    )


def sha256_json(data: Any) -> str:
    return hashlib.sha256(canonical_json(data).encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class ResolutionFinding:
    code: str
    severity: str
    message: str
    object_id: str = ""
    revision: int = 0
    path: tuple[str, ...] = ()
    details: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "code": self.code,
            "severity": self.severity,
            "message": self.message,
            "object_id": self.object_id,
            "revision": self.revision,
            "path": list(self.path),
            "details": self.details,
        }


class ResolutionProvenance:
    def __init__(self, mode: str = "working") -> None:
        self.mode = mode
        self.aliases_followed: list[str] = []
        self.object_revisions_read: list[str] = []
        self.revision_selections: list[dict[str, Any]] = []
        self.inheritance_paths: list[list[str]] = []
        self.composition_paths: list[list[str]] = []
        self.slot_values: dict[str, Any] = {}
        self.rules_evaluated: list[dict[str, Any]] = []
        self.multiplicity_decisions: list[dict[str, Any]] = []
        self.placement_decisions: list[dict[str, Any]] = []
        self.graph_checksum = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "mode": self.mode,
            "aliases_followed": sorted(self.aliases_followed),
            "object_revisions_read": sorted(set(self.object_revisions_read)),
            "revision_selections": sorted(
                self.revision_selections,
                key=lambda item: (
                    item.get("object_id", ""),
                    item.get("revision", 0),
                    item.get("reason", ""),
                ),
            ),
            "inheritance_paths": self.inheritance_paths,
            "composition_paths": self.composition_paths,
            "slot_values": dict(sorted(self.slot_values.items())),
            "rules_evaluated": self.rules_evaluated,
            "multiplicity_decisions": self.multiplicity_decisions,
            "placement_decisions": self.placement_decisions,
            "graph_checksum": self.graph_checksum,
        }


class ResolvedContentBlock:
    def __init__(
        self,
        block_id: str,
        source_template_content: str,
        rendered_content: str,
        source_object_id: str,
        source_revision: int,
        block_type: str,
        inheritance_path: list[str] | None = None,
        composition_path: list[str] | None = None,
        slot_values: dict[str, Any] | None = None,
    ) -> None:
        self.block_id = block_id
        self.source_template_content = source_template_content
        self.rendered_content = rendered_content
        # Backward-compatible alias.
        self.content = rendered_content
        self.source_object_id = source_object_id
        self.source_revision = source_revision
        self.block_type = block_type
        self.inheritance_path = inheritance_path or []
        self.composition_path = composition_path or []
        self.slot_values = slot_values or {}

    def to_dict(self) -> dict[str, Any]:
        return {
            "block_id": self.block_id,
            "content": self.rendered_content,
            "source_template_content": self.source_template_content,
            "rendered_content": self.rendered_content,
            "source_object_id": self.source_object_id,
            "source_revision": self.source_revision,
            "block_type": self.block_type,
            "inheritance_path": self.inheritance_path,
            "composition_path": self.composition_path,
            "slot_values": dict(sorted(self.slot_values.items())),
        }


class ResolvedContentTree:
    def __init__(self, mode: str = "working") -> None:
        self.blocks: list[ResolvedContentBlock] = []
        self.provenance = ResolutionProvenance(mode)
        self.translation_selections: list[dict[str, Any]] = []
        self.config_hash = ""
        self.graph_checksum = ""
        self.checksum = ""
        self.findings: list[ResolutionFinding] = []

    @property
    def warnings(self) -> list[str]:
        return [f.message for f in self.findings if f.severity == "WARNING"]

    @property
    def errors(self) -> list[str]:
        return [
            f.message for f in self.findings if f.severity in {"ERROR", "FATAL"}
        ]

    def is_valid(self) -> bool:
        return not self.errors

    def _checksum_payload(self) -> dict[str, Any]:
        return {
            "blocks": [block.to_dict() for block in self.blocks],
            "provenance": self.provenance.to_dict(),
            "translation_selections": self.translation_selections,
            "config_hash": self.config_hash,
            "graph_checksum": self.graph_checksum,
            "findings": [
                finding.to_dict()
                for finding in sorted(
                    self.findings,
                    key=lambda f: (f.severity, f.code, f.object_id, f.revision, f.path),
                )
            ],
        }

    def compute_checksum(self) -> str:
        return sha256_json(self._checksum_payload())

    def verify_checksum(self) -> bool:
        return bool(self.checksum) and self.checksum == self.compute_checksum()

    def to_dict(self) -> dict[str, Any]:
        payload = self._checksum_payload()
        payload.update(
            {
                "checksum": self.checksum,
                "warnings": self.warnings,
                "errors": self.errors,
            }
        )
        return payload


def resolve_alias(obj_id: str, aliases: dict[str, str]) -> tuple[str, list[str]]:
    visited: list[str] = []
    current = obj_id
    while current in aliases:
        if current in visited:
            cycle = visited[visited.index(current) :] + [current]
            raise ValueError(" -> ".join(cycle))
        visited.append(current)
        current = aliases[current]
    return current, visited + ([current] if visited else [])


def resolve_object_revision(
    obj: ContentObject,
    requested_revision: int | None,
    mode: str,
) -> tuple[ContentObjectRevision | None, str, ResolutionFinding | None]:
    if mode not in REVISION_MODES:
        raise ValueError(f"Unknown resolution mode: {mode}")
    if requested_revision is not None:
        revision = obj.get_revision(requested_revision)
        if revision is None:
            return None, "explicit-pin", ResolutionFinding(
                "missing-content-revision",
                "FATAL",
                f"Pinned revision {requested_revision} not found for {obj.id}",
                obj.id,
                requested_revision,
            )
        return revision, "explicit-pin", None
    if mode == "pinned":
        return None, "missing-pin", ResolutionFinding(
            "missing-revision-pin",
            "FATAL",
            f"Pinned mode requires an explicit revision for {obj.id}",
            obj.id,
        )
    revision = obj.get_revision(obj.current_revision)
    if revision is None:
        return None, "current-revision", ResolutionFinding(
            "invalid-current-revision",
            "FATAL",
            f"Current revision {obj.current_revision} not found for {obj.id}",
            obj.id,
            obj.current_revision,
        )
    reason = "current-working-revision" if mode == "working" else "preview-current-revision"
    finding = None
    if mode == "preview":
        finding = ResolutionFinding(
            "preview-unpinned-revision",
            "WARNING",
            f"Preview resolved unpinned current revision {obj.current_revision} for {obj.id}",
            obj.id,
            obj.current_revision,
        )
    return revision, reason, finding


def _merge_slots(base: list[ContentSlot], child: list[ContentSlot]) -> list[ContentSlot]:
    merged = {slot.slot_id: slot for slot in base}
    merged.update({slot.slot_id: slot for slot in child})
    return [merged[key] for key in sorted(merged)]


def _merge_revisions(
    base: ContentObjectRevision | None, child: ContentObjectRevision
) -> ContentObjectRevision:
    if base is None:
        return child
    return ContentObjectRevision(
        object_id=child.object_id,
        revision=child.revision,
        canonical_content=child.canonical_content or base.canonical_content,
        sentence_segments=child.sentence_segments or base.sentence_segments,
        slots=_merge_slots(base.slots, child.slots),
        visibility_rule=child.visibility_rule or base.visibility_rule,
        composed_objects=sorted(
            [*base.composed_objects, *child.composed_objects],
            key=lambda binding: (binding.order, binding.composition_id),
        ),
        created_at=child.created_at,
        created_by=child.created_by,
        approval_status=child.approval_status,
    )


def _render_template(
    template: str,
    slots: list[ContentSlot],
    supplied: dict[str, Any],
    tree: ResolvedContentTree,
    object_id: str,
    revision: int,
) -> tuple[str, dict[str, Any]]:
    definitions = {slot.slot_id: slot for slot in slots}
    values: dict[str, Any] = {}
    for slot_id, slot in definitions.items():
        value = supplied.get(slot_id, slot.default_value)
        if slot.required and (value is None or value == ""):
            tree.findings.append(
                ResolutionFinding(
                    "unresolved-required-slot",
                    "FATAL",
                    f"Required slot {slot_id} has no value",
                    object_id,
                    revision,
                )
            )
        values[slot_id] = value
        tree.provenance.slot_values[f"{object_id}@{revision}:{slot_id}"] = value

    def replace(match: re.Match[str]) -> str:
        slot_id = match.group(1)
        if slot_id not in definitions:
            tree.findings.append(
                ResolutionFinding(
                    "unknown-slot-placeholder",
                    "WARNING",
                    f"Unknown slot placeholder {slot_id} in {object_id}@{revision}",
                    object_id,
                    revision,
                )
            )
            return match.group(0)
        value = values.get(slot_id)
        return "" if value is None else str(value)

    return _PLACEHOLDER.sub(replace, template), values


def _approved_multiple_rule(
    object_id: str, rules: list[MultiplicityRule]
) -> MultiplicityRule | None:
    candidates = [
        rule
        for rule in rules
        if rule.object_id == object_id
        and rule.status == "approved"
        and rule.mode == "multiple"
    ]
    return max(candidates, key=lambda rule: rule.revision) if candidates else None


def _ordered_compositions(
    parent_id: str,
    bindings: list[CompositionBinding],
    tree: ResolvedContentTree,
) -> list[CompositionBinding]:
    first = sorted(
        [item for item in bindings if item.placement == "first"],
        key=lambda item: (item.order, item.composition_id),
    )
    last = sorted(
        [item for item in bindings if item.placement == "last"],
        key=lambda item: (item.order, item.composition_id),
    )
    anchored = sorted(
        [
            item
            for item in bindings
            if item.placement.startswith("before:")
            or item.placement.startswith("after:")
        ],
        key=lambda item: (item.order, item.composition_id),
    )
    invalid = [
        item
        for item in bindings
        if item not in first and item not in last and item not in anchored
    ]
    for item in invalid:
        tree.findings.append(
            ResolutionFinding(
                "invalid-composition-anchor",
                "FATAL",
                f"Invalid placement {item.placement!r} on {item.composition_id}",
                parent_id,
                details={"composition_id": item.composition_id},
            )
        )
    # Anchors refer to sibling child IDs. Build a deterministic constraint order.
    ordered = first + last
    for item in anchored:
        anchor = item.placement.split(":", 1)[1]
        positions = [
            index for index, candidate in enumerate(ordered) if candidate.child_object_id == anchor
        ]
        if len(positions) != 1:
            tree.findings.append(
                ResolutionFinding(
                    "invalid-composition-anchor",
                    "FATAL",
                    f"Anchor {anchor!r} is missing or ambiguous for {item.composition_id}",
                    parent_id,
                    details={"composition_id": item.composition_id, "anchor": anchor},
                )
            )
            continue
        index = positions[0] + (1 if item.placement.startswith("after:") else 0)
        ordered.insert(index, item)
    for index, item in enumerate(ordered):
        tree.provenance.placement_decisions.append(
            {
                "parent_id": parent_id,
                "composition_id": item.composition_id,
                "placement": item.placement,
                "final_index": index,
            }
        )
    return ordered


def resolve_content_tree(
    root_object_ids: list[str],
    objects: dict[str, ContentObject],
    pinned_revisions: dict[str, int] | None = None,
    config_values: dict[str, Any] | None = None,
    aliases: dict[str, str] | None = None,
    max_depth: int = MAX_RESOLUTION_DEPTH,
    revision_mode: str = "working",
    multiplicity_rules: list[MultiplicityRule] | None = None,
) -> ResolvedContentTree:
    if revision_mode not in REVISION_MODES:
        raise ValueError(f"Unknown resolution mode: {revision_mode}")
    pins = pinned_revisions or {}
    config = config_values or {}
    alias_map = aliases or {}
    rules = multiplicity_rules or []
    tree = ResolvedContentTree(revision_mode)
    tree.config_hash = sha256_json(config)
    graph = ContentGraph()
    occurrences: dict[str, int] = {}
    active: list[ContentGraphNode] = []

    def add_finding(finding: ResolutionFinding | None) -> None:
        if finding is not None:
            tree.findings.append(finding)

    def select_revision(
        requested_id: str,
        requested_revision: int | None,
        reason_override: str | None = None,
    ) -> tuple[str, ContentObject | None, ContentObjectRevision | None]:
        try:
            actual_id, alias_path = resolve_alias(requested_id, alias_map)
        except ValueError as exc:
            tree.findings.append(
                ResolutionFinding(
                    "alias-cycle",
                    "FATAL",
                    f"Alias cycle detected: {exc}",
                    requested_id,
                )
            )
            return requested_id, None, None
        if actual_id != requested_id:
            tree.provenance.aliases_followed.append(" -> ".join(alias_path))
        obj = objects.get(actual_id)
        if obj is None:
            tree.findings.append(
                ResolutionFinding(
                    "missing-content-object",
                    "FATAL",
                    f"ContentObject {actual_id} not found",
                    actual_id,
                )
            )
            return actual_id, None, None
        revision, reason, finding = resolve_object_revision(
            obj, requested_revision, revision_mode
        )
        add_finding(finding)
        if revision is not None:
            reason = reason_override or reason
            tree.provenance.object_revisions_read.append(
                f"{actual_id}@{revision.revision}"
            )
            tree.provenance.revision_selections.append(
                {
                    "requested_id": requested_id,
                    "object_id": actual_id,
                    "revision": revision.revision,
                    "reason": reason,
                }
            )
        return actual_id, obj, revision

    def resolve_inheritance(
        obj: ContentObject,
        revision: ContentObjectRevision,
        depth: int,
        path: list[str],
    ) -> tuple[ContentObjectRevision, list[str]]:
        current = ContentGraphNode(obj.id, revision.revision)
        if depth > max_depth:
            tree.findings.append(
                ResolutionFinding(
                    "max-resolution-depth",
                    "FATAL",
                    f"Maximum resolution depth {max_depth} exceeded",
                    obj.id,
                    revision.revision,
                    tuple(path),
                )
            )
            return revision, path
        if not obj.base_template_id or not obj.binding:
            return revision, path + [current.key]
        if obj.binding.mode == "proposed" and revision_mode == "pinned":
            tree.findings.append(
                ResolutionFinding(
                    "proposed-binding-not-releasable",
                    "FATAL",
                    f"Proposed binding cannot be resolved in pinned mode: {obj.id}",
                    obj.id,
                    revision.revision,
                )
            )
            return revision, path + [current.key]
        base_pin = pins.get(obj.base_template_id)
        base_id, base_obj, base_revision = select_revision(
            obj.base_template_id, base_pin, "base-template-pin" if base_pin else None
        )
        if base_obj is None or base_revision is None:
            return revision, path + [current.key]
        base_node = ContentGraphNode(base_id, base_revision.revision)
        graph.add_edge(
            ContentGraphEdge(current, base_node, "inherits-from", obj.binding.base_template_id)
        )
        if base_node in active:
            return revision, path + [current.key, base_node.key]
        active.append(current)
        merged_base, inherited_path = resolve_inheritance(
            base_obj, base_revision, depth + 1, path + [current.key]
        )
        active.pop()
        tree.provenance.inheritance_paths.append(inherited_path)
        if obj.binding.mode == "free":
            # A free variant keeps its own text but inherits missing structural definitions.
            structural_child = ContentObjectRevision(
                object_id=revision.object_id,
                revision=revision.revision,
                canonical_content=revision.canonical_content,
                sentence_segments=revision.sentence_segments,
                slots=revision.slots,
                visibility_rule=revision.visibility_rule,
                composed_objects=revision.composed_objects,
                created_at=revision.created_at,
                created_by=revision.created_by,
                approval_status=revision.approval_status,
            )
            return _merge_revisions(merged_base, structural_child), inherited_path
        return _merge_revisions(merged_base, revision), inherited_path

    def resolve_one(
        requested_id: str,
        requested_revision: int | None,
        depth: int,
        composition_path: list[str],
        revision_reason: str | None = None,
    ) -> list[ResolvedContentBlock]:
        actual_id, obj, revision = select_revision(
            requested_id, requested_revision, revision_reason
        )
        if obj is None or revision is None:
            return []
        node = ContentGraphNode(actual_id, revision.revision)
        if node in active:
            return []
        active.append(node)
        merged, inheritance_path = resolve_inheritance(obj, revision, depth, [])

        if merged.visibility_rule:
            try:
                visible = evaluate_rule(merged.visibility_rule, config)
                tree.provenance.rules_evaluated.append(
                    {
                        "rule_id": merged.visibility_rule.rule_id,
                        "object_id": actual_id,
                        "revision": revision.revision,
                        "result": visible,
                    }
                )
                if not visible:
                    active.pop()
                    return []
            except ValueError as exc:
                tree.findings.append(
                    ResolutionFinding(
                        "invalid-condition",
                        "FATAL",
                        f"Rule evaluation failed: {exc}",
                        actual_id,
                        revision.revision,
                    )
                )
                active.pop()
                return []

        rendered, slot_values = _render_template(
            merged.canonical_content,
            merged.slots,
            config,
            tree,
            actual_id,
            revision.revision,
        )
        parent = ResolvedContentBlock(
            block_id=actual_id,
            source_template_content=merged.canonical_content,
            rendered_content=rendered,
            source_object_id=actual_id,
            source_revision=revision.revision,
            block_type=obj.type,
            inheritance_path=inheritance_path,
            composition_path=list(composition_path),
            slot_values=slot_values,
        )
        blocks = [parent]

        for binding in _ordered_compositions(actual_id, merged.composed_objects, tree):
            global_pin = pins.get(binding.child_object_id)
            if global_pin is not None and global_pin != binding.pinned_revision:
                tree.findings.append(
                    ResolutionFinding(
                        "conflicting-revision-pin",
                        "FATAL",
                        f"Global pin {global_pin} conflicts with composition pin "
                        f"{binding.pinned_revision} for {binding.child_object_id}",
                        binding.child_object_id,
                        binding.pinned_revision,
                        details={"composition_id": binding.composition_id},
                    )
                )
                continue
            child_id, child_obj, child_revision = select_revision(
                binding.child_object_id,
                binding.pinned_revision,
                "composition-pin",
            )
            if child_obj is None or child_revision is None:
                continue
            child_node = ContentGraphNode(child_id, child_revision.revision)
            graph.add_edge(
                ContentGraphEdge(node, child_node, "composes", binding.composition_id)
            )
            if child_node in active:
                continue
            occurrences[child_id] = occurrences.get(child_id, 0) + 1
            count = occurrences[child_id]
            if count > 1:
                rule = _approved_multiple_rule(child_id, rules)
                if rule is None:
                    tree.findings.append(
                        ResolutionFinding(
                            "duplicate-content-inclusion",
                            "FATAL",
                            f"Duplicate inclusion of {child_id} requires an approved multiplicity rule",
                            child_id,
                            child_revision.revision,
                        )
                    )
                    continue
                if rule.max_occurrences and count > rule.max_occurrences:
                    tree.findings.append(
                        ResolutionFinding(
                            "multiplicity-limit-exceeded",
                            "FATAL",
                            f"Multiplicity limit {rule.max_occurrences} exceeded for {child_id}",
                            child_id,
                            child_revision.revision,
                        )
                    )
                    continue
                tree.provenance.multiplicity_decisions.append(
                    {
                        "object_id": child_id,
                        "rule_revision": rule.revision,
                        "occurrence": count,
                    }
                )
            child_path = composition_path + [
                f"{actual_id}@{revision.revision}:{binding.composition_id}",
                child_node.key,
            ]
            tree.provenance.composition_paths.append(child_path)
            blocks.extend(
                resolve_one(
                    child_id,
                    binding.pinned_revision,
                    depth + 1,
                    child_path,
                    "composition-pin",
                )
            )
        active.pop()
        return blocks

    for root_id in root_object_ids:
        requested = pins.get(root_id)
        tree.blocks.extend(resolve_one(root_id, requested, 0, []))

    for cycle in graph.find_cycles():
        tree.findings.append(
            ResolutionFinding(
                cycle.cycle_type,
                "FATAL",
                f"Content graph cycle detected: {' -> '.join(node.key for node in cycle.nodes)}",
                path=tuple(node.key for node in cycle.nodes),
                details={"edge_types": list(cycle.edge_types)},
            )
        )

    tree.graph_checksum = graph.checksum()
    tree.provenance.graph_checksum = tree.graph_checksum
    tree.findings.sort(
        key=lambda item: (item.severity, item.code, item.object_id, item.revision, item.path)
    )
    tree.checksum = tree.compute_checksum()
    return tree
