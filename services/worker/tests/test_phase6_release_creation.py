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
_AUTHOR = {"X-SIMQIN-User": "author-a", "X-SIMQIN-Role": "author"}
_APPROVER = {"X-SIMQIN-User": "approver-a", "X-SIMQIN-Role": "approver"}
_REVIEWER = {"X-SIMQIN-User": "reviewer-b", "X-SIMQIN-Role": "reviewer"}


def _candidate_payload(
    candidate_id: str = "cand-1",
    release_id: str = "rel-1",
    version: int = 1,
) -> dict:
    return {
        "candidate_id": candidate_id,
        "release_id": release_id,
        "version": version,
        "product_id": "prod-1",
        "language": "de-DE",
        "root_object_ids": ["root"],
        "revision_mode": "pinned",
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


def _translated_candidate(candidate_id: str = "cand-en", release_id: str = "rel-en") -> dict:
    payload = _candidate_payload(candidate_id, release_id)
    payload["language"] = "en-US"
    payload["translation_selections"] = [
        {"content_object_id": "root", "variant_id": "tr-root-en", "revision": 3}
    ]
    return payload


def _persist_candidate_sources(payload: dict) -> None:
    """Register the exact pinned revisions used by a candidate test fixture."""
    store = CanonicalContentStore()
    pins = payload.get("pinned_revisions", {})
    for object_row in payload.get("objects", []):
        object_id = object_row.get("id", "")
        pinned_revision = pins.get(object_id)
        if not isinstance(pinned_revision, int):
            continue
        revision_row = next(
            (row for row in object_row.get("revisions", []) if row.get("revision") == pinned_revision),
            None,
        )
        if revision_row is None or store.get(object_id, pinned_revision) is not None:
            continue
        store.add(
            object_id=object_id,
            canonical_language=object_row.get("canonical_language", "de-DE"),
            revision=ContentObjectRevision.from_dict(revision_row),
            registered_by="approver-source",
        )


def _persist_translation(
    storage_dir: Path,
    *,
    status: str = "approved",
    canonical_revision: int = 1,
) -> None:
    source_payload = dict(_candidate_payload()["objects"][0]["revisions"][0])
    source_payload["revision"] = canonical_revision
    source_payload["sentence_segments"] = [
        {**segment, "source_revision": canonical_revision}
        for segment in source_payload["sentence_segments"]
    ]
    source = ContentObjectRevision.from_dict(source_payload)
    canonical_store = CanonicalContentStore(storage_dir / "phase6-canonical-content.sqlite3")
    trusted = canonical_store.get("root", canonical_revision)
    if trusted is None:
        trusted = canonical_store.add(
            object_id="root",
            canonical_language="de-DE",
            revision=source,
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
            "segment_translations": [
                {
                    "segment_id": "seg-1",
                    "source_text": "Hallo {{name}}.",
                    "translated_text": "Hello {{name}}.",
                    "order": 0,
                }
            ],
            "provider_metadata": {"canonical_source_checksum": trusted["payload_checksum"]},
        }
    )
    store.add_variant(variant, created_by="translator-a")
    if status in {"reviewed", "approved"}:
        store.transition("tr-root-en", 3, status="reviewed", changed_by="reviewer-b")
    if status == "approved":
        store.transition("tr-root-en", 3, status="approved", changed_by="approver-a")


def _create_candidate(
    payload: dict,
    headers: dict[str, str] = _AUTHOR,
    *,
    register_sources: bool = True,
):
    if register_sources:
        _persist_candidate_sources(payload)
    return client.post("/api/v1/ifu/release-candidates", headers=headers, json=payload)


def _approve(candidate_id: str, headers: dict[str, str] = _APPROVER):
    return client.post(
        f"/api/v1/ifu/release-candidates/{candidate_id}/decision",
        headers=headers,
        json={"decision": "approved"},
    )


def _publish(candidate_id: str, headers: dict[str, str] = _APPROVER):
    return client.post("/api/v1/ifu/releases", headers=headers, json={"candidate_id": candidate_id})


def _release_schema() -> dict:
    path = Path(__file__).parents[1] / "schemas" / "phase6" / "ifu-language-release.schema.json"
    return json.loads(path.read_text(encoding="utf-8"))


def test_candidate_requires_registered_trusted_source(tmp_path, monkeypatch):
    monkeypatch.setenv("STORAGE_DIR", str(tmp_path))
    response = _create_candidate(_candidate_payload(), register_sources=False)
    assert response.status_code == 400
    findings = response.json()["detail"]["findings"]
    assert "canonical-source-not-registered" in {item["code"] for item in findings}


def test_candidate_rejects_content_that_differs_from_trusted_source(tmp_path, monkeypatch):
    monkeypatch.setenv("STORAGE_DIR", str(tmp_path))
    trusted_payload = _candidate_payload()
    _persist_candidate_sources(trusted_payload)
    candidate_payload = _candidate_payload("cand-mismatch", "rel-mismatch")
    candidate_payload["objects"][0]["revisions"][0]["canonical_content"] = "Manipuliert {{name}}."
    candidate_payload["objects"][0]["revisions"][0]["sentence_segments"][0]["source_text"] = "Manipuliert {{name}}."
    response = _create_candidate(candidate_payload, register_sources=False)
    assert response.status_code == 400
    findings = response.json()["detail"]["findings"]
    assert "canonical-source-mismatch" in {item["code"] for item in findings}


