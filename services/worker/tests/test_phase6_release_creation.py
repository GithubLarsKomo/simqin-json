from __future__ import annotations

from fastapi.testclient import TestClient

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
