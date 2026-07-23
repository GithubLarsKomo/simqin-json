from __future__ import annotations

import os
from typing import Any, Optional

from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from pydantic import BaseModel

from .parser import convert_xml
from .mapper import MappingProfile, MappingValidationError
from .authoring import AuthoringDoc, AuthoringValidationError
from .templates import list_templates, get_template, create_document
from .profiles import list_profiles, get_profile, get_allowed_actions, validate_with_profile
from .xml_writer import render_document_xml, render_document_json
from .project import Project, ProjectService, ProjectAsset, build_check, SCHEMA_VERSION
from .build_graph import BuildGraph
from .project_index import ProjectIndex
from .reference_resolver import ReferenceResolver
from .validation import validate_project
from .publish import publish_project, PackageManifest

# ---------------------------------------------------------------------------
# App
# ---------------------------------------------------------------------------

app = FastAPI(title="SIMQIN JSON Worker", version="0.1.0")

# Load default mapping profile at startup
_default_profile: MappingProfile | None = None
_profile_path = MappingProfile.default_profile_path()
if os.path.isfile(_profile_path):
    _default_profile = MappingProfile.from_yaml(_profile_path)


# ---------------------------------------------------------------------------
# Pydantic models
# ---------------------------------------------------------------------------


class AuthoringRequest(BaseModel):
    document: dict[str, Any]


# ---------------------------------------------------------------------------
# Health
# ---------------------------------------------------------------------------


@app.get("/health")
def health() -> dict:
    return {"status": "ok", "service": "worker"}


# ---------------------------------------------------------------------------
# Convert (existing)
# ---------------------------------------------------------------------------


@app.post("/api/v1/convert")
async def convert(
    file: UploadFile = File(...),
    dtd: UploadFile | None = File(None),
    mapping: UploadFile | None = File(None),
    mapping_text: Optional[str] = Form(None),
) -> dict:
    xml_bytes = await file.read()
    dtd_bytes = await dtd.read() if dtd else None

    # Determine mapping profile: textarea > file > default
    if mapping_text and mapping_text.strip():
        try:
            profile = MappingProfile.from_bytes(mapping_text.encode("utf-8"))
        except MappingValidationError as exc:
            raise HTTPException(status_code=400, detail=str(exc))
    elif mapping is not None:
        mapping_bytes = await mapping.read()
        if mapping_bytes.strip():
            try:
                profile = MappingProfile.from_bytes(mapping_bytes)
            except MappingValidationError as exc:
                raise HTTPException(status_code=400, detail=str(exc))
        else:
            raise HTTPException(status_code=400, detail="Empty mapping YAML file")
    else:
        profile = _default_profile

    return convert_xml(
        xml_bytes=xml_bytes,
        filename=file.filename or "document.xml",
        dtd_bytes=dtd_bytes,
        mapping_profile=profile,
    )


# ---------------------------------------------------------------------------
# Authoring endpoints
# ---------------------------------------------------------------------------


@app.get("/api/v1/templates")
def get_templates() -> list[dict]:
    """Return all available authoring templates."""
    return list_templates()


@app.get("/api/v1/templates/{template_id}")
def get_template_by_id(template_id: str) -> dict:
    """Return the full AuthoringDoc JSON for a given template."""
    try:
        return get_template(template_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc))


@app.post("/api/v1/authoring/render-xml")
def render_xml(req: AuthoringRequest) -> dict:
    """Render an Authoring JSON document to XML bytes (base64-encoded)."""
    import base64
    try:
        doc = AuthoringDoc.from_dict(req.document)
        xml_bytes = render_document_xml(doc)
        return {"xml_base64": base64.b64encode(xml_bytes).decode("utf-8")}
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@app.post("/api/v1/authoring/render-json")
def render_json(req: AuthoringRequest) -> dict:
    """Render an Authoring JSON document to domain JSON."""
    try:
        doc = AuthoringDoc.from_dict(req.document)
        domain_json = render_document_json(doc)
        return {"domain_json": domain_json}
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc))


# ---------------------------------------------------------------------------
# Authoring profile endpoints
# ---------------------------------------------------------------------------


@app.get("/api/v1/authoring/profiles")
def get_profiles() -> list[dict]:
    """Return all available authoring profiles."""
    return list_profiles()


@app.get("/api/v1/authoring/profiles/{profile_id}")
def get_profile_by_id(profile_id: str) -> dict:
    """Return the full profile for a given profile ID."""
    try:
        return get_profile(profile_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc))


