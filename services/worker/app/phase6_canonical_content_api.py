"""Trusted immutable canonical source snapshots for Phase 6 translation review."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Header, HTTPException
from pydantic import BaseModel

from .canonical_content_store import CanonicalContentStore
from .content_objects import ContentObjectRevision
from .phase6_roles import Phase6Principal


router = APIRouter(prefix="/api/v1", tags=["phase6-canonical-content"])


class CanonicalSnapshotPayload(BaseModel):
    object_id: str
    canonical_language: str
    revision: dict[str, Any]


def _approver(user_id: str | None, role: str | None) -> Phase6Principal:
    try:
        principal = Phase6Principal.from_trusted_headers(user_id, role)
    except ValueError as exc:
        raise HTTPException(status_code=401, detail=str(exc)) from exc
    if principal.role != "approver":
        raise HTTPException(status_code=403, detail="Approver role is required to register canonical source snapshots")
    return principal


@router.post("/content/canonical-snapshots", status_code=201)
def create_canonical_snapshot(
    payload: CanonicalSnapshotPayload,
    x_simqin_user: str | None = Header(default=None, alias="X-SIMQIN-User"),
    x_simqin_role: str | None = Header(default=None, alias="X-SIMQIN-Role"),
) -> dict[str, Any]:
    principal = _approver(x_simqin_user, x_simqin_role)
    try:
        revision = ContentObjectRevision.from_dict(payload.revision)
        return CanonicalContentStore().add(
            object_id=payload.object_id,
            canonical_language=payload.canonical_language,
            revision=revision,
            registered_by=principal.user_id,
        )
    except (TypeError, ValueError, KeyError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("/content/canonical-snapshots")
def list_canonical_snapshots() -> dict[str, Any]:
    try:
        rows = CanonicalContentStore().list()
    except ValueError as exc:
        raise HTTPException(
            status_code=500,
            detail={"message": "Canonical source integrity check failed", "reason": str(exc)},
        ) from exc
    return {"snapshots": rows, "count": len(rows)}


@router.get("/content/canonical-snapshots/{object_id}/{revision}")
def get_canonical_snapshot(object_id: str, revision: int) -> dict[str, Any]:
    try:
        row = CanonicalContentStore().get(object_id, revision)
    except ValueError as exc:
        raise HTTPException(
            status_code=500,
            detail={"message": "Canonical source integrity check failed", "reason": str(exc)},
        ) from exc
    if row is None:
        raise HTTPException(status_code=404, detail="Canonical source snapshot not found")
    return row
