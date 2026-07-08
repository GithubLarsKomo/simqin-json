"""XML writer — converts ``AuthoringDoc`` to actual DITA / SIMQIN XML.

Two public functions:

- ``render_topic_xml(doc) -> bytes`` — renders a DITA topic.
- ``render_map_xml(doc) -> bytes`` — renders a DITA map.
"""

from __future__ import annotations

import re
from typing import Any

from lxml import etree

from .authoring import AuthoringDoc, Section, Paragraph, TableBlock, ImageRef, LinkRef


def render_topic_xml(doc: AuthoringDoc) -> bytes:
    """Render a DITA topic XML document from *doc*."""
    nsmap = {None: "http://dita.oasis-open.org/architecture/dita"}
    topic = etree.Element("{http://dita.oasis-open.org/architecture/dita}topic", nsmap=nsmap)
    if doc.id:
        topic.set("id", doc.id)

    # Title
    title_el = etree.SubElement(topic, "{http://dita.oasis-open.org/architecture/dita}title")
    title_el.text = doc.title

    # Body
    body = etree.SubElement(topic, "{http://dita.oasis-open.org/architecture/dita}body")

    for sec in doc.sections:
        section_el = etree.SubElement(body, "{http://dita.oasis-open.org/architecture/dita}section")
        if sec.id:
            section_el.set("id", sec.id)

        # Section title
        sec_title = etree.SubElement(section_el, "{http://dita.oasis-open.org/architecture/dita}title")
        sec_title.text = sec.heading

        # Paragraphs
        for para in sec.paragraphs:
            p_el = etree.SubElement(section_el, "{http://dita.oasis-open.org/architecture/dita}p")
            if para.id:
                p_el.set("id", para.id)
            p_el.text = para.text

        # Tables
        for tbl in sec.tables:
            table_el = _render_table(tbl, nsmap)
            section_el.append(table_el)

        # Images
        for img in sec.images:
            img_el = _render_image(img, nsmap)
            section_el.append(img_el)

        # Links
        for link in sec.links:
            link_el = _render_link(link, nsmap)
            section_el.append(link_el)

    # Top-level assets (as <image> in the body)
    for asset in doc.assets:
        img_el = etree.SubElement(
            body, "{http://dita.oasis-open.org/architecture/dita}image"
        )
        if asset.href:
            img_el.set("href", asset.href)
        if asset.alt:
            img_el.set("alt", asset.alt)

    # Top-level references (as <xref> in the body)
    for ref in doc.references:
        xref_el = etree.SubElement(
            body, "{http://dita.oasis-open.org/architecture/dita}xref"
        )
        if ref.href:
            xref_el.set("href", ref.href)
        xref_el.text = ref.text

    xml_bytes = etree.tostring(
        topic, xml_declaration=True, encoding="UTF-8", pretty_print=True
    )
    return xml_bytes


def render_map_xml(doc: AuthoringDoc) -> bytes:
    """Render a DITA map XML document from *doc*."""
    map_el = etree.Element("map")
    if doc.id:
        map_el.set("id", doc.id)
    map_el.set("title", doc.title)

    # Title element
    title_el = etree.SubElement(map_el, "title")
    title_el.text = doc.title

    # Topicrefs
    for tref in doc.topicrefs:
        map_el.append(_render_topicref(tref))

    xml_bytes = etree.tostring(
        map_el, xml_declaration=True, encoding="UTF-8", pretty_print=True
    )
    return xml_bytes


def render_document_xml(doc: AuthoringDoc) -> bytes:
    """Render any document as XML — dispatches to topic or map renderer."""
    if doc.template in ("dita-map",):
        return render_map_xml(doc)
    return render_topic_xml(doc)


