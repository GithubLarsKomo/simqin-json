from __future__ import annotations

import json
import sqlite3
from pathlib import Path

from fastapi.testclient import TestClient
from jsonschema import Draft202012Validator

from app.canonical_content_store import CanonicalContentStore
from app.content_objects import ContentObjectRevision
from app.phase6_main import app
from app.translation_store import TranslationVariantStore
from app.translations import TranslationVariant


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
                        "canonical_content": "Hallo {{name}}.",
                        "sentence_segments": [
                            {
                                "segment_id": "seg-1",
                                "segment_type": "sentence",
                                "source_text": "Hallo {{name}}.",
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


def _translated_payload(release_id: str = "rel-en") -> dict:
    payload = _payload(release_id)
    payload["language"] = "en-US"
    payload["translation_selections"] = [
        {"content_object_id": "root", "variant_id": "tr-root-en", "revision": 3}
    ]
    return payload


def _persist_translation(
    storage_dir: Path,
    *,
    status: str = "approved",
    canonical_revision: int = 1,
) -> None:
    source_payload = _payload()["objects"][0]["revisions"][0].copy()
    source_payload["revision"] = canonical_revision
    source_payload["sentence_segments"] = [dict(item) for item in source_payload["sentence_segments"]]
    source_payload["sentence_segments"][0]["source_revision"] = canonical_revision
    source_revision = ContentObjectRevision.from_dict(source_payload)
    canonical = CanonicalContentStore(storage_dir / "phase6-canonical-content.sqlite3").add(
        object_id="root",
        canonical_language="de-DE",
        revision=source_revision,
        registered_by="approver-source",
    )

    store = TranslationVariantStore(storage_dir / "phase6-translations.sqlite3")
    variant = TranslationVariant.from_dict(
        {
            "id": "tr-root-en",
            "content_object_id": "root",
            "canonical_revision": canonical_revision,
            "target_language": "en-US",
            "revision": 3,
            "status": "generated",
            "provider_metadata": {"canonical_source_checksum": canonical["payload_checksum"]},
            "segment_translations": [
                {
                    "segment_id": "seg-1",
                    "source_text": "Hallo {{name}}.",
                    "translated_text": "Hello {{name}}.",
                    "order": 0,
                }
            ],
        }
    )
    store.add_variant(variant, created_by="translator-a")
    if status in {"reviewed", "approved"}:
        store.transition("tr-root-en", 3, status="reviewed", changed_by="reviewer-b")
    if status == "approved":
        store.transition("tr-root-en", 3, status="approved", changed_by="approver-a")
    elif status == "rejected":
        store.transition("tr-root-en", 3, status="rejected", changed_by="reviewer-b", comment="Rejected")


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
    assert body["resolved_blocks"][0]["rendered_content"] == "Hallo Alice."
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


def test_translated_release_materializes_persisted_approved_exact_revision(tmp_path, monkeypatch):
    monkeypatch.setenv("STORAGE_DIR", str(tmp_path))
    _persist_translation(tmp_path)
    response = client.post(
        "/api/v1/ifu/releases",
        headers=_APPROVER,
        json=_translated_payload(),
    )
    assert response.status_code == 201
    body = response.json()
    assert body["language"] == "en-US"
    assert body["resolved_blocks"][0]["rendered_content"] == "Hello Alice."
    assert body["translation_bindings"] == [
        {
            "content_object_id": "root",
            "target_language": "en-US",
            "variant_id": "tr-root-en",
            "revision": 3,
            "canonical_revision": 1,
        }
    ]
    Draft202012Validator(_release_schema()).validate(body)


def test_translated_release_rejects_same_revision_with_changed_source_content(tmp_path, monkeypatch):
    monkeypatch.setenv("STORAGE_DIR", str(tmp_path))
    _persist_translation(tmp_path)
    payload = _translated_payload("rel-source-tampered")
    payload["objects"][0]["revisions"][0]["canonical_content"] = "Manipuliert {{name}}."
    payload["objects"][0]["revisions"][0]["sentence_segments"][0]["source_text"] = "Manipuliert {{name}}."
    response = client.post("/api/v1/ifu/releases", headers=_APPROVER, json=payload)
    assert response.status_code == 400
    findings = response.json()["detail"]["findings"]
    assert "translation-release-source-mismatch" in {item["code"] for item in findings}


def test_translated_release_ignores_untrusted_variant_payload(tmp_path, monkeypatch):
    monkeypatch.setenv("STORAGE_DIR", str(tmp_path))
    payload = _translated_payload("rel-untrusted")
    payload["translation_variants"] = [
        {
            "id": "tr-root-en",
            "content_object_id": "root",
            "canonical_revision": 1,
            "target_language": "en-US",
            "revision": 3,
            "status": "approved",
            "segment_translations": [
                {"segment_id": "seg-1", "translated_text": "Untrusted {{name}}.", "order": 0}
            ],
        }
    ]
    response = client.post("/api/v1/ifu/releases", headers=_APPROVER, json=payload)
    assert response.status_code == 400
    findings = response.json()["detail"]["findings"]
    assert "translation-variant-not-found" in {item["code"] for item in findings}


def test_translated_release_requires_persisted_approved_variant(tmp_path, monkeypatch):
    monkeypatch.setenv("STORAGE_DIR", str(tmp_path))
    _persist_translation(tmp_path, status="reviewed")
    response = client.post(
        "/api/v1/ifu/releases",
        headers=_APPROVER,
        json=_translated_payload("rel-draft"),
    )
    assert response.status_code == 400
    findings = response.json()["detail"]["findings"]
    assert "translation-not-approved" in {item["code"] for item in findings}


def test_translated_release_requires_exact_persisted_canonical_revision(tmp_path, monkeypatch):
    monkeypatch.setenv("STORAGE_DIR", str(tmp_path))
    _persist_translation(tmp_path, canonical_revision=2)
    response = client.post(
        "/api/v1/ifu/releases",
        headers=_APPROVER,
        json=_translated_payload("rel-wrong-rev"),
    )
    assert response.status_code == 400
    findings = response.json()["detail"]["findings"]
    assert "translation-canonical-revision-mismatch" in {item["code"] for item in findings}
