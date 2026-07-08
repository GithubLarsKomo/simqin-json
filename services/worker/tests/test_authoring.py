"""Tests for the authoring module — templates, model, validation, and XML writer."""

from __future__ import annotations

import json
from pathlib import Path

from lxml import etree

from app.authoring import AuthoringDoc, Section, Paragraph, TableBlock, ImageRef, LinkRef, TopicRef, _make_id
from app.templates import list_templates, create_document
from app.xml_writer import render_topic_xml, render_map_xml, render_document_xml, render_document_json

HERE = Path(__file__).resolve().parent
FIXTURES = HERE.parent.parent.parent / "shared" / "test-fixtures"


# ---------------------------------------------------------------------------
# Template loading
# ---------------------------------------------------------------------------

def test_list_templates():
    templates = list_templates()
    assert len(templates) >= 3
    ids = [t["id"] for t in templates]
    assert "dita-topic" in ids
    assert "sop" in ids
    assert "dita-map" in ids


def test_create_dita_topic():
    doc = create_document("dita-topic")
    assert doc.template == "dita-topic"
    assert doc.title == "Neues Thema"
    assert len(doc.sections) >= 1
    assert doc.sections[0].heading == "Einleitung"


def test_create_sop():
    doc = create_document("sop")
    assert doc.template == "sop"
    assert doc.title == "Standard Operating Procedure"
    assert len(doc.sections) >= 4


def test_create_dita_map():
    doc = create_document("dita-map")
    assert doc.template == "dita-map"
    assert len(doc.topicrefs) >= 1


def test_create_unknown_template():
    try:
        create_document("nonexistent")
        assert False, "Expected ValueError"
    except ValueError:
        pass


# ---------------------------------------------------------------------------
# Authoring JSON validation
# ---------------------------------------------------------------------------

def test_validate_requires_title():
    doc = AuthoringDoc(template="dita-topic", title="", id="t1")
    errors = doc.validate()
    assert any("title" in e.lower() for e in errors)


def test_validate_requires_section_heading():
    doc = AuthoringDoc(
        template="dita-topic", title="Test", id="t1",
        sections=[Section(heading="", id="s1")],
    )
    errors = doc.validate()
    assert any("heading" in e.lower() for e in errors)


def test_validate_passes_ok():
    doc = AuthoringDoc(
        template="dita-topic", title="Valid Doc", id="valid",
        sections=[Section(heading="Intro", id="s1", paragraphs=[Paragraph(text="Hello", id="p1")])],
    )
    errors = doc.validate()
    assert len(errors) == 0


def test_id_generation():
    id1 = _make_id("Hello World")
    assert id1.startswith("hello-world-")
    id2 = _make_id("Hello World")
    assert id1 != id2  # incrementing counter


# ---------------------------------------------------------------------------
# Topic XML rendering
# ---------------------------------------------------------------------------

def test_render_topic_xml_basic():
    doc = AuthoringDoc(
        template="dita-topic",
        title="Test Topic",
        id="test-topic",
        sections=[
            Section(
                heading="Section 1", id="sec1",
                paragraphs=[Paragraph(text="Paragraph text", id="p1")],
            ),
        ],
    )
    xml_bytes = render_topic_xml(doc)
    root = etree.fromstring(xml_bytes)
    assert root.tag.endswith("topic")
    assert root.get("id") == "test-topic"
    # Title
    title = root.find("{http://dita.oasis-open.org/architecture/dita}title")
    assert title is not None
    assert title.text == "Test Topic"
    # Body
    body = root.find("{http://dita.oasis-open.org/architecture/dita}body")
    assert body is not None
    # Sections
    sections = body.findall("{http://dita.oasis-open.org/architecture/dita}section")
    assert len(sections) == 1
    sec_title = sections[0].find("{http://dita.oasis-open.org/architecture/dita}title")
    assert sec_title is not None
    assert sec_title.text == "Section 1"


def test_render_topic_xml_with_table():
    doc = AuthoringDoc(
        template="dita-topic",
        title="Table Test", id="tt",
        sections=[
            Section(
                heading="Data", id="s1",
                paragraphs=[Paragraph(text="See table", id="p1")],
                tables=[TableBlock(caption="Results", id="t1", rows=[["A", "B"], ["1", "2"]])],
            ),
        ],
    )
    xml_bytes = render_topic_xml(doc)
    root = etree.fromstring(xml_bytes)
    body = root.find("{http://dita.oasis-open.org/architecture/dita}body")
    sec = body.find("{http://dita.oasis-open.org/architecture/dita}section")
    tables = sec.findall("{http://dita.oasis-open.org/architecture/dita}table")
    assert len(tables) >= 1
    # Check tgroup
    tgroup = tables[0].find("{http://dita.oasis-open.org/architecture/dita}tgroup")
    assert tgroup is not None
    assert tgroup.get("cols") == "2"


