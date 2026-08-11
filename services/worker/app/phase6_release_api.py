"""Four-eyes Phase 6 release candidate and immutable publication API."""

from __future__ import annotations

from typing import Any, Literal

from fastapi import APIRouter, Header, HTTPException
from pydantic import BaseModel, Field

from .phase6_roles import Phase6Principal
from .release_builder import ReleaseBuildError
from .release_candidate_service import build_from_candidate_payload, validate_candidate_payload
from .release_candidate_store import ReleaseCandidateStore
from .release_store import ReleaseStore
from .release_translation import ReleaseTranslationError


router = APIRouter(prefix="/api/v1", tags=["phase6-releases"])


class ReleaseCandidateCreatePayload(BaseModel):
    candidate_id: str
    product_id: str
    language: str
    root_object_ids: list[str]
    objects: list[dict[str, Any]]
    pinned_revisions: dict[str, int]
    slot_values: dict[str, Any] = Field(default_factory=dict)
    aliases: dict[str, str] = Field(default_factory=dict)
    multiplicity_rules: list[dict[str, Any]] = Field(default_factory=list)
    revision_mode: Literal["pinned"] = "pinned"
    configuration_parameters: list[dict[str, Any]] = Field(default_factory=list)
    configuration_values: list[dict[str, Any]] = Field(default_factory=list)
    translation_selections: list[dict[str, Any]] = Field(default_factory=list)
    ruleset_revision: str = ""
    terminology_profile_revision: str = ""
    source_release_id: str = ""


class ReleaseCandidateDecisionPayload(BaseModel):
    decision: Literal["approved", "rejected"]
    comment: str = ""


class ReleaseCreatePayload(BaseModel):
    candidate_id: str
    release_id: str
    version: int = Field(ge=1)


def _principal(user_id: str | None, role: str | None) -> Phase6Principal:
    try:
        return Phase6Principal.from_trusted_headers(user_id, role)
    except ValueError as exc:
        raise HTTPException(status_code=401, detail=str(exc)) from exc


def _release_principal(user_id: str | None, role: str | None) -> Phase6Principal:
    principal = _principal(user_id, role)
    try:
        principal.require("release")
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    return principal


def _candidate_error(exc: Exception) -> HTTPException:
    if isinstance(exc, ReleaseTranslationError):
        return HTTPException(status_code=400, detail={"message": str(exc), "findings": exc.findings})
    if isinstance(exc, ReleaseBuildError):
        return HTTPException(status_code=400, detail={"message": str(exc), "findings": exc.findings})
    return HTTPException(status_code=400, detail=str(exc))


def _integrity_error(exc: ValueError, message: str) -> HTTPException:
    return HTTPException(status_code=500, detail={"message": message, "reason": str(exc)})


@router.post("/ifu/release-candidates", status_code=201)
def create_release_candidate(
    payload: ReleaseCandidateCreatePayload,
    x_simqin_user: str | None = Header(default=None, alias="X-SIMQIN-User"),
    x_simqin_role: str | None = Header(default=None, alias="X-SIMQIN-Role"),
) -> dict[str, Any]:
    principal = _principal(x_simqin_user, x_simqin_role)
    frozen = payload.model_dump()
    candidate_id = frozen.pop("candidate_id")
    try:
        validation = validate_candidate_payload(frozen)
        saved = ReleaseCandidateStore().add(candidate_id, frozen, created_by=principal.user_id)
        return {**saved, "validation": validation}
    except (ReleaseTranslationError, ReleaseBuildError, TypeError, ValueError, KeyError) as exc:
        raise _candidate_error(exc) from exc


@router.get("/ifu/release-candidates")
def list_release_candidates() -> dict[str, Any]:
    try:
        rows = ReleaseCandidateStore().list()
    except ValueError as exc:
        raise _integrity_error(exc, "Stored release candidate integrity check failed") from exc
    return {"candidates": rows, "count": len(rows)}


