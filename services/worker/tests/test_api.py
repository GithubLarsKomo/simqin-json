"""API-level tests for the SIMQIN JSON Worker service.

Tests that invalid mapping YAML returns HTTP 400 (not 500).
"""

from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.mapper import MappingProfile

HERE = Path(__file__).resolve().parent
FIXTURES = HERE.parent.parent.parent / "shared" / "test-fixtures"


def _load_fixture(name: str) -> bytes:
    with open(FIXTURES / name, "rb") as fh:
        return fh.read()


client = TestClient(app)


# ---------------------------------------------------------------------------
# Invalid YAML → HTTP 400
# ---------------------------------------------------------------------------


def test_invalid_yaml_syntax_returns_400():
    """Worker /api/v1/convert must return 400 for syntactically invalid YAML."""
    xml = _load_fixture("example-topic.xml")
    response = client.post(
        "/api/v1/convert",
        files={
            "file": ("test.xml", xml, "application/xml"),
            "mapping": ("bad.yaml", b"not: valid: yaml: [[[", "application/x-yaml"),
        },
    )
    assert response.status_code == 400
    detail = response.json().get("detail", "")
    assert "YAML" in detail or "Invalid" in detail


def test_empty_mapping_yaml_returns_400():
    """Worker must return 400 for empty (null) YAML mapping file (not whitespace-only)."""
    xml = _load_fixture("example-topic.xml")
    response = client.post(
        "/api/v1/convert",
        files={
            "file": ("test.xml", xml, "application/xml"),
            "mapping": ("empty.yaml", b"   ", "application/x-yaml"),
        },
    )
    assert response.status_code == 400
    detail = response.json().get("detail", "")
    assert "Empty" in detail or "YAML" in detail


def test_scalar_yaml_returns_400():
    """Worker must return 400 when YAML is a scalar, not a mapping."""
    xml = _load_fixture("example-topic.xml")
    response = client.post(
        "/api/v1/convert",
        files={
            "file": ("test.xml", xml, "application/xml"),
            "mapping": ("scalar.yaml", b"just a string", "application/x-yaml"),
        },
    )
    assert response.status_code == 400


def test_mapping_text_invalid_yaml_returns_400():
    """Worker must return 400 for invalid YAML in mapping_text field."""
    xml = _load_fixture("example-topic.xml")
    response = client.post(
        "/api/v1/convert",
        files={"file": ("test.xml", xml, "application/xml")},
        data={"mapping_text": "not: valid: yaml: [[["},
    )
    assert response.status_code == 400
    detail = response.json().get("detail", "")
    assert "YAML" in detail or "Invalid" in detail


# ---------------------------------------------------------------------------
# Valid mapping → HTTP 200
# ---------------------------------------------------------------------------


def test_valid_yaml_returns_200():
    """Worker must return 200 for structurally valid YAML."""
    xml = _load_fixture("example-topic.xml")
    valid_yaml = b"""
profile: test
version: 1.0.0
rules:
  - match: "/topic/title"
    target: "my_title"
    type: "text"
"""
    response = client.post(
        "/api/v1/convert",
        files={
            "file": ("test.xml", xml, "application/xml"),
            "mapping": ("good.yaml", valid_yaml, "application/x-yaml"),
        },
    )
    assert response.status_code == 200
    data = response.json()
    assert data["ok"] is True
    assert data["domain_json"]["my_title"] == "Example SIMQIN Topic"