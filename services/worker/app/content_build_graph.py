"""BuildGraph adapter for revision-aware Phase 6 content models.

The existing :mod:`build_graph` remains project/document focused.  This module
adds a deterministic graph projection for ContentObjects without changing
Phase 5 behavior.
"""

from __future__ import annotations

from typing import Any

from .build_graph import BuildGraph, GraphNode
from .content_graph import ContentGraph, ContentGraphEdge, ContentGraphNode
from .content_objects import ContentObject


CONTENT_NODE_TYPES = {
    "content-object",
    "content-revision",
    "content-template",
    "composition-binding",
    "slot",
    "applicability-rule",
    "sentence-segment",
    "content-alias",
}

CONTENT_EDGE_TYPES = {
    "inherits-from",
    "composes",
    "uses-slot",
    "controlled-by",
    "alias-of",
    "pinned-to",
}


def _revision_node_id(object_id: str, revision: int) -> str:
    return f"content-revision:{object_id}@{revision}"


def _segment_id(segment: Any) -> str:
    value = getattr(segment, "segment_id", None)
    if value is not None:
        return str(value)
    if isinstance(segment, dict):
        return str(segment.get("segment_id", ""))
    return ""


def extend_build_graph_with_content(
    graph: BuildGraph,
    objects: dict[str, ContentObject],
    aliases: dict[str, str] | None = None,
) -> BuildGraph:
    """Add Phase 6 content nodes and edges to an existing ``BuildGraph``.

    The operation is deterministic and additive. Existing Phase 5 nodes and
    edges are not modified or removed.
    """
    aliases = aliases or {}
    for object_id in sorted(objects):
        obj = objects[object_id]
        object_node = f"content-object:{object_id}"
        node_type = "content-template" if obj.type == "template" else "content-object"
        graph.add_node(GraphNode(object_node, node_type, object_id, data={
            "status": obj.status,
            "canonical_language": obj.canonical_language,
            "current_revision": obj.current_revision,
        }))

        for revision in sorted(obj.revisions, key=lambda item: item.revision):
            revision_node = _revision_node_id(object_id, revision.revision)
            graph.add_node(GraphNode(revision_node, "content-revision", revision_node, data={
                "object_id": object_id,
                "revision": revision.revision,
                "approval_status": revision.approval_status,
            }))
            graph.add_edge(object_node, revision_node, "pinned-to", str(revision.revision))

            for slot in sorted(revision.slots, key=lambda item: item.slot_id):
                slot_node = f"slot:{object_id}@{revision.revision}:{slot.slot_id}"
                graph.add_node(GraphNode(slot_node, "slot", slot.slot_id, data={"slot_type": slot.type}))
                graph.add_edge(revision_node, slot_node, "uses-slot")

            if revision.visibility_rule:
                rule = revision.visibility_rule
                rule_node = f"rule:{object_id}@{revision.revision}:{rule.rule_id}"
                graph.add_node(GraphNode(rule_node, "applicability-rule", rule.rule_id))
                graph.add_edge(revision_node, rule_node, "controlled-by")

            for segment in revision.sentence_segments:
                segment_id = _segment_id(segment)
                segment_node = f"segment:{object_id}@{revision.revision}:{segment_id}"
                graph.add_node(GraphNode(segment_node, "sentence-segment", segment_id))
                graph.add_edge(revision_node, segment_node, "contains")

            for binding in sorted(revision.composed_objects, key=lambda item: (item.order, item.composition_id)):
                binding_node = f"composition:{binding.composition_id}"
                graph.add_node(GraphNode(binding_node, "composition-binding", binding.composition_id, data={
                    "pinned_revision": binding.pinned_revision,
                    "placement": binding.placement,
                    "order": binding.order,
                }))
                graph.add_edge(revision_node, binding_node, "contains")
                graph.add_edge(
                    binding_node,
                    _revision_node_id(binding.child_object_id, binding.pinned_revision),
                    "composes",
                    binding.composition_id,
                )

        if obj.base_template_id:
            target_revision = obj.binding.detached_from_revision if obj.binding and obj.binding.detached_from_revision else 0
            target = (
                _revision_node_id(obj.base_template_id, target_revision)
                if target_revision
                else f"content-object:{obj.base_template_id}"
            )
            graph.add_edge(object_node, target, "inherits-from")

    for old_id, canonical_id in sorted(aliases.items()):
        alias_node = f"content-alias:{old_id}"
        graph.add_node(GraphNode(alias_node, "content-alias", old_id))
        graph.add_edge(alias_node, f"content-object:{canonical_id}", "alias-of")
    return graph


def build_content_graph(
    objects: dict[str, ContentObject],
    pinned_revisions: dict[str, int] | None = None,
) -> ContentGraph:
    """Create the revision-aware cycle graph used by validation."""
    pinned_revisions = pinned_revisions or {}
    graph = ContentGraph()
    for object_id in sorted(objects):
        obj = objects[object_id]
        revision_number = pinned_revisions.get(object_id, obj.current_revision)
        revision = obj.get_revision(revision_number)
        if revision is None:
            continue
        source = ContentGraphNode(object_id, revision_number)
        graph.add_node(source)
        if obj.base_template_id:
            base = objects.get(obj.base_template_id)
            if base:
                base_revision = pinned_revisions.get(base.id, base.current_revision)
                target = ContentGraphNode(base.id, base_revision)
                graph.add_edge(ContentGraphEdge(source, target, "inherits-from"))
        for binding in revision.composed_objects:
            target = ContentGraphNode(binding.child_object_id, binding.pinned_revision)
            graph.add_edge(ContentGraphEdge(source, target, "composes", binding.composition_id))
    return graph


def content_graph_report(objects: dict[str, ContentObject], pinned_revisions: dict[str, int] | None = None) -> dict[str, Any]:
    graph = build_content_graph(objects, pinned_revisions)
    cycles = graph.find_cycles()
    return {
        "statistics": {
            "content_nodes": len(graph.nodes),
            "content_edges": len(graph.edges),
        },
        "cycles": [cycle.to_dict() for cycle in cycles],
        "error_count": len(cycles),
    }