def test_release_requires_approved_candidate_and_approver(tmp_path, monkeypatch):
    monkeypatch.setenv("STORAGE_DIR", str(tmp_path))
    created = _create_candidate(_candidate_payload())
    assert created.status_code == 201

    before_approval = _publish("cand-1")
    assert before_approval.status_code == 400
    assert "must be approved" in str(before_approval.json()["detail"])

    assert _approve("cand-1").status_code == 200
    reviewer_publish = _publish("cand-1", _REVIEWER)
    assert reviewer_publish.status_code == 403


def test_candidate_creator_cannot_approve_own_candidate(tmp_path, monkeypatch):
    monkeypatch.setenv("STORAGE_DIR", str(tmp_path))
    created = _create_candidate(_candidate_payload(), _APPROVER)
    assert created.status_code == 201
    self_approval = _approve("cand-1", _APPROVER)
    assert self_approval.status_code == 400
    assert "creator cannot approve" in str(self_approval.json()["detail"])


def test_release_from_candidate_is_pinned_immutable_and_persistent(tmp_path, monkeypatch):
    monkeypatch.setenv("STORAGE_DIR", str(tmp_path))
    candidate = _create_candidate(_candidate_payload())
    assert candidate.status_code == 201
    candidate_body = candidate.json()
    assert candidate_body["payload_checksum"]
    assert candidate_body["release_id"] == "rel-1"
    assert candidate_body["version"] == 1
    assert _approve("cand-1").status_code == 200

    created = _publish("cand-1")
    assert created.status_code == 201
    body = created.json()
    assert body["release_id"] == "rel-1"
    assert body["version"] == 1
    assert body["created_by"] == "approver-a"
    assert body["provenance"]["resolution_mode"] == "pinned"
    assert body["provenance"]["release_candidate_id"] == "cand-1"
    assert body["provenance"]["release_candidate_checksum"] == candidate_body["payload_checksum"]
    assert body["resolved_blocks"][0]["rendered_content"] == "Hallo Alice."
    assert body["release_checksum"]
    Draft202012Validator(_release_schema()).validate(body)

    fetched = client.get("/api/v1/ifu/releases/rel-1")
    assert fetched.status_code == 200
    assert fetched.json()["release_checksum"] == body["release_checksum"]

    candidate_after = client.get("/api/v1/ifu/release-candidates/cand-1")
    assert candidate_after.status_code == 200
    assert candidate_after.json()["status"] == "released"


def test_candidate_rejects_unresolved_required_slot(tmp_path, monkeypatch):
    monkeypatch.setenv("STORAGE_DIR", str(tmp_path))
    payload = _candidate_payload("cand-invalid", "rel-invalid")
    payload["slot_values"] = {}
    payload["objects"][0]["revisions"][0]["slots"][0].pop("default_value", None)
    response = _create_candidate(payload)
    assert response.status_code == 400
    assert "findings" in response.json()["detail"]


def test_candidate_read_detects_stored_payload_tampering(tmp_path, monkeypatch):
    monkeypatch.setenv("STORAGE_DIR", str(tmp_path))
    assert _create_candidate(_candidate_payload()).status_code == 201
    database = tmp_path / "phase6-release-candidates.sqlite3"
    with sqlite3.connect(database) as connection:
        row = connection.execute(
            "SELECT payload_json FROM release_candidates WHERE candidate_id = ?", ("cand-1",)
        ).fetchone()
        payload = json.loads(row[0])
        payload["slot_values"]["name"] = "Mallory"
        connection.execute(
            "UPDATE release_candidates SET payload_json = ? WHERE candidate_id = ?",
            (json.dumps(payload, sort_keys=True), "cand-1"),
        )
    fetched = client.get("/api/v1/ifu/release-candidates/cand-1")
    assert fetched.status_code == 500
    assert fetched.json()["detail"]["message"] == "Stored release candidate integrity check failed"


def test_translated_release_materializes_trusted_approved_translation(tmp_path, monkeypatch):
    monkeypatch.setenv("STORAGE_DIR", str(tmp_path))
    _persist_translation(tmp_path)
    candidate = _create_candidate(_translated_candidate())
    assert candidate.status_code == 201
    assert _approve("cand-en").status_code == 200
    response = _publish("cand-en")
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


def test_candidate_ignores_untrusted_translation_payload(tmp_path, monkeypatch):
    monkeypatch.setenv("STORAGE_DIR", str(tmp_path))
    payload = _translated_candidate("cand-untrusted", "rel-untrusted")
    payload["translation_variants"] = [
        {
            "id": "tr-root-en",
            "content_object_id": "root",
            "canonical_revision": 1,
            "target_language": "en-US",
            "revision": 3,
            "status": "approved",
        }
    ]
    response = _create_candidate(payload)
    assert response.status_code == 400
    findings = response.json()["detail"]["findings"]
    assert "translation-variant-not-found" in {item["code"] for item in findings}


def test_candidate_requires_approved_translation(tmp_path, monkeypatch):
    monkeypatch.setenv("STORAGE_DIR", str(tmp_path))
    _persist_translation(tmp_path, status="reviewed")
    response = _create_candidate(_translated_candidate("cand-draft", "rel-draft"))
    assert response.status_code == 400
    findings = response.json()["detail"]["findings"]
    assert "translation-not-approved" in {item["code"] for item in findings}


def test_candidate_requires_exact_trusted_canonical_revision(tmp_path, monkeypatch):
    monkeypatch.setenv("STORAGE_DIR", str(tmp_path))
    _persist_translation(tmp_path, canonical_revision=2)
    response = _create_candidate(_translated_candidate("cand-wrong", "rel-wrong"))
    assert response.status_code == 400
    findings = response.json()["detail"]["findings"]
    codes = {item["code"] for item in findings}
    assert "translation-canonical-revision-mismatch" in codes or "translation-variant-not-found" in codes
