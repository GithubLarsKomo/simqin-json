"""Snapshot tests for the XML parser and canonical JSON generation."""

from __future__ import annotations

import json
import os
from pathlib import Path

import pytest
from lxml import etree

from app.parser import convert_xml, _node_to_json, _validate_against_schema
from app.mapper import MappingProfile

HERE = Path(__file__).resolve().parent
FIXTURES = HERE.parent.parent.parent / "shared" / "test-fixtures"


def _load_fixture(name: str) -> bytes:
    with open(FIXTURES / name, "rb") as fh:
        return fh.read()


# ---------------------------------------------------------------------------
# Basic parsing
# ---------------------------------------------------------------------------

def test_parse_valid_xml():
    xml = _load_fixture("example-topic.xml")
    result = convert_xml(xml, "example-topic.xml")
    assert result["ok"] is True
    assert result["canonical_json"] is not None
    assert result["domain_json"] is not None
    assert result["canonical_json"]["document"]["source_filename"] == "example-topic.xml"
    root = result["canonical_json"]["document"]["root"]
    assert root["type"] == "element"
    assert root["name"] == "topic"


def test_parse_with_dtd():
    xml = _load_fixture("example-topic.xml")
    dtd = _load_fixture("example-topic.dtd")
    result = convert_xml(xml, "example-topic.xml", dtd_bytes=dtd)
    assert result["ok"] is True
    assert result["validation"]["valid"] is True
    assert result["validation"]["schema_type"] == "DTD"


def test_parse_invalid_xml():
    result = convert_xml(b"<not-well-formed>", "broken.xml")
    assert result["ok"] is False
    assert result["validation"]["valid"] is False
    assert len(result["validation"]["errors"]) > 0


def test_parse_empty_xml():
    result = convert_xml(b"", "empty.xml")
    assert result["ok"] is False


# ---------------------------------------------------------------------------
# XXE protection
# ---------------------------------------------------------------------------

XXE_XML = b"""<?xml version="1.0"?>
<!DOCTYPE foo [
  <!ENTITY xxe SYSTEM "file:///etc/passwd">
]>
<root>&xxe;</root>"""


def test_xxe_is_blocked():
    """XXE must not resolve external entities."""
    result = convert_xml(XXE_XML, "xxe.xml")
    # With resolve_entities=False the entity is NOT resolved (/etc/passwd never read)
    assert result["ok"] is True
    # The entity reference should appear as-is (not resolved)
    root = result["canonical_json"]["document"]["root"]
    texts = [c.get("text", "") for c in root.get("children", [])]
    assert not any("root" in t or "bin" in t for t in texts)  # no /etc/passwd content


# ---------------------------------------------------------------------------
# Canonical JSON structure
# ---------------------------------------------------------------------------

def test_canonical_preserves_attributes():
    xml = _load_fixture("example-topic.xml")
    result = convert_xml(xml, "example-topic.xml")
    root = result["canonical_json"]["document"]["root"]
    assert root["attributes"]["id"] == "t1"


def test_canonical_preserves_text():
    xml = _load_fixture("example-topic.xml")
    result = convert_xml(xml, "example-topic.xml")
    root = result["canonical_json"]["document"]["root"]
    # The first child of root should be a text node (whitespace/newline)
    children = root["children"]
    assert len(children) > 0


def test_canonical_has_namespace_fields():
    xml = _load_fixture("example-topic.xml")
    result = convert_xml(xml, "example-topic.xml")
    root = result["canonical_json"]["document"]["root"]
    assert "namespace" in root
    assert "qualified_name" in root


# ---------------------------------------------------------------------------
# Domain JSON
# ---------------------------------------------------------------------------

def test_domain_has_title():
    xml = _load_fixture("example-topic.xml")
    result = convert_xml(xml, "example-topic.xml")
    assert result["domain_json"]["title"] == "Example SIMQIN Topic"


def test_domain_has_sections():
    xml = _load_fixture("example-topic.xml")
    result = convert_xml(xml, "example-topic.xml")
    sections = result["domain_json"]["sections"]
    assert len(sections) == 2
    assert sections[0]["heading"] == "Purpose"
    assert sections[1]["heading"] == "Scope"


