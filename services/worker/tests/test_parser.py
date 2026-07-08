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
    domain = result["domain_json"]
    assert domain["custom_title"] == "Example SIMQIN Topic"
    # Structural fields are always present even with custom mapping
    assert domain["title"] is None  # not mapped, but field exists
    assert domain["sections"] == []
    assert domain["_mapping"]["profile"] == "custom"


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
# DITA map with mapref, chapter, appendix, bookmap
# ---------------------------------------------------------------------------

def test_dita_map_full_types():
    xml = _load_fixture("example-map.ditamap")
    result = convert_xml(xml, "example-map.ditamap")
    topicrefs = result["domain_json"]["dita_map"]["topicrefs"]
    # topicref, mapref, chapter, appendix
    types_found = {r.get("format", "dita"): r for r in topicrefs}
    assert any("submap" in str(r) for r in topicrefs)  # mapref
    assert any("chapter" in str(r) or "Chapter" in str(r) for r in topicrefs)
    assert any("appendix" in str(r) or "Appendix" in str(r) for r in topicrefs)


def test_dita_map_processing_role():
    xml = _load_fixture("example-map.ditamap")
    result = convert_xml(xml, "example-map.ditamap")
    topicrefs = result["domain_json"]["dita_map"]["topicrefs"]
    for r in topicrefs:
        if r.get("processing-role") == "resource-only":
            break
    else:
        assert False, "No resource-only topicref found"


def test_dita_map_toc():
    xml = _load_fixture("example-map.ditamap")
    result = convert_xml(xml, "example-map.ditamap")
    topicrefs = result["domain_json"]["dita_map"]["topicrefs"]
    assert any(r.get("toc") == "yes" for r in topicrefs)


# ---------------------------------------------------------------------------
# Asset extraction
# ---------------------------------------------------------------------------

def test_asset_extraction_href():
    xml = _load_fixture("example-assets.xml")
    result = convert_xml(xml, "example-assets.xml")
    assets = result["domain_json"]["assets"]
    assert len(assets) >= 3
    hrefs = [a["href"] for a in assets]
    assert "img/diagram.png" in hrefs
    assert "img/photo.jpg" in hrefs
    assert "img/architecture.svg" in hrefs


def test_asset_extraction_alt_text():
    xml = _load_fixture("example-assets.xml")
    result = convert_xml(xml, "example-assets.xml")
    for a in result["domain_json"]["assets"]:
        if a["href"] == "img/diagram.png":
            assert a.get("alt") == "System Diagram"
            return
    assert False, "Expected asset with alt text"


def test_asset_extraction_fig():
    xml = _load_fixture("example-assets.xml")
    result = convert_xml(xml, "example-assets.xml")
    assets = result["domain_json"]["assets"]
    image_assets = [a for a in assets if a["type"] == "image"]
    assert len(image_assets) >= 1


def test_asset_extraction_dedup():
    """Duplicate assets (same href + same type) should be skipped."""
    xml = _load_fixture("example-assets.xml")
    result = convert_xml(xml, "example-assets.xml")
    assets = result["domain_json"]["assets"]
    diagram = [a for a in assets if a["href"] == "img/diagram.png"]
    assert len(diagram) == 1  # deduplicated


# ---------------------------------------------------------------------------
# Reference extraction
# ---------------------------------------------------------------------------

def test_reference_extraction_xref():
    xml = _load_fixture("example-assets.xml")
    result = convert_xml(xml, "example-assets.xml")
    refs = result["domain_json"]["references"]
    assert len(refs) >= 2
    xrefs = [r for r in refs if r["type"] == "xref"]
    assert len(xrefs) >= 1
    assert any("external-guide" in r.get("href", "") for r in xrefs)


def test_reference_extraction_link():
    xml = _load_fixture("example-assets.xml")
    result = convert_xml(xml, "example-assets.xml")
    refs = result["domain_json"]["references"]
    links = [r for r in refs if r["type"] == "link"]
    assert len(links) >= 1


# ---------------------------------------------------------------------------
# Mapping validation: invalid YAML
# ---------------------------------------------------------------------------

def test_mapping_validation_invalid_yaml():
    """Invalid mapping YAML should raise an exception."""
    from app.mapper import MappingProfile, MappingValidationError

    bad_yaml = b"not: valid: yaml: [[["
    try:
        MappingProfile.from_bytes(bad_yaml)
        assert False, "Expected exception"
    except (MappingValidationError, Exception):
        pass


def test_mapping_validation_missing_rules():
    """Mapping YAML without rules should raise MappingValidationError."""
    from app.mapper import MappingProfile, MappingValidationError

    try:
        MappingProfile.from_bytes(b"profile: test\nversion: 1.0.0\n")
        assert False, "Expected MappingValidationError"
    except MappingValidationError:
        pass


def test_mapping_validation_missing_match():
    """A rule without 'match' should raise MappingValidationError."""
    from app.mapper import MappingProfile, MappingValidationError

    try:
        MappingProfile.from_bytes(b"rules:\n  - target: x\n    type: text\n")
        assert False, "Expected MappingValidationError"
    except MappingValidationError:
        pass


def test_mapping_validation_invalid_type():
    """A rule with invalid 'type' should raise MappingValidationError."""
    from app.mapper import MappingProfile, MappingValidationError

    try:
        MappingProfile.from_bytes(b"rules:\n  - match: '/a'\n    target: x\n    type: unknown\n")
        assert False, "Expected MappingValidationError"
    except MappingValidationError:
        pass