@router.get("/ifu/release-candidates/{candidate_id}")
def get_release_candidate(candidate_id: str) -> dict[str, Any]:
    try:
        row = ReleaseCandidateStore().get(candidate_id)
    except ValueError as exc:
        raise _integrity_error(exc, "Stored release candidate integrity check failed") from exc
    if row is None:
        raise HTTPException(status_code=404, detail="Release candidate not found")
    return row


@router.get("/ifu/release-candidates/{candidate_id}/history")
def get_release_candidate_history(candidate_id: str) -> dict[str, Any]:
    store = ReleaseCandidateStore()
    try:
        if store.get(candidate_id) is None:
            raise HTTPException(status_code=404, detail="Release candidate not found")
    except ValueError as exc:
        raise _integrity_error(exc, "Stored release candidate integrity check failed") from exc
    events = store.history(candidate_id)
    return {"candidate_id": candidate_id, "events": events, "count": len(events)}


@router.post("/ifu/release-candidates/{candidate_id}/decision")
def decide_release_candidate(
    candidate_id: str,
    payload: ReleaseCandidateDecisionPayload,
    x_simqin_user: str | None = Header(default=None, alias="X-SIMQIN-User"),
    x_simqin_role: str | None = Header(default=None, alias="X-SIMQIN-Role"),
) -> dict[str, Any]:
    principal = _release_principal(x_simqin_user, x_simqin_role)
    store = ReleaseCandidateStore()
    try:
        candidate = store.get(candidate_id)
        if candidate is None:
            raise HTTPException(status_code=404, detail="Release candidate not found")
        if principal.user_id == candidate["created_by"]:
            raise HTTPException(status_code=400, detail="Four-eyes rule violation: release candidate creator cannot approve or reject own candidate")
        if payload.decision == "approved":
            validation = validate_candidate_payload(candidate["payload"])
            updated = store.transition(candidate_id, status="approved", changed_by=principal.user_id, comment=payload.comment)
            return {**updated, "validation": validation}
        return store.transition(candidate_id, status="rejected", changed_by=principal.user_id, comment=payload.comment)
    except HTTPException:
        raise
    except (ReleaseTranslationError, ReleaseBuildError, TypeError, ValueError, KeyError) as exc:
        raise _candidate_error(exc) from exc


@router.post("/ifu/releases", status_code=201)
def create_release(
    payload: ReleaseCreatePayload,
    x_simqin_user: str | None = Header(default=None, alias="X-SIMQIN-User"),
    x_simqin_role: str | None = Header(default=None, alias="X-SIMQIN-Role"),
) -> dict[str, Any]:
    principal = _release_principal(x_simqin_user, x_simqin_role)
    candidates = ReleaseCandidateStore()
    try:
        candidate = candidates.get(payload.candidate_id)
        if candidate is None:
            raise HTTPException(status_code=404, detail="Release candidate not found")
        if candidate["status"] != "approved":
            raise HTTPException(status_code=400, detail="Release candidate must be approved before publication")
        release = build_from_candidate_payload(
            candidate["payload"],
            release_id=payload.release_id,
            version=payload.version,
            created_by=principal.user_id,
            candidate_id=candidate["candidate_id"],
            candidate_checksum=candidate["payload_checksum"],
        )
        stored = ReleaseStore().add(release)
        candidates.transition(payload.candidate_id, status="released", changed_by=principal.user_id)
        return stored
    except HTTPException:
        raise
    except (ReleaseTranslationError, ReleaseBuildError, TypeError, ValueError, KeyError) as exc:
        raise _candidate_error(exc) from exc


@router.get("/ifu/releases")
def list_releases() -> dict[str, Any]:
    try:
        releases = ReleaseStore().list()
    except ValueError as exc:
        raise _integrity_error(exc, "Stored release integrity check failed") from exc
    return {"releases": releases, "count": len(releases)}


@router.get("/ifu/releases/{release_id}")
def get_release(release_id: str) -> dict[str, Any]:
    try:
        release = ReleaseStore().get(release_id)
    except ValueError as exc:
        raise _integrity_error(exc, "Stored release integrity check failed") from exc
    if release is None:
        raise HTTPException(status_code=404, detail="Release not found")
    return release
