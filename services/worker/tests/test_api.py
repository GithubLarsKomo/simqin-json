"""API-level tests for the SIMQIN JSON Worker service.

Tests that invalid mapping YAML returns HTTP 400 (not 500).
"""

from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.mapper import MappingProfile
from app.templates import get_template

HERE = Path(__file__).resolve().parent
FIXTURES = HERE.parent.parent.parent / "shared" / "test-fixtures"


def _load_fixture(name: str) -> bytes:
    with open(FIXTURES / name, "rb") as fh:
        return fh.read()


client = TestClient(app)


# ---------------------------------------------------------------------------
# Invalid YAML → HTTP 400
# ---------------------------------------------------------------------------


def test_invalid_yaml_syntax_returns_400():
    """Worker /api/v1/convert must return 400 for syntactically invalid YAML."""
    xml = _load_fixture("example-topic.xml")
    response = client.post(
        "/api/v1/convert",
        files={
            "file": ("test.xml", xml, "application/xml"),
            "mapping": ("bad.yaml", b"not: valid: yaml: [[[", "application/x-yaml"),
        },
    )
    assert response.status_code == 400
    detail = response.json().get("detail", "")
    assert "YAML" in detail or "Invalid" in detail


def test_empty_mapping_yaml_returns_400():
    """Worker must return 400 for empty (null) YAML mapping file (not whitespace-only)."""
    xml = _load_fixture("example-topic.xml")
    response = client.post(
        "/api/v1/convert",
        files={
            "file": ("test.xml", xml, "application/xml"),
            "mapping": ("empty.yaml", b"   ", "application/x-yaml"),
        },
    )
    assert response.status_code == 400
    detail = response.json().get("detail", "")
    assert "Empty" in detail or "YAML" in detail


def test_scalar_yaml_returns_400():
    """Worker must return 400 when YAML is a scalar, not a mapping."""
    xml = _load_fixture("example-topic.xml")
    response = client.post(
        "/api/v1/convert",
        files={
            "file": ("test.xml", xml, "application/xml"),
            "mapping": ("scalar.yaml", b"just a string", "application/x-yaml"),
        },
    )
    assert response.status_code == 400


def test_mapping_text_invalid_yaml_returns_400():
    """Worker must return 400 for invalid YAML in mapping_text field."""
    xml = _load_fixture("example-topic.xml")
    response = client.post(
        "/api/v1/convert",
        files={"file": ("test.xml", xml, "application/xml")},
        data={"mapping_text": "not: valid: yaml: [[["},
    )
    assert response.status_code == 400
    detail = response.json().get("detail", "")
    assert "YAML" in detail or "Invalid" in detail


# ---------------------------------------------------------------------------
# Valid mapping → HTTP 200
# ---------------------------------------------------------------------------


def test_valid_yaml_returns_200():
    """Worker must return 200 for structurally valid YAML."""
    xml = _load_fixture("example-topic.xml")
    valid_yaml = b"""
profile: test
version: 1.0.0
rules:
  - match: "/topic/title"
    target: "my_title"
    type: "text"
"""
    response = client.post(
        "/api/v1/convert",
        files={
            "file": ("test.xml", xml, "application/xml"),
            "mapping": ("good.yaml", valid_yaml, "application/x-yaml"),
        },
    )
    assert response.status_code == 200
    data = response.json()
    assert data["ok"] is True
    assert data["domain_json"]["my_title"] == "Example SIMQIN Topic"


# ---------------------------------------------------------------------------
# Authoring template endpoints
# ---------------------------------------------------------------------------


def test_get_templates_list():
    """GET /api/v1/templates returns all template summaries."""
    response = client.get("/api/v1/templates")
    assert response.status_code == 200
    data = response.json()
    assert isinstance(data, list)
    ids = [t["id"] for t in data]
    assert "dita-topic" in ids
    assert "sop" in ids
    assert "dita-map" in ids


def test_get_template_by_id_dita_topic():
    """GET /api/v1/templates/dita-topic returns full template JSON."""
    response = client.get("/api/v1/templates/dita-topic")
    assert response.status_code == 200
    tpl = response.json()
    assert tpl["template"] == "dita-topic"
    assert tpl["title"] == "Neues Thema"
    assert "sections" in tpl
    assert len(tpl["sections"]) >= 1


