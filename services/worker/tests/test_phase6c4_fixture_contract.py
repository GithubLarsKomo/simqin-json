"""Contract tests for the Phase 6c.4 ELISA fixture and API foundation."""

from __future__ import annotations

import json
from pathlib import Path

from fastapi.testclient import TestClient

from app.phase6_main import app


FIXTURE = Path(__file__).parent / "fixtures" / "phase6_elisa_family.json"
client = TestClient(app)


def _fixture() -> dict:
    return json.loads(FIXTURE.read_text(encoding="utf-8"))


def test_elisa_fixture_covers_required_family_scenarios():
    data = _fixture()
    assert len(data["products"]) == 10
    assert sum(item["canonical_language"] == "en-US" for item in data["products"]) == 1
    assert {item["sample_type"] for item in data["products"]} >= {"Serum", "Serum/Plasma"}
    assert len({item["incubation_minutes"] for item in data["products"]}) >= 2
    assert len({item["unit"] for item in data["products"]}) >= 4
    assert len(data["translation_variants"]) == 2
    assert {item["applicability"]["markets"][0] for item in data["translation_variants"]} == {"EU", "US"}
    assert data["translation_selection"]["translation_variant_id"] == "warning-en-eu"
    assert {item["status"] for item in data["structure_migrations"]} == {
        "pending_approval", "rejected", "changes_requested"
    }
    assert data["released_snapshot"]["immutable"] is True
    assert data["aliases"]["older-warning-id"] == "old-warning-id"
    assert "mixed_cycle" in data["invalid_graphs"]


def test_fixture_content_validates_and_resolves_through_phase6_api():
    data = _fixture()
    objects = data["content_objects"]
    values = {
        "analyte": data["products"][0]["analyte"],
        "sample_type": data["products"][0]["sample_type"],
        "incubation_minutes": data["products"][0]["incubation_minutes"],
    }

    validation = client.post(
        "/api/v1/content/validate",
        json={"objects": objects, "slot_values": values},
    )
    assert validation.status_code == 200
    validation_data = validation.json()
    assert validation_data["valid"] is True
    assert validation_data["error_count"] == 0

    resolution = client.post(
        "/api/v1/content/resolve",
        json={
            "root_object_ids": ["tpl-intended-purpose", "tpl-procedure", "conditional-sample-note"],
            "objects": objects,
            "slot_values": values,
            "aliases": data["aliases"],
            "revision_mode": "working",
            "multiplicity_rules": data["multiplicity_rules"],
        },
    )
    assert resolution.status_code == 200
    resolved = resolution.json()
    assert resolved["errors"] == []
    rendered = [block["rendered_content"] for block in resolved["blocks"]]
    assert any("ANA" in text and "Serum" in text for text in rendered)
    assert any("30" in text for text in rendered)
    assert resolved["checksum"]
    assert resolved["provenance"]["object_revisions_read"]


def test_schema_catalog_exposes_phase6_snapshot_contracts():
    response = client.get("/api/v1/content/schemas")
    assert response.status_code == 200
    names = set(response.json()["schemas"])
    assert {"content-segment", "resolved-content-tree", "ifu-language-release"}.issubset(names)
