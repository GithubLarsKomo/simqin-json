from __future__ import annotations

import json
import os
from typing import Optional

import httpx
from fastapi import FastAPI, File, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

WORKER_BASE_URL = os.getenv("WORKER_BASE_URL", "http://localhost:8090")
MAX_UPLOAD_MB = int(os.getenv("MAX_UPLOAD_MB", "25"))
CORS_ORIGINS = os.getenv("CORS_ORIGINS", '["http://localhost:5173"]')

app = FastAPI(title="SIMQIN JSON API", version="0.1.0")

cors_origins = json.loads(CORS_ORIGINS) if isinstance(CORS_ORIGINS, str) else CORS_ORIGINS

app.add_middleware(
    CORSMiddleware,
    allow_origins=cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ---------------------------------------------------------------------------
# Load JSON schemas for serving
# ---------------------------------------------------------------------------

_SCHEMAS_DIR = os.path.normpath(
    os.path.join(os.path.dirname(__file__), "..", "..", "..", "shared", "schemas")
)


def _load_schema(name: str) -> dict | None:
    path = os.path.join(_SCHEMAS_DIR, name)
    try:
        with open(path, "r", encoding="utf-8") as fh:
            return json.load(fh)
    except (FileNotFoundError, json.JSONDecodeError):
        return None


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------


@app.get("/health")
def health() -> dict:
    return {"status": "ok", "service": "api"}


@app.get("/api/v1/schemas/canonical")
def get_canonical_schema() -> dict:
    schema = _load_schema("canonical-json.schema.json")
    if schema is None:
        raise HTTPException(status_code=404, detail="Canonical schema not found")
    return schema


@app.get("/api/v1/schemas/domain")
def get_domain_schema() -> dict:
    schema = _load_schema("domain-json.schema.json")
    if schema is None:
        raise HTTPException(status_code=404, detail="Domain schema not found")
    return schema


@app.post("/api/v1/documents")
async def upload_document(
    file: UploadFile = File(...),
    dtd: Optional[UploadFile] = File(None),
    mapping: Optional[UploadFile] = File(None),
    mapping_text: Optional[str] = None,
) -> dict:
    # Validate file size
    xml_bytes = await file.read()
    if len(xml_bytes) > MAX_UPLOAD_MB * 1024 * 1024:
        raise HTTPException(status_code=413, detail="File too large")

    # Build multipart payload for the worker
    files = {"file": (file.filename, xml_bytes, file.content_type or "application/xml")}

    if dtd is not None:
        dtd_bytes = await dtd.read()
        files["dtd"] = (dtd.filename, dtd_bytes, dtd.content_type or "application/xml-dtd")

    if mapping is not None:
        mapping_bytes = await mapping.read()
        files["mapping"] = (mapping.filename, mapping_bytes, "application/x-yaml")

    data: dict[str, str] = {}
    if mapping_text and mapping_text.strip():
        data["mapping_text"] = mapping_text

    async with httpx.AsyncClient(timeout=60) as client:
        response = await client.post(
            f"{WORKER_BASE_URL}/api/v1/convert",
            files=files,
            data=data,
        )

    if response.status_code >= 400:
        try:
            detail = response.json().get("detail", response.text)
        except Exception:
            detail = response.text
        raise HTTPException(status_code=response.status_code, detail=detail)

    return response.json()


# ---------------------------------------------------------------------------
# Authoring endpoints (proxy to worker)
# ---------------------------------------------------------------------------


@app.get("/api/v1/templates")
async def get_templates() -> list[dict]:
    """Proxy: list authoring templates from worker."""
    async with httpx.AsyncClient(timeout=30) as client:
        resp = await client.get(f"{WORKER_BASE_URL}/api/v1/templates")
    if resp.status_code >= 400:
        raise HTTPException(status_code=resp.status_code, detail=resp.text)
    return resp.json()


class AuthoringJSONBody(BaseModel):
    document: dict


@app.post("/api/v1/authoring/render-xml")
async def authoring_render_xml(body: AuthoringJSONBody) -> dict:
    """Proxy: render authoring JSON to XML (base64)."""
    async with httpx.AsyncClient(timeout=30) as client:
        resp = await client.post(
            f"{WORKER_BASE_URL}/api/v1/authoring/render-xml",
            json={"document": body.document},
        )
    if resp.status_code >= 400:
        raise HTTPException(status_code=resp.status_code, detail=resp.text)
    return resp.json()


@app.post("/api/v1/authoring/render-json")
async def authoring_render_json(body: AuthoringJSONBody) -> dict:
    """Proxy: render authoring JSON to domain JSON."""
    async with httpx.AsyncClient(timeout=30) as client:
        resp = await client.post(
            f"{WORKER_BASE_URL}/api/v1/authoring/render-json",
            json={"document": body.document},
        )
    if resp.status_code >= 400:
        raise HTTPException(status_code=resp.status_code, detail=resp.text)
    return resp.json()


@app.post("/api/v1/authoring/validate")
async def authoring_validate(body: AuthoringJSONBody) -> dict:
    """Proxy: validate authoring JSON."""
    async with httpx.AsyncClient(timeout=30) as client:
        resp = await client.post(
            f"{WORKER_BASE_URL}/api/v1/authoring/validate",
            json={"document": body.document},
        )
    if resp.status_code >= 400:
        raise HTTPException(status_code=resp.status_code, detail=resp.text)
    return resp.json()
