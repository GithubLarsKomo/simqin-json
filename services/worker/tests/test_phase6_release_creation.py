from __future__ import annotations

import json
import sqlite3
from pathlib import Path

from fastapi.testclient import TestClient
from jsonschema import Draft202012Validator

from app.phase6_main import app


client = TestClient(app)
_APPROVER = {"X-SIMQIN-User": "approver-a", "X-SIMQIN-Role": "approver"}
_REVIEWER = {"X-SIMQIN-User": "reviewer-b", "X-SIMQIN-Role": "reviewer"}


def _payload(release_id: str = "rel-1", version: int = 1) -> dict:
    return {
        "release_id": release_id,
        "product_id": "prod-1",
        "language": "de-DE",
        "version": version,
        "root_object_ids": ["root"],
        "pinned_revisions": {"root": 1},
        "slot_values": {"name": "Alice"},
        "objects": [
            {
                "id": "root",
                "type": "paragraph",
                "section_type": "procedure",
                "canonical_language": "de-DE",
                "status": "approved",
                "current_revision": 1,
                "revisions": [
                    {
                        "object_id": "root",
                        "revision": 1,
                        "canonical_content": "Hello {{name}}",
                        "sentence_segments": [
                            {
                                "segment_id": "seg-1",
                                "segment_type": "sentence",
                                "source_text": "Hello {{name}}",
                                "source_revision": 1,
                                "order": 0,
                                "immutable_boundary": True,
                            }
                        ],
                        "slots": [
                            {
                                "slot_id": "name",
                                "type": "term",
                                "required": True,
                                "default_value": "World",
                            }
                        ],
                        "composed_objects": [],
                        "approval_status": "approved",
                    }
                ],
            }
        ],
    }


def _release_schema() -> dict:
    path = Path(__file__).parents[1] / "schemas" / "phase6" / "ifu-language-release.schema.json"
    return json.loads(path.read_text(encoding="utf-8"))


def test_release_creation_requires_approver(tmp_path, monkeypatch):
    monkeypatch.setenv("STORAGE_DIR", str(tmp_path))
    response = client.post("/api/v1/ifu/releases", headers=_REVIEWER, json=_payload())
    assert response.status_code == 403


def test_release_creation_is_pinned_immutable_and_persistent(tmp_path, monkeypatch):
    monkeypatch.setenv("STORAGE_DIR", str(tmp_path))
    created = client.post("/api/v1/ifu/releases", headers=_APPROVER, json=_payload())
    assert created.status_code == 201
    body = created.json()
    assert body["created_by"] == "approver-a"
    assert body["provenance"]["resolution_mode"] == "pinned"
    assert body["resolved_blocks"][0]["rendered_content"] == "Hello Alice"
    assert body["release_checksum"]
    Draft202012Validator(_release_schema()).validate(body)

    fetched = client.get("/api/v1/ifu/releases/rel-1")
    assert fetched.status_code == 200
    assert fetched.json()["release_checksum"] == body["release_checksum"]

    listed = client.get("/api/v1/ifu/releases")
    assert listed.status_code == 200
    assert listed.json()["count"] == 1

    duplicate = client.post("/api/v1/ifu/releases", headers=_APPROVER, json=_payload())
    assert duplicate.status_code == 400
    assert "already exists" in str(duplicate.json()["detail"])


def test_release_creation_rejects_unresolved_required_slot(tmp_path, monkeypatch):
    monkeypatch.setenv("STORAGE_DIR", str(tmp_path))
    payload = _payload("rel-invalid")
    payload["slot_values"] = {}
    payload["objects"][0]["revisions"][0]["slots"][0].pop("default_value", None)
    response = client.post("/api/v1/ifu/releases", headers=_APPROVER, json=payload)
    assert response.status_code == 400
    detail = response.json()["detail"]
    assert "findings" in detail


def test_release_read_detects_stored_payload_tampering(tmp_path, monkeypatch):
    monkeypatch.setenv("STORAGE_DIR", str(tmp_path))
    created = client.post("/api/v1/ifu/releases", headers=_APPROVER, json=_payload())
    assert created.status_code == 201

    database = tmp_path / "phase6-releases.sqlite3"
    with sqlite3.connect(database) as connection:
        row = connection.execute(
            "SELECT payload_json FROM ifu_language_releases WHERE release_id = ?",
            ("rel-1",),
        ).fetchone()
        payload = json.loads(row[0])
        payload["resolved_blocks"][0]["rendered_content"] = "Tampered"
        connection.execute(
            "UPDATE ifu_language_releases SET payload_json = ? WHERE release_id = ?",
            (json.dumps(payload, sort_keys=True), "rel-1"),
        )

    fetched = client.get("/api/v1/ifu/releases/rel-1")
    assert fetched.status_code == 500
    detail = fetched.json()["detail"]
    assert detail["message"] == "Stored release integrity check failed"
    assert "failed checksum verification" in detail["reason"]

    listed = client.get("/api/v1/ifu/releases")
    assert listed.status_code == 500
    assert listed.json()["detail"]["message"] == "Stored release integrity check failed"
