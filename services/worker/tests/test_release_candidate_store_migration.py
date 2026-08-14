from __future__ import annotations

import hashlib
import json
import sqlite3

import pytest

from app.release_candidate_store import ReleaseCandidateStore


def _canonical_json(value: object) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _checksum(value: object) -> str:
    return hashlib.sha256(_canonical_json(value).encode("utf-8")).hexdigest()


def _create_legacy_database(path) -> None:
    payload = {
        "release_id": "rel-legacy",
        "version": 1,
        "product_id": "prod-legacy",
        "language": "de-DE",
    }
    payload_json = _canonical_json(payload)
    payload_checksum = _checksum(payload)
    with sqlite3.connect(path) as connection:
        connection.execute(
            """
            CREATE TABLE release_candidates (
                candidate_id TEXT PRIMARY KEY,
                product_id TEXT NOT NULL,
                language TEXT NOT NULL,
                payload_json TEXT NOT NULL,
                payload_checksum TEXT NOT NULL,
                created_at TEXT NOT NULL,
                created_by TEXT NOT NULL
            )
            """
        )
        connection.execute(
            """
            CREATE TABLE release_candidate_events (
                event_id INTEGER PRIMARY KEY AUTOINCREMENT,
                candidate_id TEXT NOT NULL,
                status TEXT NOT NULL,
                changed_at TEXT NOT NULL,
                changed_by TEXT NOT NULL,
                comment TEXT NOT NULL DEFAULT ''
            )
            """
        )
        connection.execute(
            """
            INSERT INTO release_candidates (
                candidate_id, product_id, language, payload_json,
                payload_checksum, created_at, created_by
            ) VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                "cand-legacy",
                "prod-legacy",
                "de-DE",
                payload_json,
                payload_checksum,
                "2026-08-01T10:00:00+00:00",
                "author-a",
            ),
        )
        connection.execute(
            """
            INSERT INTO release_candidate_events (
                candidate_id, status, changed_at, changed_by, comment
            ) VALUES (?, ?, ?, ?, ?)
            """,
            (
                "cand-legacy",
                "candidate",
                "2026-08-01T10:00:00+00:00",
                "author-a",
                "",
            ),
        )
        connection.execute(
            """
            INSERT INTO release_candidate_events (
                candidate_id, status, changed_at, changed_by, comment
            ) VALUES (?, ?, ?, ?, ?)
            """,
            (
                "cand-legacy",
                "approved",
                "2026-08-01T11:00:00+00:00",
                "approver-b",
                "approved",
            ),
        )


def test_legacy_history_is_backfilled_once(tmp_path):
    database = tmp_path / "legacy.sqlite3"
    _create_legacy_database(database)

    store = ReleaseCandidateStore(database)
    history = store.history("cand-legacy")

    assert [event["sequence_no"] for event in history] == [1, 2]
    assert history[0]["previous_event_checksum"] == ""
    assert history[0]["event_checksum"]
    assert history[1]["previous_event_checksum"] == history[0]["event_checksum"]
    original_checksums = [event["event_checksum"] for event in history]

    # Reopening the store must verify/preserve an existing chain, never reseal it.
    reopened = ReleaseCandidateStore(database)
    assert [event["event_checksum"] for event in reopened.history("cand-legacy")] == original_checksums


def test_partially_chained_history_is_not_repaired(tmp_path):
    database = tmp_path / "partial.sqlite3"
    _create_legacy_database(database)

    # First initialization adds the chain columns and performs the legitimate legacy backfill.
    ReleaseCandidateStore(database)

    with sqlite3.connect(database) as connection:
        connection.execute(
            """
            UPDATE release_candidate_events
            SET event_checksum = NULL
            WHERE candidate_id = ? AND sequence_no = 2
            """,
            ("cand-legacy",),
        )

    # A partially present chain is not legacy. Reopening must not repair/reseal it.
    reopened = ReleaseCandidateStore(database)
    with pytest.raises(ValueError, match="audit event 2 failed checksum verification"):
        reopened.history("cand-legacy")