class AllowedActionsRequest(BaseModel):
    profile_id: str
    node_path: str = ""
    block_type: str = ""
    add_context_type: str = ""
    selected_path: str = ""


@app.post("/api/v1/authoring/allowed-actions")
def allowed_actions(req: AllowedActionsRequest) -> dict:
    """Return allowed actions for a node path or block type within a profile.

    The caller should supply:
    - ``profile_id``
    - ``block_type`` — the semantic type of the selected node
    - ``add_context_type`` — the semantic parent type for add actions

    Legacy ``node_path`` is still accepted for backward compatibility.
    """
    try:
        return get_allowed_actions(
            req.profile_id,
            node_path=req.node_path,
            block_type=req.block_type,
            add_context_type=req.add_context_type,
            selected_path=req.selected_path,
        )
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc))


# ---------------------------------------------------------------------------
# Updated authoring validation (profile-aware)
# ---------------------------------------------------------------------------


class AuthoringValidateWithProfileRequest(BaseModel):
    document: dict[str, Any]
    profile_id: str | None = None


@app.post("/api/v1/authoring/validate")
def validate_authoring(req: AuthoringValidateWithProfileRequest) -> dict:
    """Validate an Authoring JSON document using its profile.

    Falls back to the document's own 'template' field if no profile_id
    is given.
    """
    try:
        pid = req.profile_id or req.document.get("template", "dita-topic")
        errors = validate_with_profile(req.document, pid)
        return {"valid": len(errors) == 0, "errors": errors}
    except Exception as exc:
        return {"valid": False, "errors": [str(exc)]}


# ---------------------------------------------------------------------------
# Project service (singleton)
# ---------------------------------------------------------------------------

_proj_service = ProjectService()

# ---------------------------------------------------------------------------
# Pydantic models for project endpoints
# ---------------------------------------------------------------------------


class ProjectCreateRequest(BaseModel):
    name: str = ""


class ProjectAddDocumentRequest(BaseModel):
    project_id: str
    document: dict[str, Any]
    filename: str = ""


class ProjectRemoveDocumentRequest(BaseModel):
    project_id: str
    document_id: str


class ProjectRenameDocumentRequest(BaseModel):
    project_id: str
    document_id: str
    title: str


class ProjectAddAssetRequest(BaseModel):
    project_id: str
    filename: str
    mime: str = "application/octet-stream"
    size: int = 0


class ProjectRemoveAssetRequest(BaseModel):
    project_id: str
    asset_id: str


class ProjectUpdateMetadataRequest(BaseModel):
    project_id: str
    metadata: dict[str, Any]


class ProjectSetRootRequest(BaseModel):
    project_id: str
    document_id: str | None = None


class ProjectSearchRequest(BaseModel):
    project_id: str
    query: str


# ---------------------------------------------------------------------------
# Project endpoints
# ---------------------------------------------------------------------------


@app.get("/api/v1/projects/new")
def project_new(name: str = "") -> dict:
    p = _proj_service.create_project(name)
    return {"ok": True, "project": p.to_dict()}


@app.post("/api/v1/projects/open")
def project_open(req: ProjectCreateRequest) -> dict:
    p = _proj_service.open_project(req.name)
    return {"ok": True, "project": p.to_dict()}


@app.post("/api/v1/projects/save")
def project_save(req: ProjectCreateRequest) -> dict:
    return _proj_service.save_project(req.name)


@app.post("/api/v1/projects/add-document")
def project_add_document(req: ProjectAddDocumentRequest) -> dict:
    p = _proj_service.get_project(req.project_id)
    if not p:
        raise HTTPException(status_code=404, detail="Project not found")
    try:
        doc = AuthoringDoc.from_dict(req.document)
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    doc_id = p.add_document(doc, filename=req.filename)
    return {"ok": True, "document_id": doc_id, "project": p.to_dict()}


@app.post("/api/v1/projects/remove-document")
def project_remove_document(req: ProjectRemoveDocumentRequest) -> dict:
    p = _proj_service.get_project(req.project_id)
    if not p:
        raise HTTPException(status_code=404, detail="Project not found")
    ok = p.remove_document(req.document_id)
    return {"ok": ok, "project": p.to_dict()}


@app.post("/api/v1/projects/rename-document")
def project_rename_document(req: ProjectRenameDocumentRequest) -> dict:
    p = _proj_service.get_project(req.project_id)
    if not p:
        raise HTTPException(status_code=404, detail="Project not found")
    ok = p.rename_document(req.document_id, req.title)
    return {"ok": ok, "project": p.to_dict()}


