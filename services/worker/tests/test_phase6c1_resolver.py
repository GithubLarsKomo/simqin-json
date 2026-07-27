"""Behavioral tests for Phase 6c.1 resolver hardening."""

from __future__ import annotations

from app.content_graph import ContentGraph, ContentGraphEdge, ContentGraphNode
from app.content_objects import (
    CompositionBinding,
    ContentBinding,
    ContentObject,
    ContentObjectRevision,
    ContentSlot,
    MultiplicityRule,
)
from app.content_resolver import resolve_content_tree, resolve_object_revision


def _object(
    object_id: str,
    revisions: list[tuple[int, str]],
    *,
    current: int | None = None,
    base: str | None = None,
    mode: str = "derived",
) -> ContentObject:
    obj = ContentObject(
        id=object_id,
        type="paragraph",
        section_type="procedure",
        current_revision=current or revisions[-1][0],
        base_template_id=base,
        binding=ContentBinding(base_template_id=base or "", mode=mode) if base else None,
    )
    obj.revisions = [
        ContentObjectRevision(
            object_id=object_id,
            revision=revision,
            canonical_content=content,
            approval_status="approved",
        )
        for revision, content in revisions
    ]
    return obj


def test_missing_explicit_pin_never_falls_back_to_latest():
    obj = _object("a", [(1, "old"), (2, "new")], current=2)
    revision, reason, finding = resolve_object_revision(obj, 99, "working")
    assert revision is None
    assert reason == "explicit-pin"
    assert finding is not None
    assert finding.code == "missing-content-revision"


def test_pinned_mode_requires_every_root_pin():
    obj = _object("a", [(1, "text")])
    result = resolve_content_tree(["a"], {"a": obj}, revision_mode="pinned")
    assert not result.is_valid()
    assert [item.code for item in result.findings] == ["missing-revision-pin"]


def test_composition_binding_revision_is_authoritative():
    child = _object("child", [(1, "one"), (2, "two")], current=2)
    parent = _object("parent", [(1, "parent")])
    parent.revisions[0].composed_objects = [
        CompositionBinding(
            composition_id="cmp-child",
            child_object_id="child",
            pinned_revision=1,
        )
    ]
    result = resolve_content_tree(["parent"], {"parent": parent, "child": child})
    assert result.is_valid()
    assert [(block.source_object_id, block.source_revision) for block in result.blocks] == [
        ("parent", 1),
        ("child", 1),
    ]
    assert result.blocks[1].rendered_content == "one"


def test_conflicting_global_and_composition_pins_are_blocking():
    child = _object("child", [(1, "one"), (2, "two")])
    parent = _object("parent", [(1, "parent")])
    parent.revisions[0].composed_objects = [
        CompositionBinding(child_object_id="child", pinned_revision=1)
    ]
    result = resolve_content_tree(
        ["parent"],
        {"parent": parent, "child": child},
        pinned_revisions={"child": 2},
    )
    assert "conflicting-revision-pin" in [item.code for item in result.findings]


def test_resolution_checksum_excludes_itself_and_verifies():
    obj = _object("a", [(1, "stable")])
    result = resolve_content_tree(["a"], {"a": obj})
    assert result.checksum == result.compute_checksum()
    assert result.verify_checksum()
    original = result.checksum
    result.blocks[0].rendered_content = "tampered"
    assert not result.verify_checksum()
    assert result.compute_checksum() != original


def test_dictionary_insertion_order_does_not_change_checksum():
    a = _object("a", [(1, "A")])
    b = _object("b", [(1, "B")])
    first = resolve_content_tree(["a", "b"], {"a": a, "b": b})
    second = resolve_content_tree(["a", "b"], {"b": b, "a": a})
    assert first.to_dict() == second.to_dict()
    assert first.checksum == second.checksum