def test_get_template_by_id_sop():
    """GET /api/v1/templates/sop returns full SOP template JSON."""
    response = client.get("/api/v1/templates/sop")
    assert response.status_code == 200
    tpl = response.json()
    assert tpl["template"] == "sop"
    assert tpl["title"] == "Standard Operating Procedure"
    assert len(tpl["sections"]) >= 4


def test_get_template_by_id_dita_map():
    """GET /api/v1/templates/dita-map returns full DITA map template JSON."""
    response = client.get("/api/v1/templates/dita-map")
    assert response.status_code == 200
    tpl = response.json()
    assert tpl["template"] == "dita-map"
    assert len(tpl["topicrefs"]) >= 2
    # Verify nested topicrefs
    has_nested = any(len(tr.get("children", [])) > 0 for tr in tpl["topicrefs"])
    assert has_nested


def test_get_template_by_id_not_found():
    """GET /api/v1/templates/nonexistent returns 404."""
    response = client.get("/api/v1/templates/does-not-exist")
    assert response.status_code == 404


# ---------------------------------------------------------------------------
# Authoring profile endpoints
# ---------------------------------------------------------------------------


def test_get_profiles_list():
    """GET /api/v1/authoring/profiles returns all profiles."""
    response = client.get("/api/v1/authoring/profiles")
    assert response.status_code == 200
    data = response.json()
    assert isinstance(data, list)
    ids = [p["id"] for p in data]
    assert "dita-topic" in ids
    assert "sop" in ids
    assert "dita-map" in ids


def test_get_profile_by_id():
    """GET /api/v1/authoring/profiles/dita-topic returns full profile."""
    response = client.get("/api/v1/authoring/profiles/dita-topic")
    assert response.status_code == 200
    p = response.json()
    assert p["id"] == "dita-topic"
    assert "allowed_children" in p
    assert "allowed_attributes" in p
    assert "required_fields" in p
    assert "export_extension" in p
    assert p["export_extension"] == ".dita"


def test_get_profile_by_id_sop():
    """GET /api/v1/authoring/profiles/sop returns SOP profile."""
    response = client.get("/api/v1/authoring/profiles/sop")
    assert response.status_code == 200
    p = response.json()
    assert p["id"] == "sop"
    assert p["export_extension"] == ".xml"


def test_get_profile_by_id_dita_map():
    """GET /api/v1/authoring/profiles/dita-map returns DITA map profile."""
    response = client.get("/api/v1/authoring/profiles/dita-map")
    assert response.status_code == 200
    p = response.json()
    assert p["id"] == "dita-map"
    assert p["export_extension"] == ".ditamap"
    # topicref can have topicref children
    assert "topicref" in p["allowed_children"].get("topicref", [])


def test_get_profile_not_found():
    """GET /api/v1/authoring/profiles/nonexistent returns 404."""
    response = client.get("/api/v1/authoring/profiles/does-not-exist")
    assert response.status_code == 404


def test_allowed_actions_topic_section():
    """POST /api/v1/authoring/allowed-actions for doc in dita-topic."""
    response = client.post(
        "/api/v1/authoring/allowed-actions",
        json={"profile_id": "dita-topic", "node_path": "doc"},
    )
    assert response.status_code == 200
    data = response.json()
    assert "section" in data["allowed_add"]
    assert "asset" in data["allowed_add"]
    assert "reference" in data["allowed_add"]


def test_allowed_actions_topic_section_children():
    """POST /api/v1/authoring/allowed-actions for section in dita-topic."""
    response = client.post(
        "/api/v1/authoring/allowed-actions",
        json={"profile_id": "dita-topic", "node_path": "section"},
    )
    assert response.status_code == 200
    data = response.json()
    assert "paragraph" in data["allowed_add"]
    assert "table" in data["allowed_add"]
    assert "image" in data["allowed_add"]
    assert "link" in data["allowed_add"]


def test_allowed_actions_dita_map_topicref():
    """POST /api/v1/authoring/allowed-actions for topicref in dita-map."""
    response = client.post(
        "/api/v1/authoring/allowed-actions",
        json={"profile_id": "dita-map", "node_path": "topicref"},
    )
    assert response.status_code == 200
    data = response.json()
    assert "topicref" in data["allowed_add"]
    assert data["can_delete"] is True


