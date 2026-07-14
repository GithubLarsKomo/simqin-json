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


@app.get("/api/v1/templates/{template_id}")
async def get_template_by_id(template_id: str) -> dict:
    """Proxy: get full template JSON from worker."""
    async with httpx.AsyncClient(timeout=30) as client:
        resp = await client.get(f"{WORKER_BASE_URL}/api/v1/templates/{template_id}")
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


# ---------------------------------------------------------------------------
# Authoring profile endpoints (proxy to worker)
# ---------------------------------------------------------------------------


@app.get("/api/v1/authoring/profiles")
async def get_profiles() -> list[dict]:
    """Proxy: list authoring profiles from worker."""
    async with httpx.AsyncClient(timeout=30) as client:
        resp = await client.get(f"{WORKER_BASE_URL}/api/v1/authoring/profiles")
    if resp.status_code >= 400:
        raise HTTPException(status_code=resp.status_code, detail=resp.text)
    return resp.json()


@app.get("/api/v1/authoring/profiles/{profile_id}")
async def get_profile_by_id(profile_id: str) -> dict:
    """Proxy: get full profile from worker."""
    async with httpx.AsyncClient(timeout=30) as client:
        resp = await client.get(f"{WORKER_BASE_URL}/api/v1/authoring/profiles/{profile_id}")
    if resp.status_code >= 400:
        raise HTTPException(status_code=resp.status_code, detail=resp.text)
    return resp.json()


class AllowedActionsBody(BaseModel):
    profile_id: str
    node_path: str = ""
    block_type: str = ""
    add_context_type: str = ""
    selected_path: str = ""


@app.post("/api/v1/authoring/allowed-actions")
async def allowed_actions(body: AllowedActionsBody) -> dict:
    """Proxy: get allowed actions for a block type / add context."""
    async with httpx.AsyncClient(timeout=30) as client:
        resp = await client.post(
            f"{WORKER_BASE_URL}/api/v1/authoring/allowed-actions",
            json={
                "profile_id": body.profile_id,
                "node_path": body.node_path,
                "block_type": body.block_type,
                "add_context_type": body.add_context_type,
                "selected_path": body.selected_path,
            },
        )
    if resp.status_code >= 400:
        raise HTTPException(status_code=resp.status_code, detail=resp.text)
    return resp.json()

# ---------------------------------------------------------------------------
# Project endpoints (proxy to worker)
# ---------------------------------------------------------------------------


class ProjectNameBody(BaseModel):
    name: str = ""


class ProjectAddDocumentBody(BaseModel):
    project_id: str
    document: dict
    filename: str = ""


class ProjectRemoveDocumentBody(BaseModel):
    project_id: str
    document_id: str


class ProjectRenameDocumentBody(BaseModel):
    project_id: str
    document_id: str
    title: str


class ProjectAddAssetBody(BaseModel):
    project_id: str
    filename: str
    mime: str = "application/octet-stream"
    size: int = 0


class ProjectRemoveAssetBody(BaseModel):
    project_id: str
    asset_id: str


class ProjectUpdateMetadataBody(BaseModel):
    project_id: str
    metadata: dict


class ProjectSetRootBody(BaseModel):
    project_id: str
    document_id: str | None = None


class ProjectSearchBody(BaseModel):
    project_id: str
    query: str


@app.get("/api/v1/projects/new")
async def project_new(name: str = "") -> dict:
    async with httpx.AsyncClient(timeout=30) as client:
        resp = await client.get(f"{WORKER_BASE_URL}/api/v1/projects/new", params={"name": name})
    if resp.status_code >= 400:
        raise HTTPException(status_code=resp.status_code, detail=resp.text)
    return resp.json()


@app.post("/api/v1/projects/open")
async def project_open(body: ProjectNameBody) -> dict:
    async with httpx.AsyncClient(timeout=30) as client:
        resp = await client.post(f"{WORKER_BASE_URL}/api/v1/projects/open", json={"name": body.name})
    if resp.status_code >= 400:
        raise HTTPException(status_code=resp.status_code, detail=resp.text)
    return resp.json()


@app.post("/api/v1/projects/save")
async def project_save(body: ProjectNameBody) -> dict:
    async with httpx.AsyncClient(timeout=30) as client:
        resp = await client.post(f"{WORKER_BASE_URL}/api/v1/projects/save", json={"name": body.name})
    if resp.status_code >= 400:
        raise HTTPException(status_code=resp.status_code, detail=resp.text)
    return resp.json()


