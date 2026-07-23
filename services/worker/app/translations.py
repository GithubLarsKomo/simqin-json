"""Translation domain model — no LLM calls, only future-facing data structures."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _new_id() -> str:
    return str(uuid.uuid4())


TRANSLATION_STATUSES = {"generated", "reviewed", "approved", "rejected", "superseded"}


class TranslationProviderConfig:
    """Configuration for a translation provider (future LLM integration)."""

    def __init__(self, provider_id: str = "", name: str = "", model: str = "", settings: dict[str, Any] | None = None) -> None:
        self.provider_id = provider_id or _new_id()
        self.name = name
        self.model = model
        self.settings = settings or {}

    def to_dict(self) -> dict[str, Any]:
        return {"provider_id": self.provider_id, "name": self.name, "model": self.model, "settings": self.settings}

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "TranslationProviderConfig":
        return cls(provider_id=d.get("provider_id", ""), name=d.get("name", ""), model=d.get("model", ""), settings=d.get("settings", {}))


class TranslationSegment:
    """A single sentence/segment translation."""

    def __init__(self, segment_id: str = "", source_text: str = "", translated_text: str = "", order: int = 0) -> None:
        self.segment_id = segment_id
        self.source_text = source_text
        self.translated_text = translated_text
        self.order = order

    def to_dict(self) -> dict[str, Any]:
        return {"segment_id": self.segment_id, "source_text": self.source_text, "translated_text": self.translated_text, "order": self.order}

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "TranslationSegment":
        return cls(segment_id=d.get("segment_id", ""), source_text=d.get("source_text", ""), translated_text=d.get("translated_text", ""), order=d.get("order", 0))


class TranslationVariant:
    """A translation variant for a specific language and market."""

    def __init__(
        self,
        id: str = "",
        content_object_id: str = "",
        canonical_revision: int = 1,
        target_language: str = "",
        revision: int = 1,
        status: str = "generated",
        applicability: dict[str, str] | None = None,
        segment_translations: list[TranslationSegment] | None = None,
        provider_metadata: dict[str, Any] | None = None,
        created_at: str = "",
        created_by: str = "",
    ) -> None:
        self.id = id or _new_id()
        self.content_object_id = content_object_id
        self.canonical_revision = canonical_revision
        self.target_language = target_language
        self.revision = revision
        self.status = status
        self.applicability = applicability or {}
        self.segment_translations = segment_translations or []
        self.provider_metadata = provider_metadata or {}
        self.created_at = created_at or _now()
        self.created_by = created_by

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "content_object_id": self.content_object_id,
            "canonical_revision": self.canonical_revision,
            "target_language": self.target_language,
            "revision": self.revision,
            "status": self.status,
            "applicability": self.applicability,
            "segment_translations": [s.to_dict() for s in self.segment_translations],
            "provider_metadata": self.provider_metadata,
            "created_at": self.created_at,
            "created_by": self.created_by,
        }

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "TranslationVariant":
        return cls(
            id=d.get("id", ""),
            content_object_id=d.get("content_object_id", ""),
            canonical_revision=d.get("canonical_revision", 1),
            target_language=d.get("target_language", ""),
            revision=d.get("revision", 1),
            status=d.get("status", "generated"),
            applicability=d.get("applicability", {}),
            segment_translations=[TranslationSegment.from_dict(s) for s in d.get("segment_translations", [])],
            provider_metadata=d.get("provider_metadata", {}),
            created_at=d.get("created_at", ""),
            created_by=d.get("created_by", ""),
        )


def validate_segment_count(variant: TranslationVariant, source_segments: list[dict[str, Any]]) -> list[str]:
    """Enforce 1:1 segment relationship between source and translation."""
    errors: list[str] = []
    if len(variant.segment_translations) != len(source_segments):
        errors.append(
            f"Translation segment count ({len(variant.segment_translations)}) "
            f"does not match source segment count ({len(source_segments)})"
        )
        return errors
    for i, (src, seg) in enumerate(zip(source_segments, variant.segment_translations)):
        if src.get("segment_id") and seg.segment_id and src["segment_id"] != seg.segment_id:
            errors.append(
                f"Segment ID mismatch at position {i}: source={src.get('segment_id')}, "
                f"translation={seg.segment_id}"
            )
    return errors