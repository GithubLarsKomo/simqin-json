"""Project index — searchable in-memory index for a Project.

Indexes titles, ids, keys, paragraphs, sections, assets, topicrefs, metadata.
"""

from __future__ import annotations

from typing import Any

from .project import Project


class ProjectIndex:
    """Searchable project index built from a Project."""

    def __init__(self, project: Project | None = None) -> None:
        self._entries: list[dict[str, Any]] = []
        if project:
            self.build(project)

    def build(self, project: Project) -> None:
        self._entries = []

        for pd in project.documents:
            if not pd.doc:
                continue
            doc = pd.doc

            # Title
            self._entries.append({
                "doc_id": pd.id,
                "type": "title",
                "value": doc.title,
                "path": "title",
            })

            # Id
            if doc.id:
                self._entries.append({
                    "doc_id": pd.id, "type": "id", "value": doc.id, "path": "id",
                })

            # Sections
            for sec in doc.sections:
                if sec.heading:
                    self._entries.append({
                        "doc_id": pd.id, "type": "section", "value": sec.heading,
                        "path": f"sections/{sec.id}" if sec.id else "sections",
                    })
                for para in sec.paragraphs:
                    if para.text.strip():
                        self._entries.append({
                            "doc_id": pd.id, "type": "paragraph", "value": para.text,
                            "path": f"sections/{sec.id}/paragraphs" if sec.id else "paragraphs",
                        })

            # TopicRefs
            for tr in doc.topicrefs:
                self._add_topicref_entries(tr, pd.id)

            # Assets
            for a in doc.assets:
                if a.href:
                    self._entries.append({
                        "doc_id": pd.id, "type": "asset", "value": a.href,
                        "path": "assets",
                    })

            # References
            for r in doc.references:
                if r.href:
                    self._entries.append({
                        "doc_id": pd.id, "type": "reference", "value": r.href,
                        "path": "references",
                    })

    def _add_topicref_entries(self, tr, doc_id: str) -> None:
        if tr.navtitle:
            self._entries.append({
                "doc_id": doc_id, "type": "topicref",
                "value": tr.navtitle, "path": f"topicref/{tr.id}",
            })
        if tr.keys:
            self._entries.append({
                "doc_id": doc_id, "type": "key",
                "value": tr.keys, "path": f"topicref/{tr.id}/keys",
            })
        for child in tr.children:
            self._add_topicref_entries(child, doc_id)

    def search(self, query: str) -> list[dict[str, Any]]:
        """Full-text search across all indexed entries.

        Returns entries whose ``value`` contains *query* (case-insensitive).
        """
        q = query.lower()
        return [
            e for e in self._entries if q in e["value"].lower()
        ]

    def all_entries(self) -> list[dict[str, Any]]:
        return self._entries

    def count(self) -> int:
        return len(self._entries)