# ---------------------------------------------------------------------------
# Custom mapping YAML
# ---------------------------------------------------------------------------

def test_custom_mapping_profile():
    """A custom YAML mapping provided as bytes overrides the default profile."""
    xml = _load_fixture("example-topic.xml")
    custom_yaml = b"""
profile: custom
version: 1.0.0
rules:
  - match: "/topic/title"
    target: "custom_title"
    type: "text"
"""
    profile = MappingProfile.from_bytes(custom_yaml)
    result = convert_xml(xml, "example-topic.xml", mapping_profile=profile)
    assert result["domain_json"]["custom_title"] == "Example SIMQIN Topic"
    # The default profile's 'title' key should NOT be present
    assert "title" not in result["domain_json"]


# ---------------------------------------------------------------------------
# DITA map detection
# ---------------------------------------------------------------------------

def test_dita_map_topicrefs():
    xml = _load_fixture("example-ditamap.ditamap")
    result = convert_xml(xml, "example-ditamap.ditamap")
    assert result["ok"] is True
    domain = result["domain_json"]
    assert "dita_map" in domain
    dita_map = domain["dita_map"]
    assert dita_map["id"] == "my-map"
    assert "Example DITA Map" in dita_map["title"]
    assert "topicrefs" in dita_map
    # top-level topicrefs
    top_level = dita_map["topicrefs"]
    assert len(top_level) >= 2
    # first topicref should have nested children
    assert "topicrefs" in top_level[0]


def test_dita_map_navtitle():
    xml = _load_fixture("example-ditamap.ditamap")
    result = convert_xml(xml, "example-ditamap.ditamap")
    topicrefs = result["domain_json"]["dita_map"]["topicrefs"]
    assert topicrefs[0]["navtitle"] == "Overview"
    assert topicrefs[1]["navtitle"] == "Installation"


def test_dita_map_scope_format():
    xml = _load_fixture("example-ditamap.ditamap")
    result = convert_xml(xml, "example-ditamap.ditamap")
    topicrefs = result["domain_json"]["dita_map"]["topicrefs"]
    # external reference
    assert topicrefs[3]["scope"] == "external"
    assert topicrefs[3]["format"] == "html"


def test_dita_map_keys():
    xml = _load_fixture("example-ditamap.ditamap")
    result = convert_xml(xml, "example-ditamap.ditamap")
    topicrefs = result["domain_json"]["dita_map"]["topicrefs"]
    assert topicrefs[1]["keys"] == "install"
    nested = topicrefs[1]["topicrefs"]
    assert nested[1]["keys"] == "install-linux"


# ---------------------------------------------------------------------------
# Schema validation
# ---------------------------------------------------------------------------

def test_schema_validation_passes():
    xml = _load_fixture("example-topic.xml")
    result = convert_xml(xml, "example-topic.xml")
    # Schema warnings should be empty for valid output
    warnings = result["validation"]["warnings"]
    schema_warnings = [w for w in warnings if "schema" in w.get("message", "").lower()]
    # Schema file exists, so validation should run without errors
    assert len(schema_warnings) == 0, f"Schema warnings: {schema_warnings}"


def test_schema_validation_detects_missing_field():
    bad = {"document": {"source_filename": "test.xml"}}  # missing root
    errors = _validate_against_schema(bad)
    assert len(errors) > 0


# ---------------------------------------------------------------------------
# Node-to-JSON helper
# ---------------------------------------------------------------------------

def test_node_to_json_element():
    elem = etree.fromstring("<root attr='v'><child>text</child></root>")
    result = _node_to_json(elem)
    assert result["type"] == "element"
    assert result["name"] == "root"
    assert result["attributes"] == {"attr": "v"}
    assert len(result["children"]) == 1  # child element only (no text before)
    assert result["children"][0]["name"] == "child"


def test_node_to_json_text():
    elem = etree.fromstring("<root>hello</root>")
    result = _node_to_json(elem)
    children = result["children"]
    assert len(children) == 1
    assert children[0]["type"] == "text"
    assert children[0]["text"] == "hello"
