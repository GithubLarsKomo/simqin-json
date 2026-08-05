from app.composition_validation import validate_composition_placements
from app.content_objects import CompositionBinding, ContentObject, ContentObjectRevision
from app.phase6_validation import validate_content_domain


def _binding(cid: str, child: str, placement: str) -> CompositionBinding:
    return CompositionBinding(
        composition_id=cid,
        child_object_id=child,
        pinned_revision=1,
        placement=placement,
    )


def _object(object_id: str, bindings: list[CompositionBinding] | None = None) -> ContentObject:
    return ContentObject(
        id=object_id,
        current_revision=1,
        revisions=[ContentObjectRevision(
            object_id=object_id,
            revision=1,
            canonical_content=object_id,
            composed_objects=bindings or [],
        )],
    )


def test_detects_composition_placement_cycle_with_exact_path():
    bindings = [
        _binding("a", "child-a", "before:child-b"),
        _binding("b", "child-b", "before:child-a"),
    ]
    findings = validate_composition_placements(bindings)
    cycle = next(item for item in findings if item.code == "composition-placement-cycle")
    assert cycle.path == ("a", "b", "a")


def test_detects_missing_anchor():
    findings = validate_composition_placements([
        _binding("a", "child-a", "before:missing"),
    ])
    assert [(item.code, item.anchor) for item in findings] == [
        ("invalid-composition-anchor", "missing")
    ]


def test_detects_ambiguous_anchor():
    findings = validate_composition_placements([
        _binding("a", "same-child", "last"),
        _binding("b", "same-child", "last"),
        _binding("c", "other", "before:same-child"),
    ])
    ambiguous = next(item for item in findings if item.code == "ambiguous-composition-anchor")
    assert ambiguous.path == ("a", "b")


def test_phase6_validation_blocks_placement_cycle():
    parent = _object("parent", [
        _binding("a", "child-a", "before:child-b"),
        _binding("b", "child-b", "before:child-a"),
    ])
    objects = {
        "parent": parent,
        "child-a": _object("child-a"),
        "child-b": _object("child-b"),
    }
    result = validate_content_domain(objects)
    assert result.valid is False
    issue = next(item for item in result.issues if item.code == "composition-placement-cycle")
    assert issue.level == "FATAL"
    assert issue.path == ("a", "b", "a")
