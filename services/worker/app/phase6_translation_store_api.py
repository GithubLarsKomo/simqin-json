"""Persistent, role-gated workflow API for Phase 6 translation variants."""

from __future__ import annotations

from typing import Any, Literal

from fastapi import APIRouter, Header, HTTPException, Query
from pydantic import BaseModel

from .phase6_roles import Phase6Principal
from .translation_store import TranslationVariantStore
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
        return TranslationVariantStore().add_variant(variant, created_by=principal.user_id)
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
