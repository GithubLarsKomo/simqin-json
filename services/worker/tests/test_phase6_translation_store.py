from __future__ import annotations

from fastapi.testclient import TestClient

from app.canonical_content_store import CanonicalContentStore
from app.content_objects import ContentObjectRevision
from app.phase6_main import app
from app.translation_store import TranslationVariantStore
from app.translations import TranslationVariant


client = TestClient(app)
_AUTHOR = {"X-SIMQIN-User": "author-a", "X-SIMQIN-Role": "author"}
_REVIEWER = {"X-SIMQIN-User": "reviewer-b", "X-SIMQIN-Role": "reviewer"}
_APPROVER = {"X-SIMQIN-User": "approver-c", "X-SIMQIN-Role": "approver"}
_APPROVER_REVIEWER = {"X-SIMQIN-User": "approver-reviewer", "X-SIMQIN-Role": "approver"}


def _variant(status: str = "generated", *, translated_text: str = "Hello.", source_text: str = "Hallo.") -> dict:
    return {
        "id": "tr-root-en",
        "content_object_id": "root",
        "canonical_revision": 1,
        "target_language": "en-US",
        "revision": 1,
        "status": status,
        "segment_translations": [
            {
                "segment_id": "seg-1",
                "source_text": source_text,
                "translated_text": translated_text,
                "order": 0,
            }
        ],
    }


def _register_source(tmp_path, *, source_text: str = "Hallo.") -> None:
    revision = ContentObjectRevision.from_dict(
        {
            "object_id": "root",
            "revision": 1,
            "canonical_content": source_text,
            "sentence_segments": [
                {
                    "segment_id": "seg-1",
                    "segment_type": "sentence",
                    "source_text": source_text,
                    "source_revision": 1,
                    "order": 0,
                }
            ],
            "approval_status": "approved",
        }
    )
    CanonicalContentStore(tmp_path / "phase6-canonical-content.sqlite3").add(
        object_id="root",
        canonical_language="de-DE",
        revision=revision,
        registered_by="approver-source",
    )


def test_translation_store_persists_variant_and_append_only_history(tmp_path):
    store = TranslationVariantStore(tmp_path / "translations.sqlite3")
    created = store.add_variant(TranslationVariant.from_dict(_variant()), created_by="author-a")
    assert created["status"] == "generated"

    reviewed = store.transition("tr-root-en", 1, status="reviewed", changed_by="reviewer-b")
    assert reviewed["status"] == "reviewed"
    approved = store.transition("tr-root-en", 1, status="approved", changed_by="approver-c")
    assert approved["status"] == "approved"

    history = store.history("tr-root-en", 1)
    assert [row["status"] for row in history] == ["generated", "reviewed", "approved"]
    assert TranslationVariantStore(tmp_path / "translations.sqlite3").get("tr-root-en", 1)["status"] == "approved"


def test_translation_store_rejects_duplicate_revision_and_invalid_transition(tmp_path):
    store = TranslationVariantStore(tmp_path / "translations.sqlite3")
    variant = TranslationVariant.from_dict(_variant())
    store.add_variant(variant, created_by="author-a")
    try:
        store.add_variant(variant, created_by="author-a")
        assert False, "duplicate translation revision must be rejected"
    except ValueError as exc:
        assert "already exists" in str(exc)

    try:
        store.transition("tr-root-en", 1, status="approved", changed_by="approver-c")
        assert False, "generated -> approved must be rejected"
    except ValueError as exc:
        assert "Invalid translation status transition" in str(exc)


def test_translation_api_persists_lists_and_filters(tmp_path, monkeypatch):
    monkeypatch.setenv("STORAGE_DIR", str(tmp_path))
    _register_source(tmp_path)
    created = client.post("/api/v1/translations/variants", headers=_AUTHOR, json={"variant": _variant()})
    assert created.status_code == 201
    assert created.json()["created_by"] == "author-a"
    assert created.json()["provider_metadata"]["canonical_source_checksum"]

    listed = client.get(
        "/api/v1/translations/variants",
        params={"content_object_id": "root", "canonical_revision": 1, "target_language": "en-US"},
    )
    assert listed.status_code == 200
    assert listed.json()["count"] == 1
    assert listed.json()["variants"][0]["status"] == "generated"

    missing = client.get("/api/v1/translations/variants?status=approved")
    assert missing.status_code == 200
    assert missing.json()["count"] == 0


def test_translation_creation_requires_registered_trusted_source(tmp_path, monkeypatch):
    monkeypatch.setenv("STORAGE_DIR", str(tmp_path))
    response = client.post("/api/v1/translations/variants", headers=_AUTHOR, json={"variant": _variant()})
    assert response.status_code == 400
    detail = response.json()["detail"]
    assert detail["code"] == "canonical-source-not-registered"


