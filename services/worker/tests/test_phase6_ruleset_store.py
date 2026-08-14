from __future__ import annotations

import sqlite3

from fastapi.testclient import TestClient

from app.phase6_main import app
from app.release_builder import ReleaseBuildError
from app.release_candidate_service import _trusted_ruleset
from app.ruleset_store import RulesetStore


client = TestClient(app)
_APPROVER = {"X-SIMQIN-User": "approver-rules", "X-SIMQIN-Role": "approver"}
_REVIEWER = {"X-SIMQIN-User": "reviewer-rules", "X-SIMQIN-Role": "reviewer"}


def _rules() -> list[dict]:
    return [
        {
            "object_id": "warning-a",
            "mode": "multiple",
            "max_occurrences": 3,
            "reason": "May recur per assay component",
            "revision": 1,
            "status": "approved",
        }
    ]


def test_ruleset_registry_requires_approver_and_persists(tmp_path, monkeypatch):
    monkeypatch.setenv("STORAGE_DIR", str(tmp_path))
    body = {"ruleset_revision": "rules-1", "rules": _rules()}
    denied = client.post("/api/v1/rulesets", headers=_REVIEWER, json=body)
    assert denied.status_code == 403
    created = client.post("/api/v1/rulesets", headers=_APPROVER, json=body)
    assert created.status_code == 201
    assert created.json()["ruleset_revision"] == "rules-1"
    assert created.json()["payload_checksum"]
    listed = client.get("/api/v1/rulesets")
    assert listed.status_code == 200
    assert listed.json()["count"] == 1


def test_candidate_rules_are_loaded_from_trusted_ruleset(tmp_path, monkeypatch):
    monkeypatch.setenv("STORAGE_DIR", str(tmp_path))
    trusted = RulesetStore().add("rules-1", _rules(), registered_by="approver-rules")
    rules, checksum = _trusted_ruleset("rules-1", [])
    assert [rule.to_dict() for rule in rules] == trusted["rules"]
    assert checksum == trusted["payload_checksum"]


def test_candidate_rejects_asserted_ruleset_mismatch(tmp_path, monkeypatch):
    monkeypatch.setenv("STORAGE_DIR", str(tmp_path))
    RulesetStore().add("rules-1", _rules(), registered_by="approver-rules")
    altered = _rules()
    altered[0]["max_occurrences"] = 4
    try:
        _trusted_ruleset("rules-1", altered)
        assert False, "mismatched client rules must be rejected"
    except ReleaseBuildError as exc:
        assert "ruleset-mismatch" in {item["code"] for item in exc.findings}


def test_ruleset_integrity_tampering_is_detected(tmp_path):
    database = tmp_path / "rulesets.sqlite3"
    store = RulesetStore(database)
    store.add("rules-1", _rules(), registered_by="approver-rules")
    with sqlite3.connect(database) as connection:
        connection.execute(
            "UPDATE rulesets SET payload_json = ? WHERE ruleset_revision = ?",
            ('{"rules":[]}', "rules-1"),
        )
    try:
        RulesetStore(database).get("rules-1")
        assert False, "tampered trusted ruleset must fail integrity verification"
    except ValueError as exc:
        assert "failed checksum verification" in str(exc)
