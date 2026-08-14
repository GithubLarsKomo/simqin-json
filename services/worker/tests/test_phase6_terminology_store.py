from __future__ import annotations

import sqlite3

from fastapi.testclient import TestClient

from app.phase6_main import app
from app.release_builder import ReleaseBuildError
from app.release_candidate_service import _trusted_terminology_profile
from app.terminology_store import TerminologyProfileStore


client = TestClient(app)
_APPROVER = {"X-SIMQIN-User": "approver-a", "X-SIMQIN-Role": "approver"}
_AUTHOR = {"X-SIMQIN-User": "author-a", "X-SIMQIN-Role": "author"}
_PROFILE = {
    "status": "approved",
    "language": "de-DE",
    "terms": [
        {"term_id": "sample", "preferred": "Probe", "forbidden": ["Specimen"]},
    ],
}


def test_terminology_store_detects_payload_tampering(tmp_path):
    database = tmp_path / "terminology.sqlite3"
    store = TerminologyProfileStore(database)
    created = store.add("term-1", _PROFILE, registered_by="approver-a")
    assert created["payload_checksum"]
    with sqlite3.connect(database) as connection:
        connection.execute(
            "UPDATE terminology_profiles SET payload_json = ? WHERE profile_revision = ?",
            ('{"status":"approved","terms":[]}', "term-1"),
        )
    try:
        store.get("term-1")
        assert False, "tampered terminology profile must fail integrity verification"
    except ValueError as exc:
        assert "failed checksum verification" in str(exc)


def test_terminology_api_requires_approver(tmp_path, monkeypatch):
    monkeypatch.setenv("STORAGE_DIR", str(tmp_path))
    body = {"profile_revision": "term-1", "profile": _PROFILE}
    forbidden = client.post("/api/v1/terminology/profiles", headers=_AUTHOR, json=body)
    assert forbidden.status_code == 403
    created = client.post("/api/v1/terminology/profiles", headers=_APPROVER, json=body)
    assert created.status_code == 201
    assert created.json()["profile_revision"] == "term-1"


def test_release_binding_requires_registered_terminology_profile(tmp_path, monkeypatch):
    monkeypatch.setenv("STORAGE_DIR", str(tmp_path))
    try:
        _trusted_terminology_profile("missing-profile")
        assert False, "unregistered terminology profile must block release candidate"
    except ReleaseBuildError as exc:
        assert exc.findings[0]["code"] == "terminology-profile-not-registered"


def test_release_binding_uses_trusted_terminology_checksum(tmp_path, monkeypatch):
    monkeypatch.setenv("STORAGE_DIR", str(tmp_path))
    trusted = TerminologyProfileStore().add("term-1", _PROFILE, registered_by="approver-a")
    assert _trusted_terminology_profile("term-1") == trusted["payload_checksum"]
