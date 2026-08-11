"""Persistent, role-gated workflow API for Phase 6 translation variants."""

from __future__ import annotations

from typing import Any, Literal

from fastapi import APIRouter, Header, HTTPException, Query
from pydantic import BaseModel

from .canonical_content_store import CanonicalContentStore
from .phase6_roles import Phase6Principal
from .translation_store import TranslationVariantStore
from .translation_validation import validate_translation_variant
from .translations import TranslationVariant


router = APIRouter(prefix="/api/v1", tags=["phase6-translations"])


class TranslationCreatePayload(BaseModel):
    variant: dict[str, Any]


class TranslationStatusPayload(BaseModel):
    status: Literal["reviewed", "approved", "rejected", "superseded"]
    comment: str = ""


def _principal(user_id: str | None, role: str | None) -> Phase6Principal:
    try:
        return Phase6Principal.from_trusted_headers(user_id, role)
    except ValueError as exc:
        raise HTTPException(status_code=401, detail=str(exc)) from exc


def _require_transition(principal: Phase6Principal, current: str, target: str) -> None:
    if current == "generated" and target in {"reviewed", "rejected"}:
        if principal.role not in {"reviewer", "approver"}:
            raise HTTPException(status_code=403, detail="Reviewer or approver role is required")
        return
    if current == "reviewed" and target in {"approved", "rejected"}:
        if principal.role != "approver":
            raise HTTPException(status_code=403, detail="Approver role is required")
        return
    if current == "approved" and target == "superseded":
        if principal.role != "approver":
            raise HTTPException(status_code=403, detail="Approver role is required")
        return
    raise HTTPException(status_code=400, detail=f"Invalid translation status transition {current!r} -> {target!r}")


def _canonical_source(variant: TranslationVariant) -> dict[str, Any]:
    try:
        source = CanonicalContentStore().get(variant.content_object_id, variant.canonical_revision)
    except ValueError as exc:
        raise HTTPException(
            status_code=500,
            detail={"message": "Canonical source integrity check failed", "reason": str(exc)},
        ) from exc
    if source is None:
        raise HTTPException(
            status_code=400,
            detail={
                "message": "Trusted canonical source snapshot is required",
                "code": "canonical-source-not-registered",
                "content_object_id": variant.content_object_id,
                "canonical_revision": variant.canonical_revision,
            },
        )
    return source


def _source_binding_findings(variant: TranslationVariant, source: dict[str, Any]) -> list[dict[str, Any]]:
    findings: list[dict[str, Any]] = []
    payload = source["revision_payload"]
    source_segments = list(payload.get("sentence_segments", []))
    targets = variant.segment_translations
    if variant.target_language == source.get("canonical_language"):
        findings.append({
            "code": "translation-target-is-canonical-language",
            "message": "Translation target language must differ from the canonical source language",
        })
    if len(targets) != len(source_segments):
        findings.append({
            "code": "translation-segment-count-mismatch",
            "message": f"Expected {len(source_segments)} translation segments, got {len(targets)}",
        })
    for index, source_segment in enumerate(source_segments):
        if index >= len(targets):
            break
        target = targets[index]
        expected_id = str(source_segment.get("segment_id", ""))
        expected_order = source_segment.get("order", index)
        expected_text = str(source_segment.get("source_text", ""))
        if target.segment_id != expected_id:
            findings.append({
                "code": "translation-segment-id-mismatch",
                "message": f"Expected segment id {expected_id!r}, got {target.segment_id!r}",
                "segment_id": target.segment_id,
                "index": index,
            })
        if target.order != expected_order:
            findings.append({
                "code": "translation-segment-order-mismatch",
                "message": f"Expected order {expected_order}, got {target.order}",
                "segment_id": target.segment_id,
                "index": index,
            })
        if target.source_text != expected_text:
            findings.append({
                "code": "translation-source-text-mismatch",
                "message": f"Translation source text does not match trusted canonical segment {expected_id}",
                "segment_id": target.segment_id,
                "index": index,
            })
    return findings