@app.post("/api/v1/projects/add-asset")
def project_add_asset(req: ProjectAddAssetRequest) -> dict:
    p = _proj_service.get_project(req.project_id)
    if not p:
        raise HTTPException(status_code=404, detail="Project not found")
    asset = ProjectAsset(filename=req.filename, mime=req.mime, size=req.size)
    p.add_asset(asset)
    return {"ok": True, "asset_id": asset.id, "project": p.to_dict()}


@app.post("/api/v1/projects/remove-asset")
def project_remove_asset(req: ProjectRemoveAssetRequest) -> dict:
    p = _proj_service.get_project(req.project_id)
    if not p:
        raise HTTPException(status_code=404, detail="Project not found")
    ok = p.remove_asset(req.asset_id)
    return {"ok": ok, "project": p.to_dict()}


@app.post("/api/v1/projects/update-metadata")
def project_update_metadata(req: ProjectUpdateMetadataRequest) -> dict:
    p = _proj_service.get_project(req.project_id)
    if not p:
        raise HTTPException(status_code=404, detail="Project not found")
    p.update_metadata(req.metadata)
    return {"ok": True, "project": p.to_dict()}


@app.post("/api/v1/projects/set-root")
def project_set_root(req: ProjectSetRootRequest) -> dict:
    p = _proj_service.get_project(req.project_id)
    if not p:
        raise HTTPException(status_code=404, detail="Project not found")
    p.set_root_document(req.document_id)
    return {"ok": True, "project": p.to_dict()}


@app.get("/api/v1/projects/manifest")
def project_manifest(project_id: str) -> dict:
    p = _proj_service.get_project(project_id)
    if not p:
        raise HTTPException(status_code=404, detail="Project not found")
    return {"ok": True, "manifest": p.manifest()}


@app.post("/api/v1/projects/search")
def project_search(req: ProjectSearchRequest) -> dict:
    p = _proj_service.get_project(req.project_id)
    if not p:
        raise HTTPException(status_code=404, detail="Project not found")
    return {"ok": True, "results": p.search(req.query)}


@app.post("/api/v1/projects/build")
def project_build(req: ProjectCreateRequest) -> dict:
    p = _proj_service.get_project(req.name)
    if not p:
        raise HTTPException(status_code=404, detail="Project not found")
    return {"ok": True, "report": build_check(p)}


# ---------------------------------------------------------------------------
# Phase 5 — Publishing Engine endpoints
# ---------------------------------------------------------------------------


@app.post("/api/v1/projects/graph")
def project_graph(req: ProjectCreateRequest) -> dict:
    p = _proj_service.get_project(req.name)
    if not p:
        raise HTTPException(status_code=404, detail="Project not found")
    graph = BuildGraph.from_project(p)
    report = graph.full_report(p)
    return {"ok": True, "report": report}


@app.post("/api/v1/projects/index")
def project_index(req: ProjectCreateRequest) -> dict:
    p = _proj_service.get_project(req.name)
    if not p:
        raise HTTPException(status_code=404, detail="Project not found")
    idx = ProjectIndex(p)
    return {"ok": True, "entries": idx.all_entries(), "count": idx.count()}


@app.post("/api/v1/projects/resolve")
def project_resolve(req: ProjectCreateRequest) -> dict:
    p = _proj_service.get_project(req.name)
    if not p:
        raise HTTPException(status_code=404, detail="Project not found")
    resolver = ReferenceResolver(p)
    refs = resolver.resolve_all()
    return {"ok": True, "references": refs}


@app.post("/api/v1/projects/validate")
def project_validate(req: ProjectCreateRequest) -> dict:
    p = _proj_service.get_project(req.name)
    if not p:
        raise HTTPException(status_code=404, detail="Project not found")
    result = validate_project(p)
    return {"ok": True, **result.to_dict()}


@app.post("/api/v1/projects/publish")
def project_publish(req: ProjectCreateRequest) -> dict:
    p = _proj_service.get_project(req.name)
    if not p:
        raise HTTPException(status_code=404, detail="Project not found")
    result = publish_project(p)
    return {"ok": True, **result.to_dict()}


@app.post("/api/v1/projects/package-manifest")
def project_package_manifest(req: ProjectCreateRequest) -> dict:
    p = _proj_service.get_project(req.name)
    if not p:
        raise HTTPException(status_code=404, detail="Project not found")
    manifest = PackageManifest.from_project(p)
    return {"ok": True, "manifest": manifest.to_dict()}
