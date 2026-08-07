from __future__ import annotations

from fastapi.testclient import TestClient

from app.phase6_main import app
from app.translation_store import TranslationVariantStore
from app.translations import TranslationVariant


client = TestClient(app)
_AUTHOR = {"X-SIMQIN-User": "author-a", "X-SIMQIN-Role": "author"}
_REVIEWER = {"X-SIMQIN-User": "reviewer-b", "X-SIMQIN-Role": "reviewer"}
_APPROVER = {"X-SIMQIN-User": "approver-c", "X-SIMQIN-Role": "approver"}


def _variant(status: str = "generated") -> dict:
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
                "source_text": "Hallo.",
                "translated_text": "Hello.",
                "order": 0,
            }
        ],
    }


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
    created = client.post("/api/v1/translations/variants", headers=_AUTHOR, json={"variant": _variant()})
    assert created.status_code == 201
    assert created.json()["created_by"] == "author-a"

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


def test_translation_api_enforces_roles_four_eyes_and_history(tmp_path, monkeypatch):
    monkeypatch.setenv("STORAGE_DIR", str(tmp_path))
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


def test_translation_rejection_and_supersede_require_comment(tmp_path, monkeypatch):
    monkeypatch.setenv("STORAGE_DIR", str(tmp_path))
    client.post("/api/v1/translations/variants", headers=_AUTHOR, json={"variant": _variant()})

    rejected = client.post(
        "/api/v1/translations/variants/tr-root-en/1/status",
        headers=_REVIEWER,
        json={"status": "rejected"},
    )
    assert rejected.status_code == 400
    assert "Comment is required" in str(rejected.json()["detail"])