def test_allowed_actions_unknown_profile():
    """POST /api/v1/authoring/allowed-actions with unknown profile returns 404."""
    response = client.post(
        "/api/v1/authoring/allowed-actions",
        json={"profile_id": "nonexistent", "node_path": "doc"},
    )
    assert response.status_code == 404


# ---------------------------------------------------------------------------
# Profile-based validation
# ---------------------------------------------------------------------------


def test_validate_with_profile_valid():
    """POST /api/v1/authoring/validate with valid document."""
    doc = {
        "template": "dita-topic",
        "title": "Valid Doc",
        "id": "vd",
        "sections": [{"heading": "Intro", "id": "s1", "paragraphs": [{"text": "Hello", "id": "p1"}], "tables": [], "images": [], "links": []}],
        "topicrefs": [], "assets": [], "references": [],
    }
    response = client.post("/api/v1/authoring/validate", json={"document": doc})
    assert response.status_code == 200
    data = response.json()
    assert data["valid"] is True


def test_validate_with_profile_missing_title():
    """POST /api/v1/authoring/validate with missing title."""
    doc = {
        "template": "dita-topic",
        "title": "",
        "id": "vd",
        "sections": [],
        "topicrefs": [], "assets": [], "references": [],
    }
    response = client.post("/api/v1/authoring/validate", json={"document": doc})
    assert response.status_code == 200
    data = response.json()
    assert data["valid"] is False
    assert any("title" in e.lower() for e in data["errors"])


def test_validate_with_profile_unknown_field():
    """POST /api/v1/authoring/validate with disallowed field."""
    doc = {
        "template": "dita-topic",
        "title": "Test",
        "id": "t",
        "sections": [],
        "topicrefs": [], "assets": [], "references": [],
        "invalid_field": "should not be here",
    }
    response = client.post("/api/v1/authoring/validate", json={"document": doc})
    assert response.status_code == 200
    data = response.json()
    assert data["valid"] is False
    assert any("invalid_field" in e for e in data["errors"])


def test_validate_with_profile_explicit_profile_id():
    """POST /api/v1/authoring/validate with explicit profile_id."""
    doc = {
        "template": "dita-topic",
        "title": "Test",
        "id": "t",
        "sections": [],
        "topicrefs": [], "assets": [], "references": [],
    }
    response = client.post(
        "/api/v1/authoring/validate",
        json={"document": doc, "profile_id": "dita-topic"},
    )
    assert response.status_code == 200
    data = response.json()
    assert data["valid"] is True


def test_validate_dita_map_with_topicrefs():
    """POST /api/v1/authoring/validate with valid DITA map."""
    doc = {
        "template": "dita-map",
        "title": "My Map",
        "id": "mm",
        "sections": [],
        "topicrefs": [
            {"href": "a.dita", "navtitle": "A", "id": "r1", "keys": "", "children": [
                {"href": "a1.dita", "navtitle": "A1", "id": "r2", "keys": "", "children": []},
            ]},
        ],
        "assets": [], "references": [],
    }
    response = client.post("/api/v1/authoring/validate", json={"document": doc})
    assert response.status_code == 200
    data = response.json()
    assert data["valid"] is True


def test_roundtrip_after_move_and_delete():
    """Authoring JSON -> move/delete -> XML -> convert_xml should still work."""
    from app.parser import convert_xml
    from app.authoring import AuthoringDoc, Section, Paragraph
    from app.xml_writer import render_document_xml

    doc = AuthoringDoc(
        template="dita-topic",
        title="Move Test",
        id="mt",
        sections=[
            Section(heading="First", id="s1", paragraphs=[Paragraph(text="P1", id="p1")]),
            Section(heading="Second", id="s2", paragraphs=[Paragraph(text="P2", id="p2")]),
        ],
        topicrefs=[], assets=[], references=[],
    )
    # Simulate move: swap sections
    doc.sections[0], doc.sections[1] = doc.sections[1], doc.sections[0]
    # Simulate delete: remove first paragraph
    doc.sections[0].paragraphs.pop(0)

    xml_bytes = render_document_xml(doc)
    result = convert_xml(xml_bytes, "move-test.xml")
    assert result["ok"] is True
    domain = result["domain_json"]
    assert domain["title"] == "Move Test"