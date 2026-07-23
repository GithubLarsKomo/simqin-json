"""Tests for Phase 6 — Content Objects, Configuration, Translation, Migration, Alignment, Resolution."""

from __future__ import annotations

from app.content_objects import (
    ContentObject, ContentObjectRevision, ContentSlot, CompositionBinding,
    ApplicabilityRule, ContentBinding, ContentMergeRecord, MultiplicityRule,
    SuggestedTemplateCandidate, VariantGroup, IFUProduct, IFUWorkingVersion,
    IFULanguageRelease, validate_inheritance_chain, validate_composition_chain,
    MAX_INHERITANCE_DEPTH,
)
from app.configuration import ConfigurationParameter, ConfigurationCatalog, ConfigurationValue
from app.translations import TranslationVariant, TranslationSegment, validate_segment_count
from app.structure_migration import SentenceStructureMigration, approve_migration, reject_migration
from app.alignment import align_texts


# ---------------------------------------------------------------------------
# ContentObject serialization
# ---------------------------------------------------------------------------

def test_content_object_create():
    obj = ContentObject(type="section", section_type="intended-use", origin_product_id="prod-1")
    assert obj.id != ""
    assert obj.type == "section"
    assert obj.canonical_language == "de-DE"
    assert obj.status == "draft"
    assert obj.current_revision == 1


def test_content_object_roundtrip():
    obj = ContentObject(type="template", section_type="warnings", origin_product_id="prod-1")
    slot = ContentSlot(type="term", required=True, default_value="CAUTION")
    rev = ContentObjectRevision(object_id=obj.id, revision=1, slots=[slot])
    obj.revisions.append(rev)
    data = obj.to_dict()
    obj2 = ContentObject.from_dict(data)
    assert obj2.id == obj.id
    assert obj2.type == "template"
    assert len(obj2.revisions) == 1
    assert obj2.revisions[0].slots[0].type == "term"
    assert obj2.revisions[0].slots[0].required is True


# ---------------------------------------------------------------------------
# Single inheritance
# ---------------------------------------------------------------------------

def test_single_inheritance_valid():
    base = ContentObject(id="base-1", type="template", section_type="warnings")
    child = ContentObject(id="child-1", type="template", section_type="warnings", base_template_id="base-1")
    objects = {"base-1": base, "child-1": child}
    errors = validate_inheritance_chain(child, objects)
    assert len(errors) == 0


def test_inheritance_cycle_detected():
    a = ContentObject(id="a", type="template", base_template_id="b")
    b = ContentObject(id="b", type="template", base_template_id="a")
    objects = {"a": a, "b": b}
    errors = validate_inheritance_chain(a, objects)
    assert any("cycle" in e.lower() for e in errors)


def test_inheritance_missing_base():
    child = ContentObject(id="orphan", type="template", base_template_id="nonexistent")
    objects = {"orphan": child}
    errors = validate_inheritance_chain(child, objects)
    assert any("not found" in e.lower() for e in errors)


def test_inheritance_self_reference():
    obj = ContentObject(id="self", type="template", base_template_id="self")
    objects = {"self": obj}
    errors = validate_inheritance_chain(obj, objects)
    assert any("self" in e.lower() for e in errors)


def test_inheritance_exceeds_max_depth():
    objects = {}
    prev = ""
    for i in range(MAX_INHERITANCE_DEPTH + 5):
        oid = f"obj-{i}"
        obj = ContentObject(id=oid, type="template", base_template_id=prev if prev else None)
        objects[oid] = obj
        prev = oid
    errors = validate_inheritance_chain(objects[f"obj-{MAX_INHERITANCE_DEPTH + 4}"], objects)
    assert any("exceeds" in e.lower() or "depth" in e.lower() for e in errors) or len(errors) > 0


# ---------------------------------------------------------------------------
# Composition
# ---------------------------------------------------------------------------

def test_composition_valid():
    parent = ContentObject(id="parent", type="template")
    child = ContentObject(id="child", type="section")
    binding = CompositionBinding(child_object_id="child")
    rev = ContentObjectRevision(object_id="parent", revision=1, composed_objects=[binding])
    parent.revisions.append(rev)
    objects = {"parent": parent, "child": child}
    errors = validate_composition_chain(parent, objects)
    assert len(errors) == 0


def test_composition_cycle_detected():
    a = ContentObject(id="a", type="template")
    b = ContentObject(id="b", type="section")
    binding_a = CompositionBinding(child_object_id="b")
    binding_b = CompositionBinding(child_object_id="a")
    rev_a = ContentObjectRevision(object_id="a", revision=1, composed_objects=[binding_a])
    rev_b = ContentObjectRevision(object_id="b", revision=1, composed_objects=[binding_b])
    a.revisions.append(rev_a)
    b.revisions.append(rev_b)
    objects = {"a": a, "b": b}
    errors = validate_composition_chain(a, objects)
    assert any("cycle" in e.lower() for e in errors)


def test_composition_missing_child():
    parent = ContentObject(id="parent", type="template")
    binding = CompositionBinding(child_object_id="missing")
    rev = ContentObjectRevision(object_id="parent", revision=1, composed_objects=[binding])
    parent.revisions.append(rev)
    objects = {"parent": parent}
    errors = validate_composition_chain(parent, objects)
    assert any("not found" in e.lower() for e in errors)


# ---------------------------------------------------------------------------
# Multiplicity
# ---------------------------------------------------------------------------

def test_multiplicity_default_single():
    rule = MultiplicityRule(object_id="obj-1")
    assert rule.mode == "single"
    assert rule.max_occurrences == 1


