"""Trusted terminology profile registry API for Phase 6 releases."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Header, HTTPException
from pydantic import BaseModel

from .phase6_roles import Phase6Principal
from .terminology_store import TerminologyProfileStore


router = APIRouter(prefix="/api/v1", tags=["phase6-terminology"])


class TerminologyProfileCreatePayload(BaseModel):
    profile_revision: str
    profile: dict[str, Any]


def _principal(user_id: str | None, role: str | None) -> Phase6Principal:
    try:
        return Phase6Principal.from_trusted_headers(user_id, role)
    except ValueError as exc:
        raise HTTPException(status_code=401, detail=str(exc)) from exc


@router.post("/terminology/profiles", status_code=201)
def register_terminology_profile(
    payload: TerminologyProfileCreatePayload,
    x_simqin_user: str | None = Header(default=None, alias="X-SIMQIN-User"),
    x_simqin_role: str | None = Header(default=None, alias="X-SIMQIN-Role"),
) -> dict[str, Any]:
    principal = _principal(x_simqin_user, x_simqin_role)
    if principal.role != "approver":
        raise HTTPException(status_code=403, detail="Approver role is required to register terminology profiles")
    try:
        return TerminologyProfileStore().add(
            payload.profile_revision,
            payload.profile,
            registered_by=principal.user_id,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("/terminology/profiles")
def list_terminology_profiles() -> dict[str, Any]:
    try:
        rows = TerminologyProfileStore().list()
    except ValueError as exc:
        raise HTTPException(
            status_code=500,
            detail={"message": "Stored terminology profile integrity check failed", "reason": str(exc)},
        ) from exc
    return {"profiles": rows, "count": len(rows)}


@router.get("/terminology/profiles/{profile_revision}")
def get_terminology_profile(profile_revision: str) -> dict[str, Any]:
    try:
        row = TerminologyProfileStore().get(profile_revision)
    except ValueError as exc:
        raise HTTPException(
            status_code=500,
            detail={"message": "Stored terminology profile integrity check failed", "reason": str(exc)},
        ) from exc
    if row is None:
        raise HTTPException(status_code=404, detail="Terminology profile not found")
    return row
