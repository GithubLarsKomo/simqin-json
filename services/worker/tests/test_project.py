"""Tests for the project module — model, service, search, build."""

from __future__ import annotations

import json
from pathlib import Path

from app.project import (
    Project,
    ProjectAsset,
    ProjectDocument,
    ProjectService,
    build_check,
    SCHEMA_VERSION,
    _now_iso,
)
from app.authoring import AuthoringDoc, Section, Paragraph


# ---------------------------------------------------------------------------
# Project creation
# ---------------------------------------------------------------------------

def test_create_project():
    p = Project(name="Test Project")
    assert p.name == "Test Project"
    assert p.id != ""
    assert p.created != ""
    assert p.modified != ""
    assert len(p.documents) == 0
    assert len(p.assets) == 0


def test_project_default_name():
    p = Project()
    assert p.name == "Untitled Project"


def test_project_touch_updates_modified():
    p = Project(name="T")
    old = p.modified
    p._touch()
    assert p.modified >= old


# ---------------------------------------------------------------------------
# Project serialization
# ---------------------------------------------------------------------------

def test_project_roundtrip():
    p = Project(name="Roundtrip")
    doc = AuthoringDoc(template="dita-topic", title="My Doc", id="doc1")
    p.add_document(doc, filename="my-doc.json")
    data = p.to_dict()
    p2 = Project.from_dict(data)
    assert p2.name == "Roundtrip"
    assert len(p2.documents) == 1
    assert p2.documents[0].title == "My Doc"
    assert p2.documents[0].doc is not None
    assert p2.documents[0].doc.title == "My Doc"


def test_project_serializes_to_json():
    p = Project(name="JSON Test")
    doc = AuthoringDoc(template="dita-topic", title="Doc", id="d1")
    p.add_document(doc)
    json_str = json.dumps(p.to_dict())
    assert '"name": "JSON Test"' in json_str
    assert '"title": "Doc"' in json_str


# ---------------------------------------------------------------------------
# Manifest
# ---------------------------------------------------------------------------

def test_manifest_contains_schema_version():
    p = Project(name="Manifest Test")
    m = p.manifest()
    assert m["schema_version"] == SCHEMA_VERSION
    assert m["name"] == "Manifest Test"
    assert "documents" in m
    assert "assets" in m


def test_manifest_lists_document_summaries():
    p = Project(name="M")
    doc = AuthoringDoc(template="dita-topic", title="Summary Title", id="s1")
    p.add_document(doc, filename="s1.json")
    m = p.manifest()
    docs = m["documents"]
    assert len(docs) == 1
    assert docs[0]["title"] == "Summary Title"
    assert docs[0]["filename"] == "s1.json"


# ---------------------------------------------------------------------------
# Document management
# ---------------------------------------------------------------------------

def test_add_document():
    p = Project(name="Docs")
    doc = AuthoringDoc(template="dita-topic", title="New Doc", id="nd")
    doc_id = p.add_document(doc)
    assert len(p.documents) == 1
    assert p.documents[0].id == doc_id


def test_remove_document():
    p = Project(name="R")
    doc1 = AuthoringDoc(template="dita-topic", title="D1", id="d1")
    doc2 = AuthoringDoc(template="dita-topic", title="D2", id="d2")
    id1 = p.add_document(doc1)
    id2 = p.add_document(doc2)
    assert len(p.documents) == 2
    p.remove_document(id1)
    assert len(p.documents) == 1
    assert p.documents[0].id == id2


def test_rename_document():
    p = Project(name="Rename")
    doc = AuthoringDoc(template="dita-topic", title="Old", id="old")
    did = p.add_document(doc)
    p.rename_document(did, "New Title")
    assert p.documents[0].title == "New Title"
    assert p.documents[0].doc.title == "New Title"


def test_remove_document_clears_root():
    p = Project(name="Root")
    doc = AuthoringDoc(template="dita-topic", title="R", id="r")
    did = p.add_document(doc)
    p.set_root_document(did)
    assert p.root_document_id == did
    p.remove_document(did)
    assert p.root_document_id is None


# ---------------------------------------------------------------------------
# Asset management
# ---------------------------------------------------------------------------

def test_add_asset():
    p = Project(name="Assets")
    asset = ProjectAsset(filename="image.png", mime="image/png", size=1024)
    p.add_asset(asset)
    assert len(p.assets) == 1
    assert p.assets[0].filename == "image.png"
    assert p.assets[0].id != ""


