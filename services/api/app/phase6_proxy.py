"""Gateway proxies for Phase 6 content APIs."""

from __future__ import annotations

import os
from typing import Any

import httpx
from fastapi import APIRouter, HTTPException, Query

from .main import WORKER_BASE_URL


router = APIRouter(prefix="/api/v1", tags=["phase6-content"])
_USER_ID = (os.getenv("SIMQIN_USER_ID") or os.getenv("SIMQIN_REVIEWER_ID") or "").strip()
_ROLE = os.getenv("SIMQIN_ROLE", "").strip().lower()


async def _json_response(response: httpx.Response) -> Any:
    if response.status_code >= 400:
        try:
            payload = response.json()
            detail = payload.get("detail", payload) if isinstance(payload, dict) else payload
        except Exception:
            detail = response.text
        raise HTTPException(status_code=response.status_code, detail=detail)
    return response.json()


def _worker_unavailable(exc: httpx.RequestError) -> HTTPException:
    return HTTPException(
        status_code=503,
        detail={"message": "Phase 6 worker is unavailable", "reason": str(exc)},
    )


def _trusted_headers() -> dict[str, str]:
    if not _USER_ID:
        raise HTTPException(status_code=503, detail="SIMQIN_USER_ID is not configured")
    if _ROLE not in {"author", "reviewer", "approver"}:
        raise HTTPException(status_code=503, detail="SIMQIN_ROLE must be author, reviewer or approver")
    return {"X-SIMQIN-User": _USER_ID, "X-SIMQIN-Role": _ROLE}


@router.get("/session")
async def phase6_session() -> dict[str, str]:
    headers = _trusted_headers()
    return {"user_id": headers["X-SIMQIN-User"], "role": headers["X-SIMQIN-Role"]}


async def _get(path: str, *, params: dict[str, Any] | None = None) -> dict[str, Any]:
    try:
        async with httpx.AsyncClient(timeout=30) as client:
            response = await client.get(f"{WORKER_BASE_URL}{path}", params=params)
    except httpx.RequestError as exc:
        raise _worker_unavailable(exc) from exc
    return await _json_response(response)


async def _post(path: str, body: dict[str, Any], *, headers: dict[str, str] | None = None) -> dict[str, Any]:
    try:
        async with httpx.AsyncClient(timeout=30) as client:
            response = await client.post(f"{WORKER_BASE_URL}{path}", json=body, headers=headers)
    except httpx.RequestError as exc:
        raise _worker_unavailable(exc) from exc
    return await _json_response(response)


@router.get("/content/schemas")
async def phase6_schema_list() -> dict[str, Any]:
    return await _get("/api/v1/content/schemas")


@router.get("/content/schemas/{schema_name}")
async def phase6_schema(schema_name: str) -> dict[str, Any]:
    return await _get(f"/api/v1/content/schemas/{schema_name}")


@router.post("/content/graph")
async def phase6_content_graph(body: dict[str, Any]) -> dict[str, Any]:
    return await _post("/api/v1/content/graph", body)


@router.post("/content/validate")
async def phase6_content_validate(body: dict[str, Any]) -> dict[str, Any]:
    return await _post("/api/v1/content/validate", body)


@router.post("/content/resolve")
async def phase6_content_resolve(body: dict[str, Any]) -> dict[str, Any]:
    return await _post("/api/v1/content/resolve", body)


@router.post("/content/canonical-snapshots", status_code=201)
async def phase6_create_canonical_snapshot(body: dict[str, Any]) -> dict[str, Any]:
    return await _post("/api/v1/content/canonical-snapshots", body, headers=_trusted_headers())


@router.get("/content/canonical-snapshots")
async def phase6_list_canonical_snapshots() -> dict[str, Any]:
    return await _get("/api/v1/content/canonical-snapshots")


@router.get("/content/canonical-snapshots/{object_id}/{revision}")
async def phase6_get_canonical_snapshot(object_id: str, revision: int) -> dict[str, Any]:
    return await _get(f"/api/v1/content/canonical-snapshots/{object_id}/{revision}")


@router.post("/configuration/parameters", status_code=201)
async def phase6_register_configuration_parameter(body: dict[str, Any]) -> dict[str, Any]:
    return await _post("/api/v1/configuration/parameters", body, headers=_trusted_headers())


@router.get("/configuration/parameters")
async def phase6_list_configuration_parameters() -> dict[str, Any]:
    return await _get("/api/v1/configuration/parameters")


@router.get("/configuration/parameters/{parameter_id}/{revision}")
async def phase6_get_configuration_parameter(parameter_id: str, revision: int) -> dict[str, Any]:
    return await _get(f"/api/v1/configuration/parameters/{parameter_id}/{revision}")


