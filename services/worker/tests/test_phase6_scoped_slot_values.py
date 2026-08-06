from __future__ import annotations

from fastapi.testclient import TestClient

from app.phase6_main import app


client = TestClient(app)


def _object(object_id: str, label: str) -> dict:
    content = f"{label}: {{{{name}}}}"
    return {
        "id": object_id,
        "type": "paragraph",
        "section_type": "procedure",
        "canonical_language": "de-DE",
        "status": "approved",
        "current_revision": 1,
        "revisions": [
            {
                "object_id": object_id,
                "revision": 1,
                "canonical_content": content,
                "sentence_segments": [
                    {
                        "segment_id": f"{object_id}-seg-1",
                        "segment_type": "sentence",
                        "source_text": content,
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
                    }
                ],
                "composed_objects": [],
                "approval_status": "approved",
            }
        ],
    }


def test_scoped_slot_values_allow_same_slot_id_on_multiple_objects():
    objects = [_object("root-a", "A"), _object("root-b", "B")]
    slot_values = {
        "root-a@1:name": "Alice",
        "root-b@1:name": "Bob",
        "name": "legacy-fallback",
    }

    validation = client.post(
        "/api/v1/content/validate",
        json={
            "objects": objects,
            "pinned_revisions": {"root-a": 1, "root-b": 1},
            "slot_values": slot_values,
        },
    )
    assert validation.status_code == 200
    assert validation.json()["valid"] is True

    resolution = client.post(
        "/api/v1/content/resolve",
        json={
            "objects": objects,
            "root_object_ids": ["root-a", "root-b"],
            "pinned_revisions": {"root-a": 1, "root-b": 1},
            "revision_mode": "pinned",
            "slot_values": slot_values,
        },
    )
    assert resolution.status_code == 200
    body = resolution.json()
    rendered = {block["source_object_id"]: block["rendered_content"] for block in body["blocks"]}
    assert rendered == {"root-a": "A: Alice", "root-b": "B: Bob"}
    assert body["provenance"]["slot_values"]["root-a@1:name"] == "Alice"
    assert body["provenance"]["slot_values"]["root-b@1:name"] == "Bob"


def test_object_scoped_value_precedes_global_fallback():
    obj = _object("root-a", "A")
    response = client.post(
        "/api/v1/content/resolve",
        json={
            "objects": [obj],
            "root_object_ids": ["root-a"],
            "pinned_revisions": {"root-a": 1},
            "revision_mode": "pinned",
            "slot_values": {"name": "Global", "root-a:name": "Object"},
        },
    )
    assert response.status_code == 200
    assert response.json()["blocks"][0]["rendered_content"] == "A: Object"


def test_missing_required_slot_uses_same_finding_code_in_validation_and_resolution():
    obj = _object("root-a", "A")

    validation = client.post(
        "/api/v1/content/validate",
        json={"objects": [obj], "pinned_revisions": {"root-a": 1}},
    )
    assert validation.status_code == 200
    validation_codes = {item["code"] for item in validation.json()["issues"]}
    assert "unresolved-required-slot" in validation_codes
    assert "unresolved-slot" not in validation_codes

    resolution = client.post(
        "/api/v1/content/resolve",
        json={
            "objects": [obj],
            "root_object_ids": ["root-a"],
            "pinned_revisions": {"root-a": 1},
            "revision_mode": "pinned",
        },
    )
    assert resolution.status_code == 200
    resolution_codes = {item["code"] for item in resolution.json()["findings"]}
    assert "unresolved-required-slot" in resolution_codes
