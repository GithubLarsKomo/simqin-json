"""Gateway proxies for Phase 6 content APIs."""

from __future__ import annotations

from typing import Any

import httpx
from fastapi import APIRouter, HTTPException

from .main import WORKER_BASE_URL


router = APIRouter(prefix="/api/v1", tags=["phase6-content"])


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


async def _post(path: str, body: dict[str, Any]) -> dict[str, Any]:
    async with httpx.AsyncClient(timeout=30) as client:
        response = await client.post(f"{WORKER_BASE_URL}{path}", json=body)
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
