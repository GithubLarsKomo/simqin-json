"""Tests for the YAML-driven mapping engine."""

from __future__ import annotations

import os
from pathlib import Path

from lxml import etree

from app.mapper import (
    MappingProfile,
    MappingRule,
    apply_mapping,
    _domain_json_hardcoded,
    _extract_text,
)

HERE = Path(__file__).resolve().parent
FIXTURES = HERE.parent.parent.parent / "shared" / "test-fixtures"


def _load_fixture(name: str) -> bytes:
    with open(FIXTURES / name, "rb") as fh:
        return fh.read()


def _parse_xml(name: str) -> etree._Element:
    xml = _load_fixture(name)
    return etree.fromstring(xml)


# ---------------------------------------------------------------------------
# MappingProfile loading
# ---------------------------------------------------------------------------

def test_load_default_profile():
    path = MappingProfile.default_profile_path()
    assert os.path.isfile(path), f"Profile not found: {path}"
    profile = MappingProfile.from_yaml(path)
    assert profile.name == "simqin-default"
    assert len(profile.rules) > 0


def test_load_profile_from_bytes():
    yaml_bytes = b"""
profile: test
version: 1.0.0
rules:
  - match: "/root/title"
    target: "title"
    type: "text"
"""
    profile = MappingProfile.from_bytes(yaml_bytes)
    assert profile.name == "test"
    assert profile.version == "1.0.0"
    assert len(profile.rules) == 1
    assert profile.rules[0].target == "title"


# ---------------------------------------------------------------------------
# apply_mapping with profile
# ---------------------------------------------------------------------------

def test_apply_mapping_title():
    root = _parse_xml("example-topic.xml")
    profile = MappingProfile.from_yaml(MappingProfile.default_profile_path())
    domain = apply_mapping(root, profile)
    assert domain["title"] == "Example SIMQIN Topic"


def test_apply_mapping_sections():
    root = _parse_xml("example-topic.xml")
    profile = MappingProfile.from_yaml(MappingProfile.default_profile_path())
    domain = apply_mapping(root, profile)
    sections = domain.get("sections", [])
    assert len(sections) == 2
    assert sections[0]["heading"] == "Purpose"
    assert sections[1]["heading"] == "Scope"


def test_apply_mapping_topic_id():
    root = _parse_xml("example-topic.xml")
    profile = MappingProfile.from_yaml(MappingProfile.default_profile_path())
    domain = apply_mapping(root, profile)
    assert domain.get("topic_id") == "t1"


# ---------------------------------------------------------------------------
# Hardcoded fallback (backward compat)
# ---------------------------------------------------------------------------

def test_hardcoded_fallback():
    root = _parse_xml("example-topic.xml")
    domain = apply_mapping(root, None)
    assert domain["title"] == "Example SIMQIN Topic"
    assert len(domain["sections"]) == 2


def test_hardcoded_equals_profile_result():
    root = _parse_xml("example-topic.xml")
    profile = MappingProfile.from_yaml(MappingProfile.default_profile_path())
    domain_profile = apply_mapping(root, profile)
    domain_fallback = apply_mapping(root, None)
    assert domain_profile["title"] == domain_fallback["title"]
    assert len(domain_profile["sections"]) == len(domain_fallback["sections"])


# ---------------------------------------------------------------------------
# extract_text helper
# ---------------------------------------------------------------------------

def test_extract_text():
    elem = etree.fromstring("<p>Hello <b>world</b>!</p>")
    assert _extract_text(elem) == "Hello world!"


# ---------------------------------------------------------------------------
# Edge cases
# ---------------------------------------------------------------------------

def test_empty_profile():
    root = _parse_xml("example-topic.xml")
    profile = MappingProfile("empty", "0.0.0", [])
    domain = apply_mapping(root, profile)
    # _mapping metadata is always present; no user keys otherwise
    assert "title" not in domain
    assert domain.get("_mapping", {}).get("profile") == "empty"
    assert domain["_mapping"]["rule_count"] == 0


def test_invalid_xpath_in_profile():
    """An invalid XPath in a profile should produce a warning, not crash."""
    yaml_bytes = b"""
profile: badxpath
version: 1.0.0
rules:
  - match: "!!!invalid"
    target: "x"
    type: "text"
"""
    profile = MappingProfile.from_bytes(yaml_bytes)
    assert len(profile.rules) == 0  # rule was skipped
    assert any("invalid" in w.lower() for w in profile.warnings)


def test_no_match():
    root = _parse_xml("example-topic.xml")
    profile = MappingProfile("nomatch", "0.0.0", [MappingRule("/nonexistent", "x", "text")])
    domain = apply_mapping(root, profile)
    assert "x" not in domain
    # Should have a warning about 0 matches
    warnings = domain.get("_mapping", {}).get("warnings", [])
    assert any("matched 0" in w for w in warnings)


def test_mapping_warning_on_zero_matches():
    """A rule that matches nothing should produce a non-fatal warning."""
    root = _parse_xml("example-topic.xml")
    yaml_bytes = b"""
profile: warn-test
version: 1.0.0
rules:
  - match: "/topic/nonexistent"
    target: "ghost"
    type: "text"
"""
    profile = MappingProfile.from_bytes(yaml_bytes)
    domain = apply_mapping(root, profile)
    assert "ghost" not in domain
    warnings = domain.get("_mapping", {}).get("warnings", [])
    assert len(warnings) > 0
    assert any("matched 0" in w for w in warnings)


def test_mapping_metadata_present():
    """domain_json should include _mapping when a profile is used."""
    root = _parse_xml("example-topic.xml")
    profile = MappingProfile.from_yaml(MappingProfile.default_profile_path())
    domain = apply_mapping(root, profile)
    assert "_mapping" in domain
    meta = domain["_mapping"]
    assert meta["profile"] == "simqin-default"
    assert meta["version"] == "0.2.0"
    assert meta["rule_count"] > 0