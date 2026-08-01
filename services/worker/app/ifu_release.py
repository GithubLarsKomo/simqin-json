"""Immutable, checksum-verifiable IFU language release snapshots."""

from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass, field
from types import MappingProxyType
from typing import Any, Mapping


def _canonical_json(data: Any) -> str:
    return json.dumps(data, sort_keys=True, ensure_ascii=False, separators=(",", ":"))


def _freeze_mapping(value: Mapping[str, Any] | None) -> Mapping[str, Any]:
    return MappingProxyType(json.loads(json.dumps(dict(value or {}), sort_keys=True)))


@dataclass(frozen=True)
class ContentRevisionBinding:
    object_id: str
    revision: int


@dataclass(frozen=True)
class TranslationRevisionBinding:
    content_object_id: str
    target_language: str
    variant_id: str
    revision: int
    canonical_revision: int


@dataclass(frozen=True)
class ResolvedBlockSnapshot:
    block_id: str
    source_object_id: str
    source_revision: int
    rendered_content: str
    block_type: str = "text"


@dataclass(frozen=True)
class IFULanguageReleaseSnapshot:
    release_id: str
    product_id: str
    language: str
    version: int
    content_bindings: tuple[ContentRevisionBinding, ...] = field(default_factory=tuple)
    translation_bindings: tuple[TranslationRevisionBinding, ...] = field(default_factory=tuple)
    configuration_snapshot: Mapping[str, Any] = field(default_factory=lambda: MappingProxyType({}))
    resolved_blocks: tuple[ResolvedBlockSnapshot, ...] = field(default_factory=tuple)
    ruleset_revision: str = ""
    terminology_profile_revision: str = ""
    provenance: Mapping[str, Any] = field(default_factory=lambda: MappingProxyType({}))
    source_release_id: str = ""
    created_at: str = ""
    created_by: str = ""
    release_checksum: str = ""

    def __post_init__(self) -> None:
        object.__setattr__(self, "content_bindings", tuple(self.content_bindings))
        object.__setattr__(self, "translation_bindings", tuple(self.translation_bindings))
        object.__setattr__(self, "resolved_blocks", tuple(self.resolved_blocks))
        object.__setattr__(self, "configuration_snapshot", _freeze_mapping(self.configuration_snapshot))
        object.__setattr__(self, "provenance", _freeze_mapping(self.provenance))
        if not self.release_checksum:
            object.__setattr__(self, "release_checksum", self.compute_checksum())

    def checksum_payload(self) -> dict[str, Any]:
        return {
            "release_id": self.release_id,
            "product_id": self.product_id,
            "language": self.language,
            "version": self.version,
            "content_bindings": [asdict(item) for item in self.content_bindings],
            "translation_bindings": [asdict(item) for item in self.translation_bindings],
            "configuration_snapshot": dict(self.configuration_snapshot),
            "resolved_blocks": [asdict(item) for item in self.resolved_blocks],
            "ruleset_revision": self.ruleset_revision,
            "terminology_profile_revision": self.terminology_profile_revision,
            "provenance": dict(self.provenance),
            "source_release_id": self.source_release_id,
            "created_at": self.created_at,
            "created_by": self.created_by,
        }

    def compute_checksum(self) -> str:
        return hashlib.sha256(_canonical_json(self.checksum_payload()).encode("utf-8")).hexdigest()

    def verify_checksum(self) -> bool:
        return self.release_checksum == self.compute_checksum()

    def to_dict(self) -> dict[str, Any]:
        return {**self.checksum_payload(), "release_checksum": self.release_checksum}

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "IFULanguageReleaseSnapshot":
        return cls(
            release_id=data["release_id"], product_id=data["product_id"],
            language=data["language"], version=data["version"],
            content_bindings=tuple(ContentRevisionBinding(**item) for item in data.get("content_bindings", [])),
            translation_bindings=tuple(TranslationRevisionBinding(**item) for item in data.get("translation_bindings", [])),
            configuration_snapshot=data.get("configuration_snapshot", {}),
            resolved_blocks=tuple(ResolvedBlockSnapshot(**item) for item in data.get("resolved_blocks", [])),
            ruleset_revision=data.get("ruleset_revision", ""),
            terminology_profile_revision=data.get("terminology_profile_revision", ""),
            provenance=data.get("provenance", {}), source_release_id=data.get("source_release_id", ""),
            created_at=data.get("created_at", ""), created_by=data.get("created_by", ""),
            release_checksum=data.get("release_checksum", ""),
        )