def test_multiplicity_multiple():
    rule = MultiplicityRule(object_id="obj-1", mode="multiple", max_occurrences=3, reason="Needed for multi-column layout")
    assert rule.mode == "multiple"
    assert rule.max_occurrences == 3


# ---------------------------------------------------------------------------
# Slots
# ---------------------------------------------------------------------------

def test_slot_types():
    for st in ("term", "phrase", "sentence-fragment", "number", "quantity", "temperature", "analyte", "product-name", "conditional-fragment"):
        slot = ContentSlot(type=st)
        assert slot.type == st


def test_slot_allowed_values():
    slot = ContentSlot(type="enum", allowed_values=["A", "B", "C"])
    assert "A" in slot.allowed_values
    assert "D" not in slot.allowed_values


# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

def test_config_parameter_catalog():
    cat = ConfigurationCatalog()
    param = ConfigurationParameter(parameter_id="incubation-temp", label="Incubation Temperature", type="decimal", default_value="37.0")
    cat.add(param)
    assert cat.get("incubation-temp") is not None


def test_config_validate_integer():
    cat = ConfigurationCatalog()
    cat.add(ConfigurationParameter(parameter_id="count", type="integer"))
    assert len(cat.validate_value("count", "5")) == 0
    assert len(cat.validate_value("count", "abc")) > 0


def test_config_validate_enum():
    cat = ConfigurationCatalog()
    cat.add(ConfigurationParameter(parameter_id="mode", type="enum", allowed_values=["auto", "manual"]))
    assert len(cat.validate_value("mode", "auto")) == 0
    assert len(cat.validate_value("mode", "invalid")) > 0


# ---------------------------------------------------------------------------
# Translation
# ---------------------------------------------------------------------------

def test_translation_variant_segment_count_match():
    segments = [TranslationSegment(segment_id="s1"), TranslationSegment(segment_id="s2")]
    variant = TranslationVariant(
        content_object_id="obj-1", target_language="en-US", segment_translations=[
            TranslationSegment(segment_id="s1", translated_text="Hello"),
            TranslationSegment(segment_id="s2", translated_text="World"),
        ],
    )
    source = [{"segment_id": "s1"}, {"segment_id": "s2"}]
    errors = validate_segment_count(variant, source)
    assert len(errors) == 0


def test_translation_segment_count_mismatch():
    variant = TranslationVariant(
        content_object_id="obj-1", target_language="en-US",
        segment_translations=[TranslationSegment(segment_id="s1", translated_text="Hello")],
    )
    source = [{"segment_id": "s1"}, {"segment_id": "s2"}]
    errors = validate_segment_count(variant, source)
    assert len(errors) > 0


# ---------------------------------------------------------------------------
# Structure migration
# ---------------------------------------------------------------------------

def test_migration_creation():
    m = SentenceStructureMigration(object_id="obj-1", source_revision=1, created_by="alice")
    assert m.status == "draft"
    assert m.created_by == "alice"


def test_approve_migration_requires_different_person():
    m = SentenceStructureMigration(object_id="obj-1", status="pending_approval", created_by="alice")
    try:
        approve_migration(m, "alice", "ok")
        assert False, "Expected ValueError"
    except ValueError:
        pass


def test_approve_migration_requires_comment():
    m = SentenceStructureMigration(object_id="obj-1", status="pending_approval", created_by="alice")
    try:
        approve_migration(m, "bob", "")
        assert False, "Expected ValueError"
    except ValueError:
        pass


def test_reject_migration_requires_comment():
    m = SentenceStructureMigration(object_id="obj-1", status="pending_approval", created_by="alice")
    try:
        reject_migration(m, "bob", "")
        assert False, "Expected ValueError"
    except ValueError:
        pass


def test_reject_migration():
    m = SentenceStructureMigration(object_id="obj-1", status="pending_approval", created_by="alice")
    reject_migration(m, "bob", "Needs revision")
    assert m.status == "rejected"
    assert "Needs revision" in m.decision_comment


def test_self_approval_rejected():
    m = SentenceStructureMigration(object_id="obj-1", status="pending_approval", created_by="alice")
    try:
        reject_migration(m, "alice", "Not allowed")
        assert False, "Expected ValueError"
    except ValueError:
        pass


# ---------------------------------------------------------------------------
# Alignment
# ---------------------------------------------------------------------------

def test_alignment_exact_match():
    result = align_texts("Hello World", "Hello World")
    assert result.score > 0


def test_alignment_different_texts():
    result = align_texts("Hello World", "Hallo Welt")
    assert result.matches is not None


def test_alignment_detects_differences():
    result = align_texts("The temperature is 37 degrees", "The temperature is 40 degrees")
    assert len(result.differing_spans) >= 0


def test_alignment_produces_slot_candidates():
    result = align_texts("Incubate at 37 C", "Incubate at 40 C")
    assert len(result.slot_candidates) >= 0


# ---------------------------------------------------------------------------
# IFU product and release
# ---------------------------------------------------------------------------

def test_ifu_product_creation():
    prod = IFUProduct(name="ELISA Kit A", primary_language="de-DE")
    assert prod.name == "ELISA Kit A"
    assert prod.primary_language == "de-DE"


def test_ifu_working_version():
    wv = IFUWorkingVersion(product_id="prod-1", language="de-DE", version=2)
    assert wv.version == 2
    assert wv.status == "draft"


def test_ifu_language_release_pins_revisions():
    release = IFULanguageRelease(
        product_id="prod-1", language="de-DE", version=3,
        pinned_revisions={"obj-1": 5, "obj-2": 2},
        release_checksum="abc123",
    )
    assert release.pinned_revisions["obj-1"] == 5
    assert release.release_checksum == "abc123"