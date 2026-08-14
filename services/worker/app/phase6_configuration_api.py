"""Trusted configuration parameter registry for Phase 6 release candidates."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Header, HTTPException
from pydantic import BaseModel

from .configuration import ConfigurationParameter
from .configuration_store import ConfigurationParameterStore
from .phase6_roles import Phase6Principal


router = APIRouter(prefix="/api/v1", tags=["phase6-configuration"])


class ConfigurationParameterRegistration(BaseModel):
    parameter: dict[str, Any]


def _principal(user_id: str | None, role: str | None) -> Phase6Principal:
    try:
        return Phase6Principal.from_trusted_headers(user_id, role)
    except ValueError as exc:
        raise HTTPException(status_code=401, detail=str(exc)) from exc


def _integrity_error(exc: ValueError) -> HTTPException:
    return HTTPException(
        status_code=500,
        detail={"message": "Trusted configuration integrity check failed", "reason": str(exc)},
    )


@router.post("/configuration/parameters", status_code=201)
def register_configuration_parameter(
    payload: ConfigurationParameterRegistration,
    x_simqin_user: str | None = Header(default=None, alias="X-SIMQIN-User"),
    x_simqin_role: str | None = Header(default=None, alias="X-SIMQIN-Role"),
) -> dict[str, Any]:
    principal = _principal(x_simqin_user, x_simqin_role)
    if principal.role != "approver":
        raise HTTPException(status_code=403, detail="Approver role is required")
    try:
        parameter = ConfigurationParameter.from_dict(payload.parameter)
        return ConfigurationParameterStore().add(parameter, registered_by=principal.user_id)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("/configuration/parameters")
def list_configuration_parameters() -> dict[str, Any]:
    try:
        rows = ConfigurationParameterStore().list()
    except ValueError as exc:
        raise _integrity_error(exc) from exc
    return {"parameters": rows, "count": len(rows)}


@router.get("/configuration/parameters/{parameter_id}/{revision}")
def get_configuration_parameter(parameter_id: str, revision: int) -> dict[str, Any]:
    try:
        row = ConfigurationParameterStore().get(parameter_id, revision)
    except ValueError as exc:
        raise _integrity_error(exc) from exc
    if row is None:
        raise HTTPException(status_code=404, detail="Configuration parameter revision not found")
    return row