def test_remove_asset():
    p = Project(name="A")
    a1 = ProjectAsset(filename="a.png", mime="image/png")
    a2 = ProjectAsset(filename="b.png", mime="image/png")
    p.add_asset(a1)
    p.add_asset(a2)
    assert len(p.assets) == 2
    p.remove_asset(a1.id)
    assert len(p.assets) == 1
    assert p.assets[0].id == a2.id


def test_asset_refs():
    asset = ProjectAsset(filename="ref.png", mime="image/png", refs=["doc1", "doc2"])
    assert "doc1" in asset.refs


# ---------------------------------------------------------------------------
# Project service
# ---------------------------------------------------------------------------

def test_service_create():
    svc = ProjectService()
    p = svc.create_project("Service Test")
    assert p.name == "Service Test"
    assert svc.get_project(p.id) is p


def test_service_open_reuses():
    svc = ProjectService()
    p1 = svc.create_project("My Project")
    p2 = svc.open_project("My Project")
    # open_project creates a new project if name not found
    assert p2 is not None


def test_service_save_returns_manifest():
    svc = ProjectService()
    p = svc.create_project("Save Test")
    result = svc.save_project(p.id)
    assert result["ok"] is True
    assert "manifest" in result


# ---------------------------------------------------------------------------
# Search
# ---------------------------------------------------------------------------

def test_search_by_title():
    p = Project(name="Search")
    doc = AuthoringDoc(template="dita-topic", title="Important Document", id="id1")
    p.add_document(doc)
    results = p.search("Important")
    assert len(results) >= 1
    assert results[0]["title"] == "Important Document"


def test_search_by_paragraph():
    p = Project(name="Search")
    doc = AuthoringDoc(
        template="dita-topic", title="Doc", id="d1",
        sections=[Section(heading="Intro", id="s1", paragraphs=[Paragraph(text="Special keyword here", id="p1")])],
    )
    p.add_document(doc)
    results = p.search("Special keyword")
    assert len(results) >= 1
    assert any("Special keyword" in m for m in results[0]["matches"])


def test_search_returns_empty_for_no_match():
    p = Project(name="Search")
    doc = AuthoringDoc(template="dita-topic", title="Doc", id="d1")
    p.add_document(doc)
    results = p.search("nonexistent")
    assert len(results) == 0


# ---------------------------------------------------------------------------
# Build check
# ---------------------------------------------------------------------------

def test_build_check_empty():
    p = Project(name="Build")
    report = build_check(p)
    assert report["ok"] is True
    assert report["document_count"] == 0
    assert report["asset_count"] == 0


def test_build_check_counts():
    p = Project(name="Build")
    doc = AuthoringDoc(template="dita-topic", title="D", id="d")
    p.add_document(doc)
    p.add_asset(ProjectAsset(filename="a.png", mime="image/png"))
    report = build_check(p)
    assert report["document_count"] == 1
    assert report["asset_count"] == 1


# ---------------------------------------------------------------------------
# Schema validation
# ---------------------------------------------------------------------------

def test_project_schema_validation():
    """Produced project JSON should validate against project.schema.json."""
    from jsonschema import Draft202012Validator

    schema_path = Path(__file__).resolve().parent.parent.parent.parent / "shared" / "schemas" / "project.schema.json"
    with open(schema_path, "r") as fh:
        schema = json.load(fh)

    validator = Draft202012Validator(schema)
    p = Project(name="Schema Test")
    doc = AuthoringDoc(template="dita-topic", title="Test", id="t")
    p.add_document(doc)
    p.add_asset(ProjectAsset(filename="img.png", mime="image/png"))

    errors = list(validator.iter_errors(p.to_dict()))
    assert not errors, f"Project schema errors: {[e.message for e in errors]}"


def test_manifest_schema_validation():
    """Produced manifest should validate against project-manifest.schema.json."""
    from jsonschema import Draft202012Validator

    schema_path = Path(__file__).resolve().parent.parent.parent.parent / "shared" / "schemas" / "project-manifest.schema.json"
    with open(schema_path, "r") as fh:
        schema = json.load(fh)

    validator = Draft202012Validator(schema)
    p = Project(name="Manifest Schema")
    doc = AuthoringDoc(template="dita-topic", title="M", id="m")
    p.add_document(doc)

    errors = list(validator.iter_errors(p.manifest()))
    assert not errors, f"Manifest schema errors: {[e.message for e in errors]}"