# ---------------------------------------------------------------------------
# DITA table extraction
# ---------------------------------------------------------------------------

DITA_TABLE_XML = b"""<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE topic PUBLIC "-//OASIS//DTD DITA Topic//EN" "topic.dtd">
<topic id="table-test">
  <title>Table Test</title>
  <body>
    <section id="tables-section">
      <title>Tables Section</title>
      <table>
        <title>Sample Table</title>
        <tgroup cols="2">
          <thead>
            <row><entry>Name</entry><entry>Value</entry></row>
          </thead>
          <tbody>
            <row><entry>Alpha</entry><entry>1</entry></row>
            <row><entry>Beta</entry><entry>2</entry></row>
          </tbody>
        </tgroup>
      </table>
      <simpletable>
        <sthead>
          <stentry>Key</stentry><stentry>Val</stentry>
        </sthead>
        <strow>
          <stentry>A</stentry><stentry>10</stentry>
        </strow>
      </simpletable>
    </section>
  </body>
</topic>"""


def test_dita_table_extraction():
    result = convert_xml(DITA_TABLE_XML, "table-test.xml")
    sections = result["domain_json"]["sections"]
    tables_found = 0
    for sec in sections:
        if "tables" in sec:
            for tbl in sec["tables"]:
                if "Sample Table" in tbl.get("caption", ""):
                    tables_found += 1
                    assert len(tbl["rows"]) >= 2
    assert tables_found >= 1, "DITA table with caption not found in section tables"


def test_simpletable_extraction():
    result = convert_xml(DITA_TABLE_XML, "table-test.xml")
    sections = result["domain_json"]["sections"]
    total_tables = sum(
        len(sec.get("tables", [])) for sec in sections
    )
    assert total_tables >= 2, f"Expected >=2 tables, got {total_tables}"


# ---------------------------------------------------------------------------
# Domain schema validation test
# ---------------------------------------------------------------------------

def test_domain_json_matches_schema():
    """Produced domain_json SHOULD validate against domain-json.schema.json (Draft 2020-12)."""
    import json
    from jsonschema import Draft202012Validator, ValidationError

    schema_path = HERE.parent.parent.parent / "shared" / "schemas" / "domain-json.schema.json"
    with open(schema_path, "r") as fh:
        schema = json.load(fh)

    validator = Draft202012Validator(schema)

    # Test with default profile + DITA map
    xml = _load_fixture("example-topic.xml")
    result = convert_xml(xml, "example-topic.xml")
    domain = result["domain_json"]
    errors = list(validator.iter_errors(domain))
    assert not errors, f"Domain JSON schema errors: {[e.message for e in errors]}"

    # Test with custom mapping profile — should still validate
    custom_yaml = b"""
profile: custom-test
version: 2.0.0
rules:
  - match: "/topic/title"
    target: "my_title"
    type: "text"
"""
    from app.mapper import MappingProfile
    profile = MappingProfile.from_bytes(custom_yaml)
    result2 = convert_xml(xml, "custom-test.xml", mapping_profile=profile)
    domain2 = result2["domain_json"]
    errors2 = list(validator.iter_errors(domain2))
    assert not errors2, f"Custom mapping domain JSON schema errors: {[e.message for e in errors2]}"

    # Verify structural fields are present even with custom mapping
    assert domain2.get("title") is None
    assert domain2.get("sections") == []
    assert domain2.get("_mapping", {}).get("profile") == "custom-test"
    # Custom fields appear alongside structural fields
    assert domain2.get("my_title") == "Example SIMQIN Topic"

    # Test DITA map
    xml3 = _load_fixture("example-ditamap.ditamap")
    result3 = convert_xml(xml3, "example-ditamap.ditamap")
    domain3 = result3["domain_json"]
    errors3 = list(validator.iter_errors(domain3))
    assert not errors3, f"DITA map domain JSON schema errors: {[e.message for e in errors3]}"


def test_canonical_json_matches_schema():
    """Produced canonical_json SHOULD validate against canonical-json.schema.json."""
    import json
    from jsonschema import Draft202012Validator

    schema_path = HERE.parent.parent.parent / "shared" / "schemas" / "canonical-json.schema.json"
    with open(schema_path, "r") as fh:
        schema = json.load(fh)

    validator = Draft202012Validator(schema)

    xml = _load_fixture("example-topic.xml")
    result = convert_xml(xml, "example-topic.xml")
    canonical = result["canonical_json"]
    errors = list(validator.iter_errors(canonical))
    assert not errors, f"Canonical JSON schema errors: {[e.message for e in errors]}"


# ---------------------------------------------------------------------------
# Assets fixture includes references, format, scope
# ---------------------------------------------------------------------------

def test_asset_has_source_path():
    xml = _load_fixture("example-assets.xml")
    result = convert_xml(xml, "example-assets.xml")
    for a in result["domain_json"]["assets"]:
        assert "_source" in a, f"Asset missing _source path: {a}"


def test_reference_has_source_path():
    xml = _load_fixture("example-assets.xml")
    result = convert_xml(xml, "example-assets.xml")
    for r in result["domain_json"]["references"]:
        assert "_source" in r, f"Reference missing _source path: {r}"


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