@router.post("/translations/validate")
async def phase6_translation_validate(body: dict[str, Any]) -> dict[str, Any]:
    return await _post("/api/v1/translations/validate", body)


@router.post("/translations/variants", status_code=201)
async def phase6_create_translation_variant(body: dict[str, Any]) -> dict[str, Any]:
    return await _post("/api/v1/translations/variants", body, headers=_trusted_headers())


@router.get("/translations/variants")
async def phase6_list_translation_variants(
    content_object_id: str = Query(default=""),
    canonical_revision: int | None = Query(default=None, ge=1),
    target_language: str = Query(default=""),
    status: str = Query(default=""),
) -> dict[str, Any]:
    params: dict[str, Any] = {}
    if content_object_id:
        params["content_object_id"] = content_object_id
    if canonical_revision is not None:
        params["canonical_revision"] = canonical_revision
    if target_language:
        params["target_language"] = target_language
    if status:
        params["status"] = status
    return await _get("/api/v1/translations/variants", params=params)


@router.get("/translations/variants/{variant_id}/{revision}")
async def phase6_get_translation_variant(variant_id: str, revision: int) -> dict[str, Any]:
    return await _get(f"/api/v1/translations/variants/{variant_id}/{revision}")


@router.get("/translations/variants/{variant_id}/{revision}/history")
async def phase6_get_translation_history(variant_id: str, revision: int) -> dict[str, Any]:
    return await _get(f"/api/v1/translations/variants/{variant_id}/{revision}/history")


@router.post("/translations/variants/{variant_id}/{revision}/status")
async def phase6_transition_translation_status(variant_id: str, revision: int, body: dict[str, Any]) -> dict[str, Any]:
    return await _post(
        f"/api/v1/translations/variants/{variant_id}/{revision}/status",
        body,
        headers=_trusted_headers(),
    )


@router.post("/ifu/releases/verify")
async def phase6_release_verify(body: dict[str, Any]) -> dict[str, Any]:
    return await _post("/api/v1/ifu/releases/verify", body, headers=_trusted_headers())


@router.post("/ifu/release-candidates", status_code=201)
async def phase6_create_release_candidate(body: dict[str, Any]) -> dict[str, Any]:
    return await _post("/api/v1/ifu/release-candidates", body, headers=_trusted_headers())


@router.get("/ifu/release-candidates")
async def phase6_list_release_candidates() -> dict[str, Any]:
    return await _get("/api/v1/ifu/release-candidates")


@router.get("/ifu/release-candidates/{candidate_id}")
async def phase6_get_release_candidate(candidate_id: str) -> dict[str, Any]:
    return await _get(f"/api/v1/ifu/release-candidates/{candidate_id}")


@router.get("/ifu/release-candidates/{candidate_id}/history")
async def phase6_get_release_candidate_history(candidate_id: str) -> dict[str, Any]:
    return await _get(f"/api/v1/ifu/release-candidates/{candidate_id}/history")


@router.post("/ifu/release-candidates/{candidate_id}/decision")
async def phase6_decide_release_candidate(candidate_id: str, body: dict[str, Any]) -> dict[str, Any]:
    return await _post(
        f"/api/v1/ifu/release-candidates/{candidate_id}/decision",
        body,
        headers=_trusted_headers(),
    )


@router.post("/ifu/releases", status_code=201)
async def phase6_create_release(body: dict[str, Any]) -> dict[str, Any]:
    return await _post("/api/v1/ifu/releases", body, headers=_trusted_headers())


@router.get("/ifu/releases")
async def phase6_list_releases() -> dict[str, Any]:
    return await _get("/api/v1/ifu/releases")


@router.get("/ifu/releases/{release_id}")
async def phase6_get_release(release_id: str) -> dict[str, Any]:
    return await _get(f"/api/v1/ifu/releases/{release_id}")


@router.get("/reviews/migrations/{migration_id}/decisions")
async def phase6_migration_review_decisions(migration_id: str) -> dict[str, Any]:
    return await _get(f"/api/v1/reviews/migrations/{migration_id}/decisions")


@router.post("/reviews/migrations/{migration_id}/decisions", status_code=201)
async def phase6_create_migration_review_decision(migration_id: str, body: dict[str, Any]) -> dict[str, Any]:
    body = dict(body)
    body.pop("reviewer", None)
    body.pop("role", None)
    return await _post(
        f"/api/v1/reviews/migrations/{migration_id}/decisions",
        body,
        headers=_trusted_headers(),
    )
