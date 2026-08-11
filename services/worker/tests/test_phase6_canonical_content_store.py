from __future__ import annotations

import json
import sqlite3

from fastapi.testclient import TestClient

from app.phase6_main import app


client = TestClient(app)
_APPROVER = {"X-SIMQIN-User": "approver-source", "X-SIMQIN-Role": "approver"}
_REVIEWER = {"X-SIMQIN-User": "reviewer-b", "X-SIMQIN-Role": "reviewer"}


def _snapshot_payload() -> dict:
    return {
        "object_id": "root",
        "canonical_language": "de-DE",
        "revision": {
            "object_id": "root",
            "revision": 1,
            "canonical_content": "Hallo {{name}}.",
            "sentence_segments": [
                {
                    "segment_id": "seg-1",
                    "segment_type": "sentence",
                    "source_text": "Hallo {{name}}.",
                    "source_revision": 1,
                    "order": 0,
                }
            ],
            "slots": [
                {"slot_id": "name", "type": "term", "required": True}
            ],
            "approval_status": "approved",
        },
    }


def test_canonical_snapshot_requires_approver_and_is_immutable(tmp_path, monkeypatch):
    monkeypatch.setenv("STORAGE_DIR", str(tmp_path))
    forbidden = client.post("/api/v1/content/canonical-snapshots", headers=_REVIEWER, json=_snapshot_payload())
    assert forbidden.status_code == 403

    created = client.post("/api/v1/content/canonical-snapshots", headers=_APPROVER, json=_snapshot_payload())
    assert created.status_code == 201
    assert created.json()["object_id"] == "root"
    assert created.json()["payload_checksum"]
    assert created.json()["registered_by"] == "approver-source"

    duplicate = client.post("/api/v1/content/canonical-snapshots", headers=_APPROVER, json=_snapshot_payload())
    assert duplicate.status_code == 400
    assert "already exists" in str(duplicate.json()["detail"])


def test_canonical_snapshot_rejects_unapproved_revision(tmp_path, monkeypatch):
    monkeypatch.setenv("STORAGE_DIR", str(tmp_path))
    payload = _snapshot_payload()
    payload["revision"]["approval_status"] = "draft"
    response = client.post("/api/v1/content/canonical-snapshots", headers=_APPROVER, json=payload)
    assert response.status_code == 400
    assert "Only approved" in str(response.json()["detail"])


def test_canonical_snapshot_read_detects_payload_tampering(tmp_path, monkeypatch):
    monkeypatch.setenv("STORAGE_DIR", str(tmp_path))
    created = client.post("/api/v1/content/canonical-snapshots", headers=_APPROVER, json=_snapshot_payload())
    assert created.status_code == 201

    database = tmp_path / "phase6-canonical-content.sqlite3"
    with sqlite3.connect(database) as connection:
        row = connection.execute(
            "SELECT payload_json FROM canonical_content_revisions WHERE object_id = ? AND revision = ?",
            ("root", 1),
        ).fetchone()
        payload = json.loads(row[0])
        payload["canonical_content"] = "Manipulated"
        connection.execute(
            "UPDATE canonical_content_revisions SET payload_json = ? WHERE object_id = ? AND revision = ?",
            (json.dumps(payload, sort_keys=True), "root", 1),
        )

    fetched = client.get("/api/v1/content/canonical-snapshots/root/1")
    assert fetched.status_code == 500
    assert fetched.json()["detail"]["message"] == "Canonical source integrity check failed"


def test_canonical_snapshot_list_and_get(tmp_path, monkeypatch):
    monkeypatch.setenv("STORAGE_DIR", str(tmp_path))
    client.post("/api/v1/content/canonical-snapshots", headers=_APPROVER, json=_snapshot_payload())
    listed = client.get("/api/v1/content/canonical-snapshots")
    assert listed.status_code == 200
    assert listed.json()["count"] == 1
    fetched = client.get("/api/v1/content/canonical-snapshots/root/1")
    assert fetched.status_code == 200
    assert fetched.json()["revision_payload"]["canonical_content"] == "Hallo {{name}}."
