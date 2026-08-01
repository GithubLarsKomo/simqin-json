"""Behavioral tests for revisioned configuration and immutable releases."""

from dataclasses import FrozenInstanceError

from app.configuration import ConfigurationCatalog, ConfigurationParameter, ConfigurationValue
from app.ifu_release import (
    ContentRevisionBinding,
    IFULanguageReleaseSnapshot,
    ResolvedBlockSnapshot,
)


def test_catalog_preserves_parameter_revisions():
    catalog = ConfigurationCatalog()
    catalog.add(ConfigurationParameter(parameter_id="market", revision=1, type="enum", allowed_values=["EU"], status="approved"))
    catalog.add(ConfigurationParameter(parameter_id="market", revision=2, type="enum", allowed_values=["EU", "US"], status="draft"))
    assert catalog.get_revision("market", 1).allowed_values == ["EU"]
    assert catalog.get_revision("market", 2).allowed_values == ["EU", "US"]
    assert catalog.get_latest_approved("market").revision == 1


def test_duplicate_parameter_revision_is_rejected():
    catalog = ConfigurationCatalog()
    parameter = ConfigurationParameter(parameter_id="flag", revision=1, type="boolean")
    catalog.add(parameter)
    try:
        catalog.add(parameter)
        assert False, "duplicate revision must fail"
    except ValueError as exc:
        assert "Duplicate parameter revision" in str(exc)


def test_configuration_value_must_match_pinned_approved_revision():
    catalog = ConfigurationCatalog()
    catalog.add(ConfigurationParameter(parameter_id="count", revision=1, type="integer", status="approved"))
    catalog.add(ConfigurationParameter(parameter_id="count", revision=2, type="integer", status="draft"))
    assert catalog.validate_configuration_value(ConfigurationValue("count", 1, 5), require_approved=True) == []
    assert "not approved" in catalog.validate_configuration_value(ConfigurationValue("count", 2, 5), require_approved=True)[0]
    assert "not found" in catalog.validate_configuration_value(ConfigurationValue("count", 3, 5), require_approved=True)[0]


def test_string_list_and_role_restrictions_are_enforced():
    catalog = ConfigurationCatalog()
    catalog.add(ConfigurationParameter(parameter_id="countries", revision=1, type="string-list", status="approved", allowed_roles=["content_architect"]))
    value = ConfigurationValue("countries", 1, ["DE", "AT"])
    assert catalog.validate_configuration_value(value, role="content_architect", require_approved=True) == []
    assert "not allowed" in catalog.validate_configuration_value(value, role="author", require_approved=True)[0]
    assert "list of strings" in catalog.validate_configuration_value(ConfigurationValue("countries", 1, "DE"))[0]


def _release(content: str = "Stable content") -> IFULanguageReleaseSnapshot:
    return IFULanguageReleaseSnapshot(
        release_id="rel-1",
        product_id="prod-1",
        language="de-DE",
        version=1,
        content_bindings=(ContentRevisionBinding("obj-1", 3),),
        configuration_snapshot={"parameters": [{"parameter_id": "market", "parameter_revision": 1, "value": "EU"}]},
        resolved_blocks=(ResolvedBlockSnapshot("block-1", "obj-1", 3, content),),
        provenance={"resolution_checksum": "abc"},
        created_at="2026-08-01T00:00:00+00:00",
        created_by="tester",
    )


def test_release_checksum_is_deterministic_and_verifiable():
    first = _release()
    second = _release()
    assert first.release_checksum == second.release_checksum
    assert first.verify_checksum()
    assert IFULanguageReleaseSnapshot.from_dict(first.to_dict()).verify_checksum()


def test_release_is_immutable_and_defensively_copies_inputs():
    config = {"parameters": [{"parameter_id": "x", "value": 1}]}
    release = IFULanguageReleaseSnapshot(
        release_id="rel", product_id="prod", language="de-DE", version=1,
        configuration_snapshot=config,
    )
    config["parameters"][0]["value"] = 99
    assert release.configuration_snapshot["parameters"][0]["value"] == 1
    try:
        release.version = 2
        assert False, "frozen release must reject mutation"
    except FrozenInstanceError:
        pass


def test_release_checksum_changes_with_pinned_content():
    assert _release("A").release_checksum != _release("B").release_checksum
