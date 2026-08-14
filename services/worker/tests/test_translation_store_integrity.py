from __future__ import annotations

import json
import sqlite3

import pytest

from app.translation_store import TranslationVariantStore
from app.translations import TranslationVariant


def _variant() -> TranslationVariant:
    return TranslationVariant.from_dict(
        {
            "id": "tr-integrity",
            "content_object_id": "root",
            "canonical_revision": 1,
            "target_language": "en-US",
            "revision": 1,
            "status": "generated",
            "segment_translations": [
                {
                    "segment_id": "seg-1",
                    "source_text": "Hallo.",
                    "translated_text": "Hello.",
                    "order": 0,
                }
            ],
        }
    )


def test_translation_store_detects_payload_tampering(tmp_path):
    database = tmp_path / "translations.sqlite3"
    store = TranslationVariantStore(database)
    store.add_variant(_variant(), created_by="author-a")

    with sqlite3.connect(database) as connection:
        row = connection.execute(
            "SELECT payload_json FROM translation_variants WHERE variant_id = ? AND revision = ?",
            ("tr-integrity", 1),
        ).fetchone()
        payload = json.loads(row[0])
        payload["segment_translations"][0]["translated_text"] = "Altered."
        connection.execute(
            "UPDATE translation_variants SET payload_json = ? WHERE variant_id = ? AND revision = ?",
            (json.dumps(payload, sort_keys=True), "tr-integrity", 1),
        )

    with pytest.raises(ValueError, match="failed checksum verification"):
        TranslationVariantStore(database).get("tr-integrity", 1)


def test_translation_store_detects_status_event_tampering(tmp_path):
    database = tmp_path / "translations.sqlite3"
    store = TranslationVariantStore(database)
    store.add_variant(_variant(), created_by="author-a")
    store.transition("tr-integrity", 1, status="reviewed", changed_by="reviewer-b")

    with sqlite3.connect(database) as connection:
        connection.execute(
            """
            UPDATE translation_status_events
            SET changed_by = ?
            WHERE variant_id = ? AND revision = ? AND sequence_no = 2
            """,
            ("altered-reviewer", "tr-integrity", 1),
        )

    with pytest.raises(ValueError, match="audit event 2 failed checksum verification"):
        TranslationVariantStore(database).get("tr-integrity", 1)


def test_translation_store_migrates_only_fully_legacy_history(tmp_path):
    database = tmp_path / "translations.sqlite3"
    store = TranslationVariantStore(database)
    store.add_variant(_variant(), created_by="author-a")
    store.transition("tr-integrity", 1, status="reviewed", changed_by="reviewer-b")

    with sqlite3.connect(database) as connection:
        connection.execute(
            """
            UPDATE translation_status_events
            SET sequence_no = NULL, previous_event_checksum = NULL, event_checksum = NULL
            WHERE variant_id = ? AND revision = ?
            """,
            ("tr-integrity", 1),
        )

    migrated = TranslationVariantStore(database)
    history = migrated.history("tr-integrity", 1)
    assert [event["sequence_no"] for event in history] == [1, 2]
    assert history[1]["previous_event_checksum"] == history[0]["event_checksum"]
    stable_checksum = history[1]["event_checksum"]

    reopened = TranslationVariantStore(database)
    assert reopened.history("tr-integrity", 1)[1]["event_checksum"] == stable_checksum

    with sqlite3.connect(database) as connection:
        connection.execute(
            "UPDATE translation_status_events SET event_checksum = NULL WHERE variant_id = ? AND revision = ? AND sequence_no = 2",
            ("tr-integrity", 1),
        )

    with pytest.raises(ValueError):
        TranslationVariantStore(database).get("tr-integrity", 1)
