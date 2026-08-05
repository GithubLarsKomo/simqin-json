from __future__ import annotations

from fastapi.testclient import TestClient

from app.phase6_main import app
from app.review_store import ReviewDecisionStore


client = TestClient(app)
_REVIEWER_HEADERS = {
    "X-SIMQIN-User": "reviewer-b",
    "X-SIMQIN-Role": "reviewer",
}
_APPROVER_HEADERS = {
    "X-SIMQIN-User": "approver-c",
    "X-SIMQIN-Role": "approver",
}
_AUTHOR_HEADERS = {
    "X-SIMQIN-User": "author-z",
    "X-SIMQIN-Role": "author",
}


def test_review_store_persists_across_instances(tmp_path):
    database = tmp_path / "reviews.sqlite3"
    first = ReviewDecisionStore(database)
    created = first.add_decision(
        migration_id="mig-1",
        created_by="author-a",
        reviewer="reviewer-b",
        decision="approved",
    )

    second = ReviewDecisionStore(database)
    rows = second.list_decisions("mig-1")

    assert len(rows) == 1
    assert rows[0]["decision_id"] == created["decision_id"]
    assert rows[0]["decision"] == "approved"


def test_review_store_enforces_four_eyes_rule(tmp_path):
    store = ReviewDecisionStore(tmp_path / "reviews.sqlite3")

    try:
        store.add_decision(
            migration_id="mig-1",
            created_by="author-a",
            reviewer="author-a",
            decision="approved",
        )
    except ValueError as exc:
        assert "Four-eyes" in str(exc)
    else:
        raise AssertionError("Self-review must be rejected")


def test_review_store_requires_comment_for_negative_decisions(tmp_path):
    store = ReviewDecisionStore(tmp_path / "reviews.sqlite3")

    for decision in ("rejected", "changes_requested"):
        try:
            store.add_decision(
                migration_id="mig-1",
                created_by="author-a",
                reviewer="reviewer-b",
                decision=decision,
            )
        except ValueError as exc:
            assert "Comment is required" in str(exc)
        else:
            raise AssertionError(f"{decision} without comment must be rejected")


def test_review_store_is_append_only(tmp_path):
    store = ReviewDecisionStore(tmp_path / "reviews.sqlite3")
    store.add_decision(
        migration_id="mig-1",
        created_by="author-a",
        reviewer="reviewer-b",
        decision="changes_requested",
        comment="Please preserve sentence boundaries.",
    )
    store.add_decision(
        migration_id="mig-1",
        created_by="author-a",
        reviewer="reviewer-c",
        decision="approved",
    )

    rows = store.list_decisions("mig-1")
    assert [row["decision"] for row in rows] == ["changes_requested", "approved"]


def test_review_api_requires_trusted_identity_and_role(tmp_path, monkeypatch):
    monkeypatch.setenv("STORAGE_DIR", str(tmp_path))

    response = client.post(
        "/api/v1/reviews/migrations/mig-api/decisions",
        json={"created_by": "author-a", "decision": "approved"},
    )

    assert response.status_code == 401
    assert "Trusted user identity" in response.json()["detail"]


def test_author_role_cannot_review(tmp_path, monkeypatch):
    monkeypatch.setenv("STORAGE_DIR", str(tmp_path))

    response = client.post(
        "/api/v1/reviews/migrations/mig-api/decisions",
        headers=_AUTHOR_HEADERS,
        json={"created_by": "author-a", "decision": "approved"},
    )

    assert response.status_code == 403
    assert "not permitted" in response.json()["detail"]


def test_reviewer_role_persists_and_lists_decisions(tmp_path, monkeypatch):
    monkeypatch.setenv("STORAGE_DIR", str(tmp_path))

    response = client.post(
        "/api/v1/reviews/migrations/mig-api/decisions",
        headers=_REVIEWER_HEADERS,
        json={
            "created_by": "author-a",
            "decision": "rejected",
            "comment": "Segment mapping needs correction.",
        },
    )
    assert response.status_code == 201
    body = response.json()
    assert body["migration_id"] == "mig-api"
    assert body["decision"] == "rejected"
    assert body["reviewer"] == "reviewer-b"

    listed = client.get("/api/v1/reviews/migrations/mig-api/decisions")
    assert listed.status_code == 200
    payload = listed.json()
    assert payload["count"] == 1
    assert payload["decisions"][0]["comment"] == "Segment mapping needs correction."


def test_approver_role_can_review(tmp_path, monkeypatch):
    monkeypatch.setenv("STORAGE_DIR", str(tmp_path))

    response = client.post(
        "/api/v1/reviews/migrations/mig-approver/decisions",
        headers=_APPROVER_HEADERS,
        json={"created_by": "author-a", "decision": "approved"},
    )

    assert response.status_code == 201
    assert response.json()["reviewer"] == "approver-c"


def test_review_api_rejects_self_review_from_trusted_identity(tmp_path, monkeypatch):
    monkeypatch.setenv("STORAGE_DIR", str(tmp_path))

    response = client.post(
        "/api/v1/reviews/migrations/mig-api/decisions",
        headers={"X-SIMQIN-User": "author-a", "X-SIMQIN-Role": "reviewer"},
        json={"created_by": "author-a", "decision": "approved"},
    )
    assert response.status_code == 400
    assert "Four-eyes" in response.json()["detail"]