def test_translation_creation_rejects_source_text_mismatch(tmp_path, monkeypatch):
    monkeypatch.setenv("STORAGE_DIR", str(tmp_path))
    _register_source(tmp_path)
    response = client.post(
        "/api/v1/translations/variants",
        headers=_AUTHOR,
        json={"variant": _variant(source_text="Manipuliert.")},
    )
    assert response.status_code == 400
    findings = response.json()["detail"]["findings"]
    assert "translation-source-text-mismatch" in {item["code"] for item in findings}


def test_translation_creation_requires_author_role(tmp_path, monkeypatch):
    monkeypatch.setenv("STORAGE_DIR", str(tmp_path))
    _register_source(tmp_path)
    response = client.post("/api/v1/translations/variants", headers=_REVIEWER, json={"variant": _variant()})
    assert response.status_code == 403
    assert "Author role" in str(response.json()["detail"])


def test_translation_api_enforces_roles_four_eyes_and_history(tmp_path, monkeypatch):
    monkeypatch.setenv("STORAGE_DIR", str(tmp_path))
    _register_source(tmp_path)
    created = client.post("/api/v1/translations/variants", headers=_AUTHOR, json={"variant": _variant()})
    assert created.status_code == 201

    self_review = client.post(
        "/api/v1/translations/variants/tr-root-en/1/status",
        headers=_AUTHOR,
        json={"status": "reviewed"},
    )
    assert self_review.status_code in {400, 403}

    reviewed = client.post(
        "/api/v1/translations/variants/tr-root-en/1/status",
        headers=_REVIEWER,
        json={"status": "reviewed"},
    )
    assert reviewed.status_code == 200
    assert reviewed.json()["status"] == "reviewed"

    reviewer_cannot_approve = client.post(
        "/api/v1/translations/variants/tr-root-en/1/status",
        headers=_REVIEWER,
        json={"status": "approved"},
    )
    assert reviewer_cannot_approve.status_code == 403

    approved = client.post(
        "/api/v1/translations/variants/tr-root-en/1/status",
        headers=_APPROVER,
        json={"status": "approved"},
    )
    assert approved.status_code == 200
    assert approved.json()["status"] == "approved"

    history = client.get("/api/v1/translations/variants/tr-root-en/1/history")
    assert history.status_code == 200
    assert [event["status"] for event in history.json()["events"]] == ["generated", "reviewed", "approved"]


def test_review_revalidates_placeholders_against_trusted_source(tmp_path, monkeypatch):
    monkeypatch.setenv("STORAGE_DIR", str(tmp_path))
    _register_source(tmp_path, source_text="Hallo {{name}}.")
    created = client.post(
        "/api/v1/translations/variants",
        headers=_AUTHOR,
        json={"variant": _variant(source_text="Hallo {{name}}.", translated_text="Hello.")},
    )
    assert created.status_code == 201
    reviewed = client.post(
        "/api/v1/translations/variants/tr-root-en/1/status",
        headers=_REVIEWER,
        json={"status": "reviewed"},
    )
    assert reviewed.status_code == 400
    findings = reviewed.json()["detail"]["findings"]
    assert "translation-placeholder-mismatch" in {item["code"] for item in findings}


def test_reviewer_and_approver_must_be_different_people(tmp_path, monkeypatch):
    monkeypatch.setenv("STORAGE_DIR", str(tmp_path))
    _register_source(tmp_path)
    created = client.post("/api/v1/translations/variants", headers=_AUTHOR, json={"variant": _variant()})
    assert created.status_code == 201

    reviewed = client.post(
        "/api/v1/translations/variants/tr-root-en/1/status",
        headers=_APPROVER_REVIEWER,
        json={"status": "reviewed"},
    )
    assert reviewed.status_code == 200

    self_approval = client.post(
        "/api/v1/translations/variants/tr-root-en/1/status",
        headers=_APPROVER_REVIEWER,
        json={"status": "approved"},
    )
    assert self_approval.status_code == 400
    assert "reviewer and approver must differ" in str(self_approval.json()["detail"])


def test_translation_rejection_and_supersede_require_comment(tmp_path, monkeypatch):
    monkeypatch.setenv("STORAGE_DIR", str(tmp_path))
    _register_source(tmp_path)
    client.post("/api/v1/translations/variants", headers=_AUTHOR, json={"variant": _variant()})

    rejected = client.post(
        "/api/v1/translations/variants/tr-root-en/1/status",
        headers=_REVIEWER,
        json={"status": "rejected"},
    )
    assert rejected.status_code == 400
    assert "Comment is required" in str(rejected.json()["detail"])
