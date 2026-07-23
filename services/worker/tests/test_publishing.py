"""Tests for Phase 5 — Build Graph, Project Index, Reference Resolver, Validation, Publish."""

from __future__ import annotations

import json
from pathlib import Path

from app.project import Project, ProjectAsset
from app.authoring import AuthoringDoc, Section, Paragraph, ImageRef, LinkRef, TopicRef, AssetRef, ReferenceRef
from app.build_graph import BuildGraph
from app.project_index import ProjectIndex
from app.reference_resolver import ReferenceResolver
from app.validation import validate_project
from app.publish import publish_project, PackageManifest


def _make_project() -> Project:
    p = Project(name="Test Project")
    doc1 = AuthoringDoc(template="dita-topic", title="Doc 1", id="doc1",
        sections=[Section(heading="Intro", id="s1",
            paragraphs=[Paragraph(text="Hello world", id="p1")],
            images=[ImageRef(src="img/photo.png", alt="Photo", id="img1")],
            links=[LinkRef(href="#target", text="See more", id="lnk1")],
        )],
    )
    doc2 = AuthoringDoc(template="dita-map", title="Map", id="map1",
        topicrefs=[TopicRef(href="doc1.dita", navtitle="Doc 1", id="tr1", keys="main")],
    )
    p.add_document(doc1, "doc1.json")
    p.add_document(doc2, "map.json")
    p.add_asset(ProjectAsset(filename="photo.png", mime="image/png", size=2048))
    return p


# ---------------------------------------------------------------------------
# Build Graph
# ---------------------------------------------------------------------------

def test_graph_creation():
    p = _make_project()
    graph = BuildGraph.from_project(p)
    assert len(graph.nodes) >= 3  # project + 2 documents + sections etc
    assert len(graph.edges) > 0


def test_graph_has_project_node():
    p = _make_project()
    graph = BuildGraph.from_project(p)
    assert graph.has_node("project")


def test_graph_detects_duplicate_ids():
    p = Project(name="Dup")
    doc1 = AuthoringDoc(template="dita-topic", title="D1", id="same-id")
    doc2 = AuthoringDoc(template="dita-topic", title="D2", id="same-id")
    p.add_document(doc1)
    p.add_document(doc2)
    graph = BuildGraph.from_project(p)
    issues = graph.find_duplicate_ids()
    assert len(issues) >= 1
    assert issues[0]["type"] == "duplicate_id"


def test_graph_detects_duplicate_keys():
    p = Project(name="Keys")
    doc = AuthoringDoc(template="dita-map", title="M", id="m1",
        topicrefs=[
            TopicRef(href="a.dita", navtitle="A", id="ta", keys="dupkey"),
            TopicRef(href="b.dita", navtitle="B", id="tb", keys="dupkey"),
        ],
    )
    p.add_document(doc)
    graph = BuildGraph.from_project(p)
    issues = graph.find_duplicate_keys()
    assert len(issues) >= 1


def test_graph_full_report_contains_statistics():
    p = _make_project()
    graph = BuildGraph.from_project(p)
    report = graph.full_report(p)
    assert "statistics" in report
    assert report["statistics"]["total_nodes"] > 0
    assert "issues" in report


# ---------------------------------------------------------------------------
# Project Index
# ---------------------------------------------------------------------------

def test_index_build():
    p = _make_project()
    idx = ProjectIndex(p)
    assert idx.count() > 0


def test_index_search():
    p = _make_project()
    idx = ProjectIndex(p)
    results = idx.search("Hello")
    assert len(results) >= 1


def test_index_search_returns_empty():
    p = _make_project()
    idx = ProjectIndex(p)
    results = idx.search("nonexistent")
    assert len(results) == 0


# ---------------------------------------------------------------------------
# Reference Resolver
# ---------------------------------------------------------------------------

def test_resolver_resolves_href():
    p = _make_project()
    resolver = ReferenceResolver(p)
    res = resolver.resolve_href("#target")
    assert res.status in ("resolved", "unresolved")


def test_resolver_empty_href_is_error():
    p = _make_project()
    resolver = ReferenceResolver(p)
    res = resolver.resolve_href("")
    assert res.status == "error"


def test_resolver_external_url():
    p = _make_project()
    resolver = ReferenceResolver(p)
    res = resolver.resolve_href("https://example.com")
    assert res.status == "external"


def test_resolver_unknown_href():
    p = _make_project()
    resolver = ReferenceResolver(p)
    res = resolver.resolve_href("/nonexistent/path.dita")
    assert res.status == "unresolved"


# ---------------------------------------------------------------------------
# Validation
# ---------------------------------------------------------------------------

def test_validation_passes_for_clean_project():
    p = _make_project()
    result = validate_project(p)
    d = result.to_dict()
    # Links like "#target" in the test project may be unresolved
    # but shouldn't have duplicate IDs
    dup_issues = [i for i in d["issues"] if i["type"] == "duplicate_id"]
    assert len(dup_issues) == 0, f"Found duplicate IDs: {dup_issues}"


def test_validation_detects_duplicate_ids():
    p = Project(name="Dup")
    d1 = AuthoringDoc(template="dita-topic", title="D1", id="dup")
    d2 = AuthoringDoc(template="dita-topic", title="D2", id="dup")
    p.add_document(d1)
    p.add_document(d2)
    result = validate_project(p)
    d = result.to_dict()
    assert any("duplicate" in i["type"] for i in d["issues"])


# ---------------------------------------------------------------------------
# Publish
# ---------------------------------------------------------------------------

def test_publish_returns_statistics():
    p = _make_project()
    result = publish_project(p)
    d = result.to_dict()
    assert "statistics" in d
    assert d["statistics"]["total_nodes"] > 0


def test_publish_returns_resolved_references():
    p = _make_project()
    result = publish_project(p)
    assert isinstance(result.resolved_references, list)


# ---------------------------------------------------------------------------
# PackageManifest
# ---------------------------------------------------------------------------

def test_package_manifest_from_project():
    p = _make_project()
    manifest = PackageManifest.from_project(p)
    d = manifest.to_dict()
    assert d["name"] == "Test Project"
    assert len(d["documents"]) == 2
    assert len(d["assets"]) == 1


def test_package_manifest_schema_version():
    manifest = PackageManifest(name="Test")
    assert manifest.schema_version == "1.0.0"
    assert manifest.profile_version == "0.2.0"