def test_slot_defaults_and_overrides_are_rendered():
    obj = _object("a", [(1, "Incubate for {{duration}} min")])
    obj.revisions[0].slots = [
        ContentSlot(slot_id="duration", type="number", required=True, default_value="30")
    ]
    default = resolve_content_tree(["a"], {"a": obj})
    override = resolve_content_tree(["a"], {"a": obj}, config_values={"duration": 45})
    assert default.blocks[0].rendered_content == "Incubate for 30 min"
    assert override.blocks[0].rendered_content == "Incubate for 45 min"
    assert override.blocks[0].to_dict()["slot_values"] == {"duration": 45}


def test_duplicate_inclusion_is_not_a_cycle_and_requires_rule():
    shared = _object("shared", [(1, "shared")])
    left = _object("left", [(1, "left")])
    right = _object("right", [(1, "right")])
    root = _object("root", [(1, "root")])
    left.revisions[0].composed_objects = [
        CompositionBinding(composition_id="left-shared", child_object_id="shared", pinned_revision=1)
    ]
    right.revisions[0].composed_objects = [
        CompositionBinding(composition_id="right-shared", child_object_id="shared", pinned_revision=1)
    ]
    root.revisions[0].composed_objects = [
        CompositionBinding(composition_id="root-left", child_object_id="left", pinned_revision=1, order=1),
        CompositionBinding(composition_id="root-right", child_object_id="right", pinned_revision=1, order=2),
    ]
    objects = {item.id: item for item in [root, left, right, shared]}
    result = resolve_content_tree(["root"], objects)
    codes = [item.code for item in result.findings]
    assert "duplicate-content-inclusion" in codes
    assert "composition-cycle" not in codes
    assert "mixed-content-cycle" not in codes

    allowed = resolve_content_tree(
        ["root"],
        objects,
        multiplicity_rules=[
            MultiplicityRule(
                object_id="shared",
                mode="multiple",
                max_occurrences=2,
                revision=1,
                status="approved",
            )
        ],
    )
    assert "duplicate-content-inclusion" not in [item.code for item in allowed.findings]
    assert [block.source_object_id for block in allowed.blocks].count("shared") == 2


def test_content_graph_detects_mixed_cycle_with_exact_path():
    a = ContentGraphNode("a", 1)
    b = ContentGraphNode("b", 2)
    c = ContentGraphNode("c", 3)
    graph = ContentGraph()
    graph.add_edge(ContentGraphEdge(a, b, "inherits-from"))
    graph.add_edge(ContentGraphEdge(b, c, "composes"))
    graph.add_edge(ContentGraphEdge(c, a, "composes"))
    cycles = graph.find_cycles()
    assert len(cycles) == 1
    assert cycles[0].cycle_type == "mixed-content-cycle"
    assert [node.key for node in cycles[0].nodes] == ["a@1", "b@2", "c@3", "a@1"]


def test_diamond_graph_is_not_a_cycle():
    a = ContentGraphNode("a", 1)
    b = ContentGraphNode("b", 1)
    c = ContentGraphNode("c", 1)
    d = ContentGraphNode("d", 1)
    graph = ContentGraph()
    graph.add_edge(ContentGraphEdge(a, b, "composes"))
    graph.add_edge(ContentGraphEdge(a, c, "composes"))
    graph.add_edge(ContentGraphEdge(b, d, "composes"))
    graph.add_edge(ContentGraphEdge(c, d, "composes"))
    assert graph.find_cycles() == []


def test_composition_order_uses_order_then_stable_id():
    parent = _object("parent", [(1, "parent")])
    a = _object("a", [(1, "A")])
    b = _object("b", [(1, "B")])
    parent.revisions[0].composed_objects = [
        CompositionBinding(
            composition_id="z-binding",
            child_object_id="b",
            pinned_revision=1,
            placement="last",
            order=10,
        ),
        CompositionBinding(
            composition_id="a-binding",
            child_object_id="a",
            pinned_revision=1,
            placement="last",
            order=10,
        ),
    ]
    result = resolve_content_tree(
        ["parent"], {"parent": parent, "a": a, "b": b}
    )
    assert [block.source_object_id for block in result.blocks] == ["parent", "a", "b"]
