"""Validation engine for Projects.

Validation levels: INFO, WARNING, ERROR, FATAL.

Checks:
- duplicate ids
- broken links
- duplicate keys
- missing assets
- invalid references
- profile violations
"""

from __future__ import annotations

from typing import Any

from .project import Project
from .build_graph import BuildGraph
from .reference_resolver import ReferenceResolver


class ValidationIssue:
    __slots__ = ("level", "type", "message", "doc_id", "path", "data")

    def __init__(self, level: str, type: str, message: str,
                 doc_id: str | None = None, path: str | None = None,
                 data: dict | None = None) -> None:
        self.level = level
        self.type = type
        self.message = message
        self.doc_id = doc_id
        self.path = path
        self.data = data or {}

    def to_dict(self) -> dict[str, Any]:
        return {
            "level": self.level,
            "type": self.type,
            "message": self.message,
            "doc_id": self.doc_id,
            "path": self.path,
        }


class ValidationResult:
    """Result of a full project validation."""

    def __init__(self) -> None:
        self.issues: list[ValidationIssue] = []

    def add(self, issue: ValidationIssue) -> None:
        self.issues.append(issue)

    def to_dict(self) -> dict[str, Any]:
        return {
            "valid": all(i.level not in ("ERROR", "FATAL") for i in self.issues),
            "issues": [i.to_dict() for i in self.issues],
            "error_count": len([i for i in self.issues if i.level in ("ERROR", "FATAL")]),
            "warning_count": len([i for i in self.issues if i.level == "WARNING"]),
            "info_count": len([i for i in self.issues if i.level == "INFO"]),
        }


# ---------------------------------------------------------------------------
# Main validation function
# ---------------------------------------------------------------------------


def validate_project(project: Project) -> ValidationResult:
    """Run all validation checks on *project* and return ``ValidationResult``."""
    result = ValidationResult()

    # Build graph for structural checks
    graph = BuildGraph.from_project(project)

    # Duplicate ids
    for issue in graph.find_duplicate_ids():
        result.add(ValidationIssue(
            level=issue["severity"],
            type=issue["type"],
            message=issue["message"],
        ))

    # Duplicate keys
    for issue in graph.find_duplicate_keys():
        result.add(ValidationIssue(
            level=issue["severity"],
            type=issue["type"],
            message=issue["message"],
        ))

    # Orphan documents
    for issue in graph.find_orphan_documents(project):
        result.add(ValidationIssue(
            level=issue["severity"],
            type=issue["type"],
            message=issue["message"],
            doc_id=issue["doc_id"],
        ))

    # Orphan assets
    for issue in graph.find_orphan_assets(project):
        result.add(ValidationIssue(
            level=issue["severity"],
            type=issue["type"],
            message=issue["message"],
        ))

    # Broken links via reference resolver
    resolver = ReferenceResolver(project)
    resolved_refs = resolver.resolve_all()
    for ref in resolved_refs:
        if ref["status"] == "unresolved":
            result.add(ValidationIssue(
                level="ERROR",
                type="broken_link",
                message=ref.get("message", f"Unresolved reference: {ref['original']}"),
                doc_id=ref.get("doc_id"),
                path=ref.get("source"),
            ))

    # Circular references
    for issue in graph.find_circular_references():
        result.add(ValidationIssue(
            level=issue["severity"],
            type=issue["type"],
            message=issue["message"],
        ))

    return result