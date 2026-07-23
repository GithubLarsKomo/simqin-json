"""Reference resolver — resolves href, keyref, conref, and topicref references
within a Project.

Supports relative project paths and returns diagnostics.
"""

from __future__ import annotations

import os
from typing import Any

from .project import Project


class ReferenceResolution:
    """Result of resolving a single reference."""

    def __init__(
        self,
        ref_type: str,
        original: str,
        resolved: str | None = None,
        target_id: str | None = None,
        status: str = "unresolved",
        message: str = "",
    ) -> None:
        self.ref_type = ref_type
        self.original = original
        self.resolved = resolved
        self.target_id = target_id
        self.status = status
        self.message = message

    def to_dict(self) -> dict[str, Any]:
        return {
            "ref_type": self.ref_type,
            "original": self.original,
            "resolved": self.resolved,
            "target_id": self.target_id,
            "status": self.status,
            "message": self.message,
        }


class ReferenceResolver:
    """Resolves references within a Project."""

    def __init__(self, project: Project) -> None:
        self._project = project
        self._doc_map: dict[str, str] = {}  # id -> doc_id
        self._key_map: dict[str, str] = {}  # key -> href
        self._href_map: dict[str, str] = {}  # href -> doc_id
        self._build_maps()

    def _build_maps(self) -> None:
        for pd in self._project.documents:
            if not pd.doc:
                continue
            doc = pd.doc
            if doc.id:
                self._doc_map[doc.id] = pd.id
            # TopicRef keys
            for tr in doc.topicrefs:
                self._collect_keys(tr)
            for sec in doc.sections:
                if sec.id:
                    self._doc_map[sec.id] = pd.id

    def _collect_keys(self, tr) -> None:
        if tr.keys:
            self._key_map[tr.keys] = tr.href or ""
        if tr.href:
            self._href_map[tr.href] = tr.href
            # Strip path to extract filename
            fname = os.path.basename(tr.href)
            if fname:
                self._href_map[fname] = tr.href
        for child in tr.children:
            self._collect_keys(child)

    def resolve_href(self, href: str) -> ReferenceResolution:
        """Resolve an href to a target."""
        if not href:
            return ReferenceResolution("href", href, status="error", message="Empty href")

        # Check if href matches a document id
        if href in self._doc_map:
            return ReferenceResolution(
                "href", href, resolved=href, target_id=self._doc_map[href],
                status="resolved",
            )

        # Check if href is a known path
        if href in self._href_map:
            return ReferenceResolution(
                "href", href, resolved=self._href_map[href],
                status="resolved",
            )

        # External URLs are valid
        if href.startswith("http://") or href.startswith("https://"):
            return ReferenceResolution("href", href, resolved=href, status="external")

        return ReferenceResolution(
            "href", href, status="unresolved",
            message=f"href '{href}' could not be resolved in project",
        )

    def resolve_keyref(self, keyref: str) -> ReferenceResolution:
        """Resolve a keyref to its target href."""
        if not keyref:
            return ReferenceResolution("keyref", keyref, status="error", message="Empty keyref")

        if keyref in self._key_map:
            target = self._key_map[keyref]
            return ReferenceResolution(
                "keyref", keyref, resolved=target, status="resolved",
            )

        return ReferenceResolution(
            "keyref", keyref, status="unresolved",
            message=f"Key '{keyref}' not defined in project",
        )

    def resolve_conref(self, conref: str) -> ReferenceResolution:
        """Resolve a conref (placeholder for future implementation)."""
        return ReferenceResolution(
            "conref", conref, status="not_implemented",
            message="Conref resolution not yet implemented",
        )

    def resolve_topicref(self, href: str) -> ReferenceResolution:
        """Resolve a topicref href."""
        return self.resolve_href(href)

    def resolve_all(self) -> list[dict[str, Any]]:
        """Resolve all references in the project and return diagnostics."""
        results: list[dict[str, Any]] = []

        for pd in self._project.documents:
            if not pd.doc:
                continue
            doc = pd.doc

            # TopicRef hrefs
            for tr in doc.topicrefs:
                self._resolve_topicref_recursive(tr, results)

            # Section links
            for sec in doc.sections:
                for lnk in sec.links:
                    if lnk.href:
                        res = self.resolve_href(lnk.href)
                        d = res.to_dict()
                        d["doc_id"] = pd.id
                        d["source"] = f"section/{sec.id}" if sec.id else "section"
                        results.append(d)

        return results

    def _resolve_topicref_recursive(self, tr, results: list[dict[str, Any]]) -> None:
        if tr.href:
            res = self.resolve_href(tr.href)
            d = res.to_dict()
            d["doc_id"] = next(
                (pd.id for pd in self._project.documents if pd.doc and pd.doc.id == tr.id),
                None,
            )
            d["source"] = f"topicref/{tr.id}" if tr.id else "topicref"
            results.append(d)
        for child in tr.children:
            self._resolve_topicref_recursive(child, results)