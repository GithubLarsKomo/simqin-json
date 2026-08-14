"""Trusted multiplicity ruleset registry for Phase 6 releases."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Header, HTTPException
from pydantic import BaseModel, Field

from .phase6_roles import Phase6Principal
from .ruleset_store import RulesetStore


router = APIRouter(prefix="/api/v1", tags=["phase6-rulesets"])


class RulesetCreatePayload(BaseModel):
    ruleset_revision: str
    rules: list[dict[str, Any]] = Field(default_factory=list)


def _principal(user_id: str | None, role: str | None) -> Phase6Principal:
    try:
        return Phase6Principal.from_trusted_headers(user_id, role)
    except ValueError as exc:
        raise HTTPException(status_code=401, detail=str(exc)) from exc


@router.post("/rulesets", status_code=201)
def create_ruleset(
    payload: RulesetCreatePayload,
    x_simqin_user: str | None = Header(default=None, alias="X-SIMQIN-User"),
    x_simqin_role: str | None = Header(default=None, alias="X-SIMQIN-Role"),
) -> dict[str, Any]:
    principal = _principal(x_simqin_user, x_simqin_role)
    if principal.role != "approver":
        raise HTTPException(status_code=403, detail="Approver role is required to register trusted rulesets")
    try:
        return RulesetStore().add(
            payload.ruleset_revision,
            payload.rules,
            registered_by=principal.user_id,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("/rulesets")
def list_rulesets() -> dict[str, Any]:
    try:
        rows = RulesetStore().list()
    except ValueError as exc:
        raise HTTPException(
            status_code=500,
            detail={"message": "Trusted ruleset integrity check failed", "reason": str(exc)},
        ) from exc
    return {"rulesets": rows, "count": len(rows)}


@router.get("/rulesets/{ruleset_revision}")
def get_ruleset(ruleset_revision: str) -> dict[str, Any]:
    try:
        row = RulesetStore().get(ruleset_revision)
    except ValueError as exc:
        raise HTTPException(
            status_code=500,
            detail={"message": "Trusted ruleset integrity check failed", "reason": str(exc)},
        ) from exc
    if row is None:
        raise HTTPException(status_code=404, detail="Trusted ruleset not found")
    return row
