"""Behavioral tests for typed slots, strict translations and release creation."""

from app.configuration import ConfigurationCatalog, ConfigurationParameter, ConfigurationValue
from app.content_objects import ContentObject, ContentObjectRevision, ContentSlot
from app.content_resolver import resolve_content_tree
from app.release_builder import ReleaseBuildError, build_language_release_snapshot
from app.slot_validation import validate_slot_value
from app.translation_validation import (
    TranslationSelection,
    select_translation_variant,
    validate_translation_variant,
)
from app.translations import TranslationSegment, TranslationVariant


def test_quantity_and_range_slot_validation():
    quantity = ContentSlot(slot_id="volume", type="quantity", required=True, allowed_units=["mL"])
    assert validate_slot_value(quantity, {"value": 2.5, "unit": "mL"}) == []
    assert [item.code for item in validate_slot_value(quantity, {"value": 2.5, "unit": "L"})] == ["invalid-slot-unit"]

    range_slot = ContentSlot(slot_id="range", type="range")
    assert validate_slot_value(range_slot, {"lower": 1, "upper": 3}) == []
    assert [item.code for item in validate_slot_value(range_slot, {"lower": 4, "upper": 3})] == ["invalid-slot-range"]


def test_percentage_slot_is_bounded():
    slot = ContentSlot(slot_id="cutoff", type="percentage")
    assert validate_slot_value(slot, 42) == []
    assert [item.code for item in validate_slot_value(slot, 101)] == ["invalid-slot-value"]


def _source_segments():
    return [
        {"segment_id": "s1", "segment_type": "sentence", "source_text": "Use {{sample}}.", "order": 0},
        {"segment_id": "s2", "segment_type": "sentence", "source_text": "Incubate.", "order": 1},
    ]


def test_strict_translation_accepts_exact_one_to_one_mapping():
    variant = TranslationVariant(
        id="v1", content_object_id="obj", canonical_revision=3,
        target_language="en-US", revision=2, status="approved",
        segment_translations=[
            TranslationSegment(segment_id="s1", translated_text="Use {{sample}}.", order=0),
            TranslationSegment(segment_id="s2", translated_text="Incubate.", order=1),
        ],
    )
    assert validate_translation_variant(variant, _source_segments()) == []


def test_strict_translation_rejects_reordering_and_placeholder_loss():
    variant = TranslationVariant(
        id="v1", content_object_id="obj", canonical_revision=3,
        target_language="en-US", revision=2, status="approved",
        segment_translations=[
            TranslationSegment(segment_id="s2", translated_text="Use sample.", order=1),
            TranslationSegment(segment_id="s1", translated_text="Incubate.", order=0),
        ],
    )
    codes = [item.code for item in validate_translation_variant(variant, _source_segments())]
    assert "translation-segment-id-mismatch" in codes
    assert "translation-segment-order-mismatch" in codes
    assert "translation-placeholder-mismatch" in codes


def test_translation_selection_requires_unambiguous_context():
    eu = TranslationVariant(
        id="eu", content_object_id="obj", canonical_revision=1,
        target_language="en-US", revision=1, status="approved",
        applicability={"markets": ["EU"]},
    )
    us = TranslationVariant(
        id="us", content_object_id="obj", canonical_revision=1,
        target_language="en-US", revision=1, status="approved",
        applicability={"markets": ["US"]},
    )
    selected, findings = select_translation_variant(
        [us, eu], content_object_id="obj", canonical_revision=1,
        target_language="en-US", context={"market": "EU"},
    )
    assert findings == []
    assert selected.id == "eu"


def _resolved_tree():
    obj = ContentObject(id="obj", type="paragraph", section_type="procedure", current_revision=1)
    obj.revisions = [ContentObjectRevision(
        object_id="obj", revision=1, canonical_content="Use {{sample}}.",
        slots=[ContentSlot(slot_id="sample", type="sample-type", required=True)],
        approval_status="approved",
    )]
    return resolve_content_tree(
        ["obj"], {"obj": obj}, pinned_revisions={"obj": 1},
        config_values={"sample": "serum"}, revision_mode="pinned",
    )


def test_release_builder_pins_resolution_configuration_and_translation():
    catalog = ConfigurationCatalog()
    catalog.add(ConfigurationParameter(
        parameter_id="sample", revision=1, type="string", status="approved",
    ))
    selection = TranslationSelection(
        working_version_id="work-1", content_object_id="obj", canonical_revision=1,
        target_language="en-US", translation_variant_id="variant-1",
        translation_revision=2, selected_by="reviewer", selected_at="2026-08-01T00:00:00+00:00",
    )
    release = build_language_release_snapshot(
        release_id="rel-1", product_id="prod-1", language="en-US", version=1,
        resolved_tree=_resolved_tree(), configuration_catalog=catalog,
        configuration_values=[ConfigurationValue("sample", 1, "serum")],
        translation_selections=[selection], created_at="2026-08-01T00:00:00+00:00",
        created_by="reviewer",
    )
    assert release.verify_checksum()
    assert release.content_bindings[0].object_id == "obj"
    assert release.content_bindings[0].revision == 1
    assert release.translation_bindings[0].variant_id == "variant-1"
    assert release.configuration_snapshot["parameters"][0]["parameter_revision"] == 1
    assert release.resolved_blocks[0].rendered_content == "Use serum."


def test_release_builder_rejects_unapproved_configuration_revision():
    catalog = ConfigurationCatalog()
    catalog.add(ConfigurationParameter(parameter_id="sample", revision=1, type="string", status="draft"))
    try:
        build_language_release_snapshot(
            release_id="rel", product_id="prod", language="de-DE", version=1,
            resolved_tree=_resolved_tree(), configuration_catalog=catalog,
            configuration_values=[ConfigurationValue("sample", 1, "serum")],
        )
        assert False, "release creation must fail"
    except ReleaseBuildError as exc:
        assert exc.findings[0]["code"] == "invalid-configuration-snapshot"
