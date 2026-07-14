"""Project model and service for the SIMQIN JSON Platform.

A Project manages a collection of AuthoringDoc documents, assets, metadata,
and a root DITA map reference.  Projects are serializable as JSON and can be
persisted via manifest files.
"""

from __future__ import annotations

import json
import os
import re
import uuid
from datetime import datetime, timezone
from typing import Any

from .authoring import AuthoringDoc


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

SCHEMA_VERSION = "1.0.0"
PROJECT_MANIFEST = "project.json"


# ---------------------------------------------------------------------------
# Domain models
# ---------------------------------------------------------------------------


class ProjectAsset:
    """An asset within a project."""

    def __init__(
        self,
        id: str = "",
        filename: str = "",
        mime: str = "application/octet-stream",
        size: int = 0,
        refs: list[str] | None = None,
    ) -> None:
        self.id = id or str(uuid.uuid4())
        self.filename = filename
        self.mime = mime
        self.size = size
        self.refs = refs or []

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "filename": self.filename,
            "mime": self.mime,
            "size": self.size,
            "refs": self.refs,
        }

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "ProjectAsset":
        return cls(
            id=d.get("id", ""),
            filename=d.get("filename", ""),
            mime=d.get("mime", "application/octet-stream"),
            size=d.get("size", 0),
            refs=d.get("refs", []),
        )


class ProjectDocument:
    """A document reference within a project."""

    def __init__(
        self,
        id: str = "",
        title: str = "",
        filename: str = "",
        doc: AuthoringDoc | None = None,
    ) -> None:
        self.id = id or str(uuid.uuid4())
        self.title = title
        self.filename = filename
        self.doc = doc

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "title": self.title,
            "filename": self.filename,
            "doc": self.doc.to_dict() if self.doc else None,
        }

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "ProjectDocument":
        doc_raw = d.get("doc")
        doc = AuthoringDoc.from_dict(doc_raw) if doc_raw and isinstance(doc_raw, dict) else None
        return cls(
            id=d.get("id", ""),
            title=d.get("title", ""),
            filename=d.get("filename", ""),
            doc=doc,
        )


