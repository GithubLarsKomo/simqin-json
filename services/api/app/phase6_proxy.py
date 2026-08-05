"""Gateway proxies for Phase 6 content APIs."""

from __future__ import annotations

import os
from typing import Any

import httpx
from fastapi import APIRouter, HTTPException

from .main import WORKER_BASE_URL


router = APIRouter(prefix="/api/v1", tags=["phase6-content"])
_REVIEWER_ID = os.getenv("SIMQIN_REVIEWER_ID", "").strip()


async def _json_response(response: httpx.Response) -> Any:
    if response.status_code >= 400:
        try:
            payload = response.json()
            detail = payload.get("detail", payload) if isinstance(payload, dict) else payload
        except Exception:
            detail = response.text
        raise HTTPException(status_code=response.status_code, detail=detail)
    return response.json()


@router.get("/content/schemas")
async def phase6_schema_list() -> dict[str, Any]:
    async with httpx.AsyncClient(timeout=30) as client:
        response = await client.get(f"{WORKER_BASE_URL}/api/v1/content/schemas")
    return await _json_response(response)


@router.get("/content/schemas/{schema_name}")
async def phase6_schema(schema_name: str) -> dict[str, Any]:
    async with httpx.AsyncClient(timeout=30) as client:
        response = await client.get(f"{WORKER_BASE_URL}/api/v1/content/schemas/{schema_name}")
    return await _json_response(response)


async def _post(
    path: str,
    body: dict[str, Any],
    *,
    headers: dict[str, str] | None = None,
) -> dict[str, Any]:
    async with httpx.AsyncClient(timeout=30) as client:
        response = await client.post(f"{WORKER_BASE_URL}{path}", json=body, headers=headers)
    return await _json_response(response)


@router.post("/content/graph")
async def phase6_content_graph(body: dict[str, Any]) -> dict[str, Any]:
    return await _post("/api/v1/content/graph", body)


@router.post("/content/validate")
async def phase6_content_validate(body: dict[str, Any]) -> dict[str, Any]:
    return await _post("/api/v1/content/validate", body)


@router.post("/content/resolve")
async def phase6_content_resolve(body: dict[str, Any]) -> dict[str, Any]:
    return await _post("/api/v1/content/resolve", body)


@router.post("/translations/validate")
async def phase6_translation_validate(body: dict[str, Any]) -> dict[str, Any]:
    return await _post("/api/v1/translations/validate", body)


@router.post("/ifu/releases/verify")
async def phase6_release_verify(body: dict[str, Any]) -> dict[str, Any]:
    return await _post("/api/v1/ifu/releases/verify", body)


@router.get("/reviews/migrations/{migration_id}/decisions")
async def phase6_migration_review_decisions(migration_id: str) -> dict[str, Any]:
    async with httpx.AsyncClient(timeout=30) as client:
        response = await client.get(
            f"{WORKER_BASE_URL}/api/v1/reviews/migrations/{migration_id}/decisions"
        )
    return await _json_response(response)


@router.post("/reviews/migrations/{migration_id}/decisions", status_code=201)
async def phase6_create_migration_review_decision(
    migration_id: str,
    body: dict[str, Any],
) -> dict[str, Any]:
    if not _REVIEWER_ID:
        raise HTTPException(status_code=503, detail="SIMQIN_REVIEWER_ID is not configured")
    body = dict(body)
    body.pop("reviewer", None)
    return await _post(
        f"/api/v1/reviews/migrations/{migration_id}/decisions",
        body,
        headers={"X-SIMQIN-Reviewer": _REVIEWER_ID},
    )
