"""Authoring JSON model — a browser-editable document model for SIMQIN/DITA XML.

This module defines the Pydantic-like dataclasses used to represent a
structured document being authored in the browser.  The model is serialised
as JSON on the wire and converted to actual XML by ``xml_writer.py``.
"""

from __future__ import annotations

from typing import Any


# ---------------------------------------------------------------------------
# Simple dataclass replacements (no Pydantic dependency needed)
# ---------------------------------------------------------------------------

class AuthoringValidationError(ValueError):
    """Raised when an authoring JSON document fails validation."""


class AuthoringDoc:
    """Top-level authoring document.

    Attributes:
        template:       Template identifier (e.g. "dita-topic", "sop", "dita-map").
        title:          Document title.
        id:             Optional root ID (auto-generated if omitted).
        sections:       Ordered list of sections (only for topic-like templates).
        topicrefs:      TopicRef list (only for map-like templates).
        assets:         Image references.
        references:     Link/xref references.
    """

    def __init__(
        self,
        template: str,
        title: str = "",
        id: str = "",
        sections: list["Section"] | None = None,
        topicrefs: list["TopicRef"] | None = None,
        assets: list["AssetRef"] | None = None,
        references: list["ReferenceRef"] | None = None,
    ) -> None:
        self.template = template
        self.title = title
        self.id = id or _make_id(title or "doc")
        self.sections = sections or []
        self.topicrefs = topicrefs or []
        self.assets = assets or []
        self.references = references or []

    def to_dict(self) -> dict[str, Any]:
        return {
            "template": self.template,
            "title": self.title,
            "id": self.id,
            "sections": [s.to_dict() for s in self.sections],
            "topicrefs": [t.to_dict() for t in self.topicrefs],
            "assets": [a.to_dict() for a in self.assets],
            "references": [r.to_dict() for r in self.references],
        }

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "AuthoringDoc":
        return cls(
            template=d.get("template", "dita-topic"),
            title=d.get("title", ""),
            id=d.get("id", ""),
            sections=[Section.from_dict(s) for s in d.get("sections", [])],
            topicrefs=[TopicRef.from_dict(t) for t in d.get("topicrefs", [])],
            assets=[AssetRef.from_dict(a) for a in d.get("assets", [])],
            references=[ReferenceRef.from_dict(r) for r in d.get("references", [])],
        )

    def validate(self) -> list[str]:
        errors: list[str] = []
        if not self.title.strip():
            errors.append("Title is required.")
        if not self.id.strip():
            errors.append("Document ID is required.")
        if self.template in ("dita-topic", "sop"):
            for i, sec in enumerate(self.sections):
                sec_errors = sec.validate(i)
                errors.extend(sec_errors)
            for i, a in enumerate(self.assets):
                if not a.href.strip():
                    errors.append(f"assets[{i}]: href is required.")
            for i, r in enumerate(self.references):
                if not r.href.strip():
                    errors.append(f"references[{i}]: href is required.")
        return errors


class Section:
    """A single document section with optional heading, paragraphs, tables,
    images, and links."""

    def __init__(
        self,
        heading: str = "",
        id: str = "",
        paragraphs: list["Paragraph"] | None = None,
        tables: list["TableBlock"] | None = None,
        images: list["ImageRef"] | None = None,
        links: list["LinkRef"] | None = None,
    ) -> None:
        self.heading = heading
        self.id = id or _make_id(heading or "section")
        self.paragraphs = paragraphs or []
        self.tables = tables or []
        self.images = images or []
        self.links = links or []

    def to_dict(self) -> dict[str, Any]:
        return {
            "heading": self.heading,
            "id": self.id,
            "paragraphs": [p.to_dict() for p in self.paragraphs],
            "tables": [t.to_dict() for t in self.tables],
            "images": [i.to_dict() for i in self.images],
            "links": [l.to_dict() for l in self.links],
        }

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "Section":
        return cls(
            heading=d.get("heading", ""),
            id=d.get("id", ""),
            paragraphs=[Paragraph.from_dict(p) for p in d.get("paragraphs", [])],
            tables=[TableBlock.from_dict(t) for t in d.get("tables", [])],
            images=[ImageRef.from_dict(i) for i in d.get("images", [])],
            links=[LinkRef.from_dict(l) for l in d.get("links", [])],
        )

    def validate(self, index: int) -> list[str]:
        errors: list[str] = []
        if not self.heading.strip():
            errors.append(f"sections[{index}]: section heading is required.")
        return errors


