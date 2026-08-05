"""API tests for the Phase 6 worker router."""

from fastapi.testclient import TestClient

from app.ifu_release import IFULanguageReleaseSnapshot, ResolvedBlockSnapshot
from app.phase6_main import app


client = TestClient(app)
_APPROVER_HEADERS = {
    "X-SIMQIN-User": "approver-a",
    "X-SIMQIN-Role": "approver",
}
_REVIEWER_HEADERS = {
    "X-SIMQIN-User": "reviewer-a",
    "X-SIMQIN-Role": "reviewer",
}


def _object(object_id: str = "root", content: str = "Hello {{name}}") -> dict:
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
                        "segment_id": "seg-1",
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
                        "default_value": "World",
                    }
                ],
                "composed_objects": [],
                "approval_status": "approved",
            }
        ],
    }


def test_phase6_schema_endpoints_list_and_fetch():
    listing = client.get("/api/v1/content/schemas")
    assert listing.status_code == 200
    assert "content-segment" in listing.json()["schemas"]

    schema = client.get("/api/v1/content/schemas/content-segment")
    assert schema.status_code == 200
    assert schema.json()["$schema"].startswith("https://json-schema.org/")

    missing = client.get("/api/v1/content/schemas/does-not-exist")
    assert missing.status_code == 404


def test_content_validate_and_resolve_endpoints():
    obj = _object()
    validation = client.post(
        "/api/v1/content/validate",
        json={"objects": [obj], "slot_values": {"name": "Alice"}},
    )
    assert validation.status_code == 200
    assert validation.json()["valid"] is True

    resolution = client.post(
        "/api/v1/content/resolve",
        json={
            "objects": [obj],
            "root_object_ids": ["root"],
            "pinned_revisions": {"root": 1},
            "slot_values": {"name": "Alice"},
            "revision_mode": "pinned",
        },
    )
    assert resolution.status_code == 200
    body = resolution.json()
    assert body["errors"] == []
    assert body["blocks"][0]["rendered_content"] == "Hello Alice"
    assert body["checksum"]


def test_content_graph_reports_mixed_cycle():
    a = _object("a", "A")
    b = _object("b", "B")
    a["base_template_id"] = "b"
    a["binding"] = {"base_template_id": "b", "mode": "derived"}
    b["revisions"][0]["composed_objects"] = [
        {
            "composition_id": "b-a",
            "child_object_id": "a",
            "pinned_revision": 1,
            "placement": "last",
            "order": 0,
        }
    ]
    response = client.post(
        "/api/v1/content/graph",
        json={"objects": [a, b], "pinned_revisions": {"a": 1, "b": 1}},
    )
    assert response.status_code == 200
    assert response.json()["cycles"][0]["type"] == "mixed-content-cycle"


def test_translation_validate_reports_placeholder_loss():
    response = client.post(
        "/api/v1/translations/validate",
        json={
            "source_segments": [
                {
                    "segment_id": "seg-1",
                    "segment_type": "sentence",
                    "source_text": "Use {{sample}}.",
                    "source_revision": 1,
                    "order": 0,
                    "immutable_boundary": True,
                }
            ],
            "variant": {
                "id": "tr-1",
                "content_object_id": "root",
                "canonical_revision": 1,
                "target_language": "en-US",
                "revision": 1,
                "status": "approved",
                "segment_translations": [
                    {
                        "segment_id": "seg-1",
                        "source_text": "Use {{sample}}.",
                        "translated_text": "Use the specimen.",
                        "order": 0,
                    }
                ],
            },
        },
    )
    assert response.status_code == 200
    assert response.json()["valid"] is False
    assert "translation-placeholder-mismatch" in {
        item["code"] for item in response.json()["findings"]
    }


def test_release_verify_requires_approver_role():
    response = client.post(
        "/api/v1/ifu/releases/verify",
        headers=_REVIEWER_HEADERS,
        json={"release": {}},
    )
    assert response.status_code == 403
    assert "not permitted" in response.json()["detail"]


def test_release_verify_endpoint_detects_tampering():
    release = IFULanguageReleaseSnapshot(
        release_id="rel-1",
        product_id="prod-1",
        language="de-DE",
        version=1,
        resolved_blocks=(ResolvedBlockSnapshot("block-1", "root", 1, "Stable"),),
        created_at="2026-08-01T00:00:00+00:00",
        created_by="tester",
    )
    valid = client.post(
        "/api/v1/ifu/releases/verify",
        headers=_APPROVER_HEADERS,
        json={"release": release.to_dict()},
    )
    assert valid.status_code == 200
    assert valid.json()["valid"] is True

    tampered = release.to_dict()
    tampered["resolved_blocks"][0]["rendered_content"] = "Changed"
    invalid = client.post(
        "/api/v1/ifu/releases/verify",
        headers=_APPROVER_HEADERS,
        json={"release": tampered},
    )
    assert invalid.status_code == 200
    assert invalid.json()["valid"] is False