def test_render_topic_xml_with_image_and_link():
    doc = AuthoringDoc(
        template="dita-topic",
        title="Media Test", id="mt",
        sections=[
            Section(
                heading="Media", id="s1",
                images=[ImageRef(src="img/test.png", alt="Test", id="img1")],
                links=[LinkRef(href="#target", text="Go to target", id="l1")],
            ),
        ],
    )
    xml_bytes = render_topic_xml(doc)
    root = etree.fromstring(xml_bytes)
    body = root.find("{http://dita.oasis-open.org/architecture/dita}body")
    sec = body.find("{http://dita.oasis-open.org/architecture/dita}section")
    images = sec.findall("{http://dita.oasis-open.org/architecture/dita}image")
    assert len(images) >= 1
    assert images[0].get("href") == "img/test.png"
    xrefs = sec.findall("{http://dita.oasis-open.org/architecture/dita}xref")
    assert len(xrefs) >= 1
    assert xrefs[0].get("href") == "#target"


# ---------------------------------------------------------------------------
# DITA map XML rendering
# ---------------------------------------------------------------------------

def test_render_map_xml_basic():
    doc = AuthoringDoc(
        template="dita-map",
        title="Test Map", id="test-map",
        topicrefs=[
            TopicRef(href="topic1.dita", navtitle="Topic 1", id="ref1", keys="k1"),
            TopicRef(href="topic2.dita", navtitle="Topic 2", id="ref2", keys="",
                     children=[TopicRef(href="sub.dita", navtitle="Sub", id="ref3")]),
        ],
    )
    xml_bytes = render_map_xml(doc)
    root = etree.fromstring(xml_bytes)
    assert root.tag == "map"
    # Title
    title = root.find("title")
    assert title is not None
    # Topicrefs
    refs = root.findall("topicref")
    assert len(refs) == 2
    assert refs[0].get("href") == "topic1.dita"
    assert refs[0].get("keys") == "k1"
    # Nested
    nested = refs[1].findall("topicref")
    assert len(nested) == 1
    assert nested[0].get("href") == "sub.dita"


# ---------------------------------------------------------------------------
# Roundtrip test: Authoring JSON -> XML -> convert_xml -> domain_json
# ---------------------------------------------------------------------------

def test_roundtrip_via_converter():
    """Authoring JSON -> XML -> existing convert_xml -> domain_json should preserve title and sections."""
    from app.parser import convert_xml

    doc = AuthoringDoc(
        template="dita-topic",
        title="Roundtrip Test",
        id="rt",
        sections=[
            Section(
                heading="Results", id="s1",
                paragraphs=[Paragraph(text="Roundtrip works!", id="p1")],
            ),
        ],
    )
    xml_bytes = render_topic_xml(doc)
    result = convert_xml(xml_bytes, "roundtrip.xml")
    assert result["ok"] is True
    domain = result["domain_json"]
    assert domain["title"] == "Roundtrip Test"
    assert len(domain["sections"]) >= 1
    # The section heading should be preserved
    assert any("Results" in str(sec) for sec in domain["sections"])


def test_roundtrip_ditamap_via_converter():
    """Authoring DITA map -> XML -> convert_xml should produce dita_map in domain_json."""
    from app.parser import convert_xml

    doc = AuthoringDoc(
        template="dita-map",
        title="Map Roundtrip",
        id="mr",
        topicrefs=[
            TopicRef(href="a.dita", navtitle="A", id="ra"),
            TopicRef(href="b.dita", navtitle="B", id="rb"),
        ],
    )
    xml_bytes = render_map_xml(doc)
    result = convert_xml(xml_bytes, "roundtrip.ditamap")
    assert result["ok"] is True
    domain = result["domain_json"]
    assert "dita_map" in domain
    assert len(domain["dita_map"]["topicrefs"]) == 2


# ---------------------------------------------------------------------------
# render_document_json
# ---------------------------------------------------------------------------

def test_render_document_json_topic():
    doc = AuthoringDoc(
        template="dita-topic",
        title="JSON Test", id="jt",
        sections=[Section(heading="S1", id="s1", paragraphs=[Paragraph(text="Hello", id="p1")])],
    )
    domain = render_document_json(doc)
    assert domain["title"] == "JSON Test"
    assert len(domain["sections"]) == 1
    assert domain["sections"][0]["heading"] == "S1"


def test_render_document_json_map():
    doc = AuthoringDoc(
        template="dita-map",
        title="Map JSON", id="mj",
        topicrefs=[TopicRef(href="x.dita", navtitle="X", id="rx")],
    )
    domain = render_document_json(doc)
    assert "dita_map" in domain
    assert len(domain["dita_map"]["topicrefs"]) == 1