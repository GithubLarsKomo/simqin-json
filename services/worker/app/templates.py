"""Templates for the SIMQIN / DITA authoring UI.

Each template returns an ``AuthoringDoc`` pre-populated with sensible
default content.
"""

from __future__ import annotations

from .authoring import (
    AuthoringDoc,
    Section,
    Paragraph,
    TableBlock,
    ImageRef,
    LinkRef,
    TopicRef,
)


# ---------------------------------------------------------------------------
# Template registry
# ---------------------------------------------------------------------------

TEMPLATES: dict[str, dict] = {
    "dita-topic": {
        "name": "DITA Topic",
        "description": "Eine standardkonforme DITA Topic-Datei mit Titel, Abschnitten, Absätzen, Tabellen, Bildern und Verweisen.",
        "default_id": "new-topic",
        "default_title": "Neues Thema",
    },
    "sop": {
        "name": "SOP-Dokument",
        "description": "Ein SOP-ähnliches Dokument (Standard Operating Procedure) mit strukturierten Abschnitten.",
        "default_id": "new-sop",
        "default_title": "Standard Operating Procedure",
    },
    "dita-map": {
        "name": "DITA Map",
        "description": "Eine DITA Map mit verschachtelbaren TopicRefs.",
        "default_id": "new-map",
        "default_title": "Neue DITA Map",
    },
}


def list_templates() -> list[dict]:
    """Return all available templates as a list of summary dicts."""
    return [
        {
            "id": tid,
            "name": info["name"],
            "description": info["description"],
        }
        for tid, info in TEMPLATES.items()
    ]


def create_document(template_id: str) -> AuthoringDoc:
    """Create a new ``AuthoringDoc`` from the given template ID.

    Raises ``ValueError`` if *template_id* is unknown.
    """
    if template_id not in TEMPLATES:
        raise ValueError(f"Unknown template: {template_id}")

    info = TEMPLATES[template_id]
    doc_id = info["default_id"]
    title = info["default_title"]

    if template_id == "dita-topic":
        return AuthoringDoc(
            template="dita-topic",
            id=doc_id,
            title=title,
            sections=[
                Section(
                    heading="Einleitung",
                    id=f"{doc_id}-intro",
                    paragraphs=[
                        Paragraph(text="Dies ist der erste Absatz der Einleitung. Ersetzen Sie diesen Text durch Ihren Inhalt."),
                        Paragraph(text="Weitere Informationen finden Sie im nächsten Abschnitt."),
                    ],
                    links=[
                        LinkRef(href="#next-section", text="Zum nächsten Abschnitt"),
                    ],
                ),
            ],
        )

    if template_id == "sop":
        return AuthoringDoc(
            template="sop",
            id=doc_id,
            title=title,
            sections=[
                Section(
                    heading="Zweck",
                    id=f"{doc_id}-purpose",
                    paragraphs=[Paragraph(text="Beschreiben Sie den Zweck dieses Dokuments.")],
                ),
                Section(
                    heading="Geltungsbereich",
                    id=f"{doc_id}-scope",
                    paragraphs=[Paragraph(text="Definieren Sie den Geltungsbereich.")],
                ),
                Section(
                    heading="Verantwortlichkeiten",
                    id=f"{doc_id}-responsibilities",
                    paragraphs=[Paragraph(text="Wer ist für die Umsetzung verantwortlich?")],
                ),
                Section(
                    heading="Durchführung",
                    id=f"{doc_id}-procedure",
                    paragraphs=[Paragraph(text="Schritt-für-Schritt-Anleitung.")],
                    tables=[
                        TableBlock(
                            caption="Arbeitsschritte",
                            id=f"{doc_id}-steps-table",
                            rows=[
                                ["Schritt", "Beschreibung", "Verantwortlich"],
                                ["1", "", ""],
                                ["2", "", ""],
                            ],
                        ),
                    ],
                ),
            ],
        )

    if template_id == "dita-map":
        return AuthoringDoc(
            template="dita-map",
            id=doc_id,
            title=title,
            topicrefs=[
                TopicRef(
                    href="topic-einleitung.dita",
                    navtitle="Einleitung",
                    id=f"{doc_id}-ref-intro",
                ),
                TopicRef(
                    href="topic-hauptteil.dita",
                    navtitle="Hauptteil",
                    id=f"{doc_id}-ref-main",
                    keys="main",
                    children=[
                        TopicRef(
                            href="topic-abschnitt-1.dita",
                            navtitle="Abschnitt 1",
                            id=f"{doc_id}-ref-sec1",
                        ),
                    ],
                ),
            ],
        )

    # Fallback: bare document
    return AuthoringDoc(template=template_id, id=doc_id, title=title)