class Paragraph:
    """A paragraph of text content."""

    def __init__(self, text: str = "", id: str = "") -> None:
        self.text = text
        self.id = id or ""

    def to_dict(self) -> dict[str, Any]:
        return {"text": self.text, "id": self.id}

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "Paragraph":
        return cls(text=d.get("text", ""), id=d.get("id", ""))


class TableBlock:
    """A table with caption and rows of cells."""

    def __init__(
        self,
        caption: str = "",
        id: str = "",
        rows: list[list[str]] | None = None,
    ) -> None:
        self.caption = caption
        self.id = id or _make_id(caption or "table")
        self.rows = rows or []

    def to_dict(self) -> dict[str, Any]:
        return {"caption": self.caption, "id": self.id, "rows": self.rows}

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "TableBlock":
        return cls(
            caption=d.get("caption", ""),
            id=d.get("id", ""),
            rows=d.get("rows", []),
        )


class ImageRef:
    """A reference to an image asset."""

    def __init__(
        self,
        src: str = "",
        alt: str = "",
        id: str = "",
    ) -> None:
        self.src = src
        self.alt = alt
        self.id = id or _make_id(alt or "img")

    def to_dict(self) -> dict[str, Any]:
        return {"src": self.src, "alt": self.alt, "id": self.id}

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "ImageRef":
        return cls(src=d.get("src", ""), alt=d.get("alt", ""), id=d.get("id", ""))


class LinkRef:
    """A cross-reference or hyperlink."""

    def __init__(
        self,
        href: str = "",
        text: str = "",
        id: str = "",
    ) -> None:
        self.href = href
        self.text = text
        self.id = id or _make_id(text or "link")

    def to_dict(self) -> dict[str, Any]:
        return {"href": self.href, "text": self.text, "id": self.id}

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "LinkRef":
        return cls(
            href=d.get("href", ""),
            text=d.get("text", ""),
            id=d.get("id", ""),
        )


# --- For DITA maps ---

class TopicRef:
    """A topicref entry in a DITA map."""

    def __init__(
        self,
        href: str = "",
        navtitle: str = "",
        id: str = "",
        keys: str = "",
        children: list["TopicRef"] | None = None,
    ) -> None:
        self.href = href
        self.navtitle = navtitle
        self.id = id or _make_id(navtitle or "ref")
        self.keys = keys
        self.children = children or []

    def to_dict(self) -> dict[str, Any]:
        return {
            "href": self.href,
            "navtitle": self.navtitle,
            "id": self.id,
            "keys": self.keys,
            "children": [c.to_dict() for c in self.children],
        }

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "TopicRef":
        return cls(
            href=d.get("href", ""),
            navtitle=d.get("navtitle", ""),
            id=d.get("id", ""),
            keys=d.get("keys", ""),
            children=[cls.from_dict(c) for c in d.get("children", [])],
        )


class AssetRef:
    """A top-level asset reference of the document."""

    def __init__(self, type: str = "image", href: str = "", alt: str = "") -> None:
        self.type = type
        self.href = href
        self.alt = alt

    def to_dict(self) -> dict[str, Any]:
        return {"type": self.type, "href": self.href, "alt": self.alt}

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "AssetRef":
        return cls(
            type=d.get("type", "image"),
            href=d.get("href", ""),
            alt=d.get("alt", ""),
        )


class ReferenceRef:
    """A top-level reference of the document."""

    def __init__(self, type: str = "xref", href: str = "", text: str = "") -> None:
        self.type = type
        self.href = href
        self.text = text

    def to_dict(self) -> dict[str, Any]:
        return {"type": self.type, "href": self.href, "text": self.text}

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "ReferenceRef":
        return cls(
            type=d.get("type", "xref"),
            href=d.get("href", ""),
            text=d.get("text", ""),
        )


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

import re

_ID_COUNTER: int = 0


def _make_id(hint: str) -> str:
    """Generate a simple XML-safe ID from *hint*."""
    global _ID_COUNTER
    _ID_COUNTER += 1
    base = re.sub(r"[^a-zA-Z0-9_-]", "", hint.lower().replace(" ", "-")) or "id"
    return f"{base}-{_ID_COUNTER}"