@app.post("/api/v1/projects/add-document")
async def project_add_document(body: ProjectAddDocumentBody) -> dict:
    async with httpx.AsyncClient(timeout=30) as client:
        resp = await client.post(f"{WORKER_BASE_URL}/api/v1/projects/add-document", json=body.model_dump())
    if resp.status_code >= 400:
        raise HTTPException(status_code=resp.status_code, detail=resp.text)
    return resp.json()


@app.post("/api/v1/projects/remove-document")
async def project_remove_document(body: ProjectRemoveDocumentBody) -> dict:
    async with httpx.AsyncClient(timeout=30) as client:
        resp = await client.post(f"{WORKER_BASE_URL}/api/v1/projects/remove-document", json=body.model_dump())
    if resp.status_code >= 400:
        raise HTTPException(status_code=resp.status_code, detail=resp.text)
    return resp.json()


@app.post("/api/v1/projects/rename-document")
async def project_rename_document(body: ProjectRenameDocumentBody) -> dict:
    async with httpx.AsyncClient(timeout=30) as client:
        resp = await client.post(f"{WORKER_BASE_URL}/api/v1/projects/rename-document", json=body.model_dump())
    if resp.status_code >= 400:
        raise HTTPException(status_code=resp.status_code, detail=resp.text)
    return resp.json()


@app.post("/api/v1/projects/add-asset")
async def project_add_asset(body: ProjectAddAssetBody) -> dict:
    async with httpx.AsyncClient(timeout=30) as client:
        resp = await client.post(f"{WORKER_BASE_URL}/api/v1/projects/add-asset", json=body.model_dump())
    if resp.status_code >= 400:
        raise HTTPException(status_code=resp.status_code, detail=resp.text)
    return resp.json()


@app.post("/api/v1/projects/remove-asset")
async def project_remove_asset(body: ProjectRemoveAssetBody) -> dict:
    async with httpx.AsyncClient(timeout=30) as client:
        resp = await client.post(f"{WORKER_BASE_URL}/api/v1/projects/remove-asset", json=body.model_dump())
    if resp.status_code >= 400:
        raise HTTPException(status_code=resp.status_code, detail=resp.text)
    return resp.json()


@app.post("/api/v1/projects/update-metadata")
async def project_update_metadata(body: ProjectUpdateMetadataBody) -> dict:
    async with httpx.AsyncClient(timeout=30) as client:
        resp = await client.post(f"{WORKER_BASE_URL}/api/v1/projects/update-metadata", json=body.model_dump())
    if resp.status_code >= 400:
        raise HTTPException(status_code=resp.status_code, detail=resp.text)
    return resp.json()


@app.post("/api/v1/projects/set-root")
async def project_set_root(body: ProjectSetRootBody) -> dict:
    async with httpx.AsyncClient(timeout=30) as client:
        resp = await client.post(f"{WORKER_BASE_URL}/api/v1/projects/set-root", json=body.model_dump())
    if resp.status_code >= 400:
        raise HTTPException(status_code=resp.status_code, detail=resp.text)
    return resp.json()


@app.get("/api/v1/projects/manifest")
async def project_manifest(project_id: str) -> dict:
    async with httpx.AsyncClient(timeout=30) as client:
        resp = await client.get(f"{WORKER_BASE_URL}/api/v1/projects/manifest", params={"project_id": project_id})
    if resp.status_code >= 400:
        raise HTTPException(status_code=resp.status_code, detail=resp.text)
    return resp.json()


@app.post("/api/v1/projects/search")
async def project_search(body: ProjectSearchBody) -> dict:
    async with httpx.AsyncClient(timeout=30) as client:
        resp = await client.post(f"{WORKER_BASE_URL}/api/v1/projects/search", json=body.model_dump())
    if resp.status_code >= 400:
        raise HTTPException(status_code=resp.status_code, detail=resp.text)
    return resp.json()


@app.post("/api/v1/projects/build")
async def project_build(body: ProjectNameBody) -> dict:
    async with httpx.AsyncClient(timeout=30) as client:
        resp = await client.post(f"{WORKER_BASE_URL}/api/v1/projects/build", json={"name": body.name})
    if resp.status_code >= 400:
        raise HTTPException(status_code=resp.status_code, detail=resp.text)
    return resp.json()