def render_document_json(doc: AuthoringDoc) -> dict[str, Any]:
    """Render an ``AuthoringDoc`` to the existing domain JSON format.

    This allows the existing frontend tabs (Canonical/Domain etc.)
    to display authored documents.
    """
    # Produce a flat domain-like JSON
    result: dict[str, Any] = {
        "title": doc.title,
        "sections": [],
        "assets": [a.to_dict() for a in doc.assets],
        "references": [r.to_dict() for r in doc.references],
        "metadata": {"root_element": "topic" if doc.template != "dita-map" else "map"},
    }

    for sec in doc.sections:
        result["sections"].append({
            "heading": sec.heading,
            "body": " ".join(p.text for p in sec.paragraphs if p.text),
            "tables": [t.to_dict() for t in sec.tables],
            "figures": [],
        })

    if doc.template == "dita-map":
        result["dita_map"] = {
            "id": doc.id,
            "title": doc.title,
            "topicrefs": _topicrefs_to_dicts(doc.topicrefs),
        }

    return result


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _render_table(tbl: TableBlock, nsmap: dict) -> etree._Element:
    table_el = etree.Element("{http://dita.oasis-open.org/architecture/dita}table")
    if tbl.id:
        table_el.set("id", tbl.id)
    if tbl.caption:
        caption_el = etree.SubElement(
            table_el, "{http://dita.oasis-open.org/architecture/dita}title"
        )
        caption_el.text = tbl.caption

    # Build tgroup with cols
    ncols = max((len(r) for r in tbl.rows), default=1)
    tgroup = etree.SubElement(
        table_el, "{http://dita.oasis-open.org/architecture/dita}tgroup"
    )
    tgroup.set("cols", str(ncols))
    # Colspecs
    for _ in range(ncols):
        etree.SubElement(tgroup, "{http://dita.oasis-open.org/architecture/dita}colspec")

    # Find header row and body rows
    if tbl.rows:
        thead = etree.SubElement(
            tgroup, "{http://dita.oasis-open.org/architecture/dita}thead"
        )
        header_row = etree.SubElement(
            thead, "{http://dita.oasis-open.org/architecture/dita}row"
        )
        for cell in tbl.rows[0]:
            entry = etree.SubElement(
                header_row, "{http://dita.oasis-open.org/architecture/dita}entry"
            )
            entry.text = cell

        tbody = etree.SubElement(
            tgroup, "{http://dita.oasis-open.org/architecture/dita}tbody"
        )
        for row_data in tbl.rows[1:]:
            row_el = etree.SubElement(
                tbody, "{http://dita.oasis-open.org/architecture/dita}row"
            )
            for cell in row_data:
                entry = etree.SubElement(
                    row_el, "{http://dita.oasis-open.org/architecture/dita}entry"
                )
                entry.text = cell

    return table_el


def _render_image(img: ImageRef, nsmap: dict) -> etree._Element:
    el = etree.Element("{http://dita.oasis-open.org/architecture/dita}image")
    if img.id:
        el.set("id", img.id)
    if img.src:
        el.set("href", img.src)
    if img.alt:
        el.set("alt", img.alt)
    return el


def _render_link(link: LinkRef, nsmap: dict) -> etree._Element:
    el = etree.Element("{http://dita.oasis-open.org/architecture/dita}xref")
    if link.id:
        el.set("id", link.id)
    if link.href:
        el.set("href", link.href)
    el.text = link.text
    return el


def _render_topicref(tref) -> etree._Element:
    el = etree.Element("topicref")
    if tref.href:
        el.set("href", tref.href)
    if tref.navtitle:
        el.set("navtitle", tref.navtitle)
    if tref.keys:
        el.set("keys", tref.keys)
    if tref.id:
        el.set("id", tref.id)
    for child in tref.children:
        el.append(_render_topicref(child))
    return el


def _topicrefs_to_dicts(trefs) -> list[dict[str, Any]]:
    """Convert TopicRef list to nested dicts for domain_json"""
    result = []
    for t in trefs:
        entry: dict[str, Any] = {
            "href": t.href,
            "navtitle": t.navtitle,
            "keys": t.keys,
        }
        entry = {k: v for k, v in entry.items() if v}
        if t.children:
            entry["topicrefs"] = _topicrefs_to_dicts(t.children)
        result.append(entry)
    return result