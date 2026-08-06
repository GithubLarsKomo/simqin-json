"""Privileged Phase 6 immutable release creation and retrieval API."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Literal

from fastapi import APIRouter, Header, HTTPException
from pydantic import BaseModel, Field

from .configuration import ConfigurationCatalog, ConfigurationParameter, ConfigurationValue
from .content_objects import ContentObject, MultiplicityRule
from .content_resolver import resolve_content_tree
from .phase6_roles import Phase6Principal
from .release_builder import ReleaseBuildError, build_language_release_snapshot
from .release_store import ReleaseStore


router = APIRouter(prefix="/api/v1", tags=["phase6-releases"])


class ReleaseCreatePayload(BaseModel):
    release_id: str
    product_id: str
    language: str
    version: int = Field(ge=1)
    root_object_ids: list[str]
    objects: list[dict[str, Any]]
    pinned_revisions: dict[str, int]
    slot_values: dict[str, Any] = Field(default_factory=dict)
    aliases: dict[str, str] = Field(default_factory=dict)
    multiplicity_rules: list[dict[str, Any]] = Field(default_factory=list)
    revision_mode: Literal["pinned"] = "pinned"
    configuration_parameters: list[dict[str, Any]] = Field(default_factory=list)
    configuration_values: list[dict[str, Any]] = Field(default_factory=list)
    ruleset_revision: str = ""
    terminology_profile_revision: str = ""
    source_release_id: str = ""


def _principal(user_id: str | None, role: str | None) -> Phase6Principal:
    try:
        principal = Phase6Principal.from_trusted_headers(user_id, role)
        principal.require("release")
        return principal
    except ValueError as exc:
        raise HTTPException(status_code=401, detail=str(exc)) from exc
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc


def _objects(rows: list[dict[str, Any]]) -> dict[str, ContentObject]:
    parsed: dict[str, ContentObject] = {}
    for row in rows:
        obj = ContentObject.from_dict(row)
        if obj.id in parsed:
            raise ValueError(f"Duplicate ContentObject id {obj.id}")
        parsed[obj.id] = obj
    return parsed


def _integrity_error(exc: ValueError) -> HTTPException:
    return HTTPException(
        status_code=500,
        detail={"message": "Stored release integrity check failed", "reason": str(exc)},
    )


@router.post("/ifu/releases", status_code=201)
def create_release(
    payload: ReleaseCreatePayload,
    x_simqin_user: str | None = Header(default=None, alias="X-SIMQIN-User"),
    x_simqin_role: str | None = Header(default=None, alias="X-SIMQIN-Role"),
) -> dict[str, Any]:
    principal = _principal(x_simqin_user, x_simqin_role)
    try:
        objects = _objects(payload.objects)
        rules = [MultiplicityRule.from_dict(row) for row in payload.multiplicity_rules]
        tree = resolve_content_tree(
            root_object_ids=payload.root_object_ids,
            objects=objects,
            pinned_revisions=payload.pinned_revisions,
            config_values=payload.slot_values,
            aliases=payload.aliases,
            revision_mode=payload.revision_mode,
            multiplicity_rules=rules,
        )
        catalog = ConfigurationCatalog()
        for row in payload.configuration_parameters:
            catalog.add(ConfigurationParameter.from_dict(row))
        values = [ConfigurationValue.from_dict(row) for row in payload.configuration_values]
        release = build_language_release_snapshot(
            release_id=payload.release_id,
            product_id=payload.product_id,
            language=payload.language,
            version=payload.version,
            resolved_tree=tree,
            configuration_catalog=catalog,
            configuration_values=values,
            ruleset_revision=payload.ruleset_revision,
            terminology_profile_revision=payload.terminology_profile_revision,
            source_release_id=payload.source_release_id,
            created_at=datetime.now(timezone.utc).isoformat(),
            created_by=principal.user_id,
        )
        return ReleaseStore().add(release)
    except ReleaseBuildError as exc:
        raise HTTPException(status_code=400, detail={"message": str(exc), "findings": exc.findings}) from exc
    except (TypeError, ValueError, KeyError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("/ifu/releases")
def list_releases() -> dict[str, Any]:
    try:
        releases = ReleaseStore().list()
    except ValueError as exc:
        raise _integrity_error(exc) from exc
    return {"releases": releases, "count": len(releases)}


@router.get("/ifu/releases/{release_id}")
def get_release(release_id: str) -> dict[str, Any]:
    try:
        release = ReleaseStore().get(release_id)
    except ValueError as exc:
        raise _integrity_error(exc) from exc
    if release is None:
        raise HTTPException(status_code=404, detail="Release not found")
    return release
