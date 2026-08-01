"""Integration tests for Phase 6 BuildGraph and ValidationEngine adapters."""

from app.build_graph import BuildGraph
from app.content_build_graph import content_graph_report, extend_build_graph_with_content
from app.content_objects import CompositionBinding, ContentObject, ContentObjectRevision, ContentSlot
from app.content_segment import ContentSegment
from app.phase6_validation import validate_content_domain
from app.translations import TranslationSegment, TranslationVariant


def _object(object_id: str, content: str = "text") -> ContentObject:
    return ContentObject(
        id=object_id,
        type="paragraph",
        section_type="procedure",
        status="approved",
        current_revision=1,
        revisions=[ContentObjectRevision(
            object_id=object_id,
            revision=1,
            canonical_content=content,
            approval_status="approved",
        )],
    )


def test_build_graph_extension_adds_revision_slot_and_composition_nodes():
    parent = _object("parent")
    child = _object("child")
    parent.revisions[0].slots = [ContentSlot(slot_id="duration", type="number")]
    parent.revisions[0].composed_objects = [
        CompositionBinding(
            composition_id="cmp-child",
            child_object_id="child",
            pinned_revision=1,
        )
    ]
    graph = extend_build_graph_with_content(BuildGraph(), {"parent": parent, "child": child})
    assert graph.nodes["content-object:parent"].type == "content-object"
    assert graph.nodes["content-revision:parent@1"].type == "content-revision"
    assert graph.nodes["slot:parent@1:duration"].type == "slot"
    assert graph.nodes["composition:cmp-child"].type == "composition-binding"
    assert any(
        edge.type == "composes"
        and edge.target == "content-revision:child@1"
        for edge in graph.edges
    )


def test_content_graph_report_detects_mixed_cycle():
    a = _object("a")
    b = _object("b")
    c = _object("c")
    a.base_template_id = "b"
    b.revisions[0].composed_objects = [CompositionBinding(child_object_id="c", pinned_revision=1)]
    c.revisions[0].composed_objects = [CompositionBinding(child_object_id="a", pinned_revision=1)]
    report = content_graph_report({"a": a, "b": b, "c": c})
    assert report["error_count"] == 1
    assert report["cycles"][0]["type"] == "mixed-content-cycle"
    assert report["cycles"][0]["path"] == ["a@1", "b@1", "c@1", "a@1"]


def test_validation_engine_returns_exact_slot_and_revision_codes():
    obj = _object("root", "Use {{duration}}")
    obj.revisions[0].slots = [
        ContentSlot(slot_id="duration", type="number", required=True, default_value="")
    ]
    obj.revisions[0].composed_objects = [
        CompositionBinding(child_object_id="missing", pinned_revision=3)
    ]
    result = validate_content_domain({"root": obj})
    codes = [issue.code for issue in result.issues]
    assert codes == ["unresolved-slot", "missing-content-object"]
    assert result.valid is False


def test_validation_engine_integrates_strict_translation_findings():
    obj = _object("root")
    source = [ContentSegment(
        segment_id="s1",
        segment_type="sentence",
        source_text="Use {{analyte}}.",
        source_revision=1,
        order=0,
    )]
    variant = TranslationVariant(
        id="tr-1",
        content_object_id="root",
        canonical_revision=1,
        target_language="en-US",
        revision=1,
        status="approved",
        segment_translations=[TranslationSegment(
            segment_id="s1",
            translated_text="Use analyte.",
            order=0,
        )],
    )
    result = validate_content_domain(
        {"root": obj},
        translations=[(variant, source)],
    )
    assert [issue.code for issue in result.issues] == ["translation-placeholder-mismatch"]
    assert result.to_dict()["error_count"] == 1