def _validate_against_source(variant: TranslationVariant, *, target_status: str, full: bool) -> dict[str, Any]:
    source = _canonical_source(variant)
    findings = _source_binding_findings(variant, source)
    expected_checksum = str(variant.provider_metadata.get("canonical_source_checksum", ""))
    if expected_checksum and expected_checksum != source["payload_checksum"]:
        findings.append({
            "code": "translation-source-checksum-mismatch",
            "message": "Translation is bound to a different canonical source checksum",
        })
    if full:
        candidate = TranslationVariant.from_dict(variant.to_dict())
        candidate.status = target_status
        validation_findings = validate_translation_variant(
            candidate,
            list(source["revision_payload"].get("sentence_segments", [])),
            source_revision_status=str(source.get("approval_status", "")),
        )
        findings.extend({
            "code": item.code,
            "message": item.message,
            "segment_id": item.segment_id,
            "index": item.index,
        } for item in validation_findings)
    if findings:
        raise HTTPException(
            status_code=400,
            detail={"message": "Translation validation against trusted canonical source failed", "findings": findings},
        )
    return source


@router.post("/translations/variants", status_code=201)
def create_translation_variant(
    payload: TranslationCreatePayload,
    x_simqin_user: str | None = Header(default=None, alias="X-SIMQIN-User"),
    x_simqin_role: str | None = Header(default=None, alias="X-SIMQIN-Role"),
) -> dict[str, Any]:
    principal = _principal(x_simqin_user, x_simqin_role)
    if principal.role != "author":
        raise HTTPException(status_code=403, detail="Author role is required to create translation variants")
    try:
        variant = TranslationVariant.from_dict(payload.variant)
        source = _validate_against_source(variant, target_status="generated", full=False)
        variant.provider_metadata = dict(variant.provider_metadata)
        variant.provider_metadata["canonical_source_checksum"] = source["payload_checksum"]
        return TranslationVariantStore().add_variant(variant, created_by=principal.user_id)
    except HTTPException:
        raise
    except (TypeError, ValueError, KeyError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("/translations/variants")
def list_translation_variants(
    content_object_id: str = Query(default=""),
    canonical_revision: int | None = Query(default=None, ge=1),
    target_language: str = Query(default=""),
    status: str = Query(default=""),
) -> dict[str, Any]:
    rows = TranslationVariantStore().list(
        content_object_id=content_object_id.strip(),
        canonical_revision=canonical_revision,
        target_language=target_language.strip(),
        status=status.strip(),
    )
    return {"variants": rows, "count": len(rows)}


@router.get("/translations/variants/{variant_id}/{revision}")
def get_translation_variant(variant_id: str, revision: int) -> dict[str, Any]:
    row = TranslationVariantStore().get(variant_id, revision)
    if row is None:
        raise HTTPException(status_code=404, detail="Translation variant not found")
    return row


@router.get("/translations/variants/{variant_id}/{revision}/history")
def get_translation_history(variant_id: str, revision: int) -> dict[str, Any]:
    store = TranslationVariantStore()
    if store.get(variant_id, revision) is None:
        raise HTTPException(status_code=404, detail="Translation variant not found")
    events = store.history(variant_id, revision)
    return {"variant_id": variant_id, "revision": revision, "events": events, "count": len(events)}


@router.post("/translations/variants/{variant_id}/{revision}/status")
def transition_translation_status(
    variant_id: str,
    revision: int,
    payload: TranslationStatusPayload,
    x_simqin_user: str | None = Header(default=None, alias="X-SIMQIN-User"),
    x_simqin_role: str | None = Header(default=None, alias="X-SIMQIN-Role"),
) -> dict[str, Any]:
    principal = _principal(x_simqin_user, x_simqin_role)
    store = TranslationVariantStore()
    current = store.get(variant_id, revision)
    if current is None:
        raise HTTPException(status_code=404, detail="Translation variant not found")
    if principal.user_id == str(current.get("created_by", "")) and payload.status in {"reviewed", "approved"}:
        raise HTTPException(status_code=400, detail="Four-eyes rule violation: creator cannot review or approve own translation")
    _require_transition(principal, str(current.get("status", "")), payload.status)
    if payload.status == "approved":
        reviewed_events = [event for event in store.history(variant_id, revision) if event.get("status") == "reviewed"]
        if not reviewed_events:
            raise HTTPException(status_code=400, detail="Translation must be reviewed before approval")
        reviewer = str(reviewed_events[-1].get("changed_by", ""))
        if reviewer == principal.user_id:
            raise HTTPException(status_code=400, detail="Four-eyes rule violation: reviewer and approver must differ")
    if payload.status in {"reviewed", "approved"}:
        candidate = TranslationVariant.from_dict(current)
        _validate_against_source(candidate, target_status=payload.status, full=True)
    try:
        return store.transition(
            variant_id,
            revision,
            status=payload.status,
            changed_by=principal.user_id,
            comment=payload.comment,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