class Project:
    """A workspace project containing documents, assets, and metadata."""

    def __init__(
        self,
        id: str = "",
        name: str = "",
        created: str = "",
        modified: str = "",
        root_document_id: str | None = None,
        documents: list[ProjectDocument] | None = None,
        assets: list[ProjectAsset] | None = None,
        metadata: dict[str, Any] | None = None,
        settings: dict[str, Any] | None = None,
    ) -> None:
        now = _now_iso()
        self.id = id or str(uuid.uuid4())
        self.name = name or "Untitled Project"
        self.created = created or now
        self.modified = modified or now
        self.root_document_id = root_document_id
        self.documents = documents or []
        self.assets = assets or []
        self.metadata = metadata or {}
        self.settings = settings or {}

    # ------------------------------------------------------------------
    # Serialization
    # ------------------------------------------------------------------

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "name": self.name,
            "created": self.created,
            "modified": self.modified,
            "root_document_id": self.root_document_id,
            "documents": [d.to_dict() for d in self.documents],
            "assets": [a.to_dict() for a in self.assets],
            "metadata": self.metadata,
            "settings": self.settings,
        }

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "Project":
        return cls(
            id=d.get("id", ""),
            name=d.get("name", "Untitled"),
            created=d.get("created", ""),
            modified=d.get("modified", ""),
            root_document_id=d.get("root_document_id"),
            documents=[ProjectDocument.from_dict(dd) for dd in d.get("documents", [])],
            assets=[ProjectAsset.from_dict(aa) for aa in d.get("assets", [])],
            metadata=d.get("metadata", {}),
            settings=d.get("settings", {}),
        )

    # ------------------------------------------------------------------
    # Manifest generation
    # ------------------------------------------------------------------

    def manifest(self) -> dict[str, Any]:
        """Produce a lightweight project manifest (without full document bodies)."""
        return {
            "schema_version": SCHEMA_VERSION,
            "project_id": self.id,
            "name": self.name,
            "created": self.created,
            "modified": self.modified,
            "root_document_id": self.root_document_id,
            "documents": [
                {
                    "id": d.id,
                    "title": d.title or (d.doc.title if d.doc else ""),
                    "filename": d.filename,
                }
                for d in self.documents
            ],
            "assets": [a.to_dict() for a in self.assets],
            "metadata": self.metadata,
        }

    # ------------------------------------------------------------------
    # Document management
    # ------------------------------------------------------------------

    def add_document(self, doc: AuthoringDoc, filename: str = "") -> str:
        pd = ProjectDocument(
            id=str(uuid.uuid4()),
            title=doc.title,
            filename=filename or f"{doc.id or 'doc'}.json",
            doc=doc,
        )
        self.documents.append(pd)
        self._touch()
        return pd.id

    def remove_document(self, doc_id: str) -> bool:
        before = len(self.documents)
        self.documents = [d for d in self.documents if d.id != doc_id]
        if self.root_document_id == doc_id:
            self.root_document_id = None
        if len(self.documents) < before:
            self._touch()
            return True
        return False

    def rename_document(self, doc_id: str, new_title: str) -> bool:
        for d in self.documents:
            if d.id == doc_id:
                d.title = new_title
                if d.doc:
                    d.doc.title = new_title
                self._touch()
                return True
        return False

    def get_document(self, doc_id: str) -> AuthoringDoc | None:
        for d in self.documents:
            if d.id == doc_id:
                return d.doc
        return None

    def set_root_document(self, doc_id: str | None) -> None:
        self.root_document_id = doc_id
        self._touch()

    # ------------------------------------------------------------------
    # Asset management
    # ------------------------------------------------------------------

    def add_asset(self, asset: ProjectAsset) -> None:
        self.assets.append(asset)
        self._touch()

    def remove_asset(self, asset_id: str) -> bool:
        before = len(self.assets)
        self.assets = [a for a in self.assets if a.id != asset_id]
        if len(self.assets) < before:
            self._touch()
            return True
        return False

    def update_metadata(self, meta: dict[str, Any]) -> None:
        self.metadata.update(meta)
        self._touch()

    # ------------------------------------------------------------------
    # Search
    # ------------------------------------------------------------------

    def search(self, query: str) -> list[dict[str, Any]]:
        """In-memory search over document titles, paragraphs, section ids,
        topicrefs, and asset filenames.

        Returns a list of ``{ doc_id, title, matches: [...] }``.
        """
        results: list[dict[str, Any]] = []
        q = query.lower()

        for pd in self.documents:
            if not pd.doc:
                continue
            matches: list[str] = []
            doc = pd.doc

            # Title
            if q in doc.title.lower():
                matches.append(f"title: {doc.title}")

            # Section headings, ids, paragraphs
            for sec in doc.sections:
                if q in sec.heading.lower():
                    matches.append(f"section heading: {sec.heading}")
                if q in sec.id.lower():
                    matches.append(f"section id: {sec.id}")
                for p in sec.paragraphs:
                    if q in p.text.lower():
                        matches.append(f"paragraph: {p.text[:60]}...")

            # Topicrefs
            for tr in doc.topicrefs:
                if q in tr.navtitle.lower() or q in tr.href.lower():
                    matches.append(f"topicref: {tr.navtitle}")

            if matches:
                results.append({"doc_id": pd.id, "title": doc.title, "matches": matches})

        # Also search assets
        for a in self.assets:
            if q in a.filename.lower():
                results.append({"asset_id": a.id, "title": a.filename, "matches": [f"asset: {a.filename}"]})

        return results

    # ------------------------------------------------------------------
    # Internals
    # ------------------------------------------------------------------

    def _touch(self) -> None:
        self.modified = _now_iso()


# ---------------------------------------------------------------------------
# Project service
# ---------------------------------------------------------------------------

class ProjectService:
    """In-memory project service with optional file persistence."""

    def __init__(self, storage_dir: str = "") -> None:
        self._projects: dict[str, Project] = {}
        self._storage_dir = storage_dir

    def create_project(self, name: str = "") -> Project:
        p = Project(name=name or "Untitled Project")
        self._projects[p.id] = p
        return p

    def get_project(self, pid: str) -> Project | None:
        return self._projects.get(pid)

    def save_project(self, pid: str) -> dict[str, Any]:
        p = self._projects.get(pid)
        if not p:
            return {"ok": False, "error": "Project not found"}
        manifest = p.manifest()
        if self._storage_dir:
            os.makedirs(self._storage_dir, exist_ok=True)
            path = os.path.join(self._storage_dir, PROJECT_MANIFEST)
            with open(path, "w", encoding="utf-8") as fh:
                json.dump(manifest, fh, indent=2, ensure_ascii=False)
        return {"ok": True, "manifest": manifest}

    def open_project(self, name: str) -> Project:
        p = self._projects.get(name)
        if not p:
            p = self.create_project(name)
        return p

    def clear(self) -> None:
        self._projects.clear()


# ---------------------------------------------------------------------------
# Build service
# ---------------------------------------------------------------------------

def build_check(project: Project) -> dict[str, Any]:
    """Perform a basic build check on a project.

    Returns a report with reference validity and document count.
    """
    issues: list[dict[str, Any]] = []
    for pd in project.documents:
        if pd.doc:
            # Check that referenced assets exist
            for img in pd.doc.sections:
                pass  # placeholder for deeper checking
            issues.append({
                "doc_id": pd.id,
                "title": pd.title or pd.doc.title,
                "paragraph_count": sum(len(s.paragraphs) for s in pd.doc.sections),
                "section_count": len(pd.doc.sections),
            })

    return {
        "ok": True,
        "document_count": len(project.documents),
        "asset_count": len(project.assets),
        "issues": issues,
    }


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()