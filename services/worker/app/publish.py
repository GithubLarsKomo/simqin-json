"""Publishing service — resolves, normalizes, and produces a PublishResult.

Pipeline:
  Project
    -> Resolved Project (references resolved)
    -> Normalized XML
    -> PublishResult (statistics + diagnostics)
"""

from __future__ import annotations

from typing import Any

from .project import Project
from .build_graph import BuildGraph
from .reference_resolver import ReferenceResolver
from .validation import validate_project


class PublishResult:
    """Result of a publish operation."""

    def __init__(self) -> None:
        self.statistics: dict[str, Any] = {}
        self.warnings: list[dict[str, Any]] = []
        self.errors: list[dict[str, Any]] = []
        self.resolved_references: list[dict[str, Any]] = []
        self.unused_assets: list[dict[str, Any]] = []
        self.orphan_documents: list[dict[str, Any]] = []

    def to_dict(self) -> dict[str, Any]:
        return {
            "statistics": self.statistics,
            "warnings": self.warnings,
            "errors": self.errors,
            "resolved_references": self.resolved_references,
            "unused_assets": self.unused_assets,
            "orphan_documents": self.orphan_documents,
            "ok": len(self.errors) == 0,
        }


def publish_project(project: Project) -> PublishResult:
    """Run the full publishing pipeline on *project*.

    Steps:
      1. Validate project
      2. Build dependency graph
      3. Resolve references
      4. Generate report
    """
    result = PublishResult()

    # 1. Validation
    validation = validate_project(project)
    for issue in validation.issues:
        entry = {
            "level": issue.level,
            "type": issue.type,
            "message": issue.message,
            "doc_id": issue.doc_id,
            "path": issue.path,
        }
        if issue.level in ("ERROR", "FATAL"):
            result.errors.append(entry)
        elif issue.level == "WARNING":
            result.warnings.append(entry)

    # 2. Graph
    graph = BuildGraph.from_project(project)
    report = graph.full_report(project)
    result.statistics = report["statistics"]

    # 3. Reference resolution
    resolver = ReferenceResolver(project)
    refs = resolver.resolve_all()
    result.resolved_references = refs

    # 4. Unused assets
    for issue in report["issues"]:
        if issue["type"] == "orphan_asset":
            result.unused_assets.append({
                "asset_id": issue.get("asset_id"),
                "filename": issue.get("filename"),
            })
        if issue["type"] == "orphan_document":
            result.orphan_documents.append({
                "doc_id": issue.get("doc_id"),
                "title": issue.get("title"),
            })

    return result


# ---------------------------------------------------------------------------
# Package manifest model
# ---------------------------------------------------------------------------


class PackageManifest:
    """Represents a package-ready manifest with checksums."""

    def __init__(
        self,
        name: str = "",
        documents: list[dict[str, Any]] | None = None,
        assets: list[dict[str, Any]] | None = None,
        schema_version: str = "1.0.0",
        profile_version: str = "0.2.0",
    ) -> None:
        self.name = name
        self.documents = documents or []
        self.assets = assets or []
        self.schema_version = schema_version
        self.profile_version = profile_version

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "schema_version": self.schema_version,
            "profile_version": self.profile_version,
            "documents": self.documents,
            "assets": self.assets,
        }

    @classmethod
    def from_project(cls, project: Project) -> "PackageManifest":
        docs = []
        for pd in project.documents:
            doc_entry = {
                "id": pd.id,
                "title": pd.title,
                "filename": pd.filename or f"{pd.id}.json",
            }
            if pd.doc:
                doc_entry["template"] = pd.doc.template
            docs.append(doc_entry)

        assets = [a.to_dict() for a in project.assets]

        return cls(
            name=project.name,
            documents=docs,
            assets=assets,
        )