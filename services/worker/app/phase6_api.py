"""HTTP API router for Phase 6 content resolution and validation."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from .content_build_graph import content_graph_report
from .content_objects import ContentObject, MultiplicityRule
from .content_resolver import resolve_content_tree
from .content_segment import ContentSegment
from .ifu_release import IFULanguageReleaseSnapshot
from .phase6_validation import validate_content_domain
from .translation_validation import validate_translation_variant
from .translations import TranslationVariant


router = APIRouter(prefix="/api/v1", tags=["phase6-content"])
_SCHEMA_DIR = Path(__file__).resolve().parent.parent / "schemas" / "phase6"


class ContentPayload(BaseModel):
    objects: list[dict[str, Any]] = Field(default_factory=list)
    pinned_revisions: dict[str, int] = Field(default_factory=dict)
    slot_values: dict[str, Any] = Field(default_factory=dict)


class ResolvePayload(ContentPayload):
    root_object_ids: list[str]
    aliases: dict[str, str] = Field(default_factory=dict)
    revision_mode: str = "working"
    multiplicity_rules: list[dict[str, Any]] = Field(default_factory=list)
    max_depth: int = 20


class TranslationValidatePayload(BaseModel):
    variant: dict[str, Any]
    source_segments: list[dict[str, Any]]
    source_revision_status: str = "approved"


class ReleaseVerifyPayload(BaseModel):
    release: dict[str, Any]


def _objects(rows: list[dict[str, Any]]) -> dict[str, ContentObject]:
    parsed: dict[str, ContentObject] = {}
    for row in rows:
        obj = ContentObject.from_dict(row)
        if obj.id in parsed:
            raise HTTPException(status_code=400, detail=f"Duplicate ContentObject id {obj.id}")
        parsed[obj.id] = obj
    return parsed


@router.get("/content/schemas")
def list_phase6_schemas() -> dict[str, Any]:
    names = sorted(path.stem.replace(".schema", "") for path in _SCHEMA_DIR.glob("*.schema.json"))
    return {"schemas": names, "count": len(names)}


@router.get("/content/schemas/{schema_name}")
def get_phase6_schema(schema_name: str) -> dict[str, Any]:
    if not schema_name or any(char not in "abcdefghijklmnopqrstuvwxyz0123456789-" for char in schema_name):
        raise HTTPException(status_code=400, detail="Invalid schema name")
    path = _SCHEMA_DIR / f"{schema_name}.schema.json"
    if not path.is_file():
        raise HTTPException(status_code=404, detail="Phase 6 schema not found")
    return json.loads(path.read_text(encoding="utf-8"))


@router.post("/content/graph")
def content_graph(payload: ContentPayload) -> dict[str, Any]:
    objects = _objects(payload.objects)
    return content_graph_report(objects, payload.pinned_revisions)


@router.post("/content/validate")
def content_validate(payload: ContentPayload) -> dict[str, Any]:
    objects = _objects(payload.objects)
    return validate_content_domain(
        objects,
        pinned_revisions=payload.pinned_revisions,
        slot_values=payload.slot_values,
    ).to_dict()


@router.post("/content/resolve")
def content_resolve(payload: ResolvePayload) -> dict[str, Any]:
    objects = _objects(payload.objects)
    rules = [MultiplicityRule.from_dict(row) for row in payload.multiplicity_rules]
    tree = resolve_content_tree(
        root_object_ids=payload.root_object_ids,
        objects=objects,
        pinned_revisions=payload.pinned_revisions,
        config_values=payload.slot_values,
        aliases=payload.aliases,
        max_depth=payload.max_depth,
        revision_mode=payload.revision_mode,
        multiplicity_rules=rules,
    )
    return tree.to_dict()


@router.post("/translations/validate")
def translation_validate(payload: TranslationValidatePayload) -> dict[str, Any]:
    variant = TranslationVariant.from_dict(payload.variant)
    segments = [ContentSegment.from_dict(row) for row in payload.source_segments]
    findings = validate_translation_variant(
        variant,
        segments,
        source_revision_status=payload.source_revision_status,
    )
    return {
        "valid": len(findings) == 0,
        "findings": [
            {
                "code": finding.code,
                "message": finding.message,
                "segment_id": finding.segment_id,
                "index": finding.index,
            }
            for finding in findings
        ],
    }


@router.post("/ifu/releases/verify")
def release_verify(payload: ReleaseVerifyPayload) -> dict[str, Any]:
    try:
        release = IFULanguageReleaseSnapshot.from_dict(payload.release)
    except (KeyError, TypeError, ValueError) as exc:
        raise HTTPException(status_code=400, detail=f"Invalid release snapshot: {exc}") from exc
    return {
        "valid": release.verify_checksum(),
        "release_id": release.release_id,
        "release_checksum": release.release_checksum,
        "computed_checksum": release.compute_checksum(),
    }
