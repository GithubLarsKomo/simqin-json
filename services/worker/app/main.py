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


@app.post("/api/v1/authoring/allowed-actions")
def allowed_actions(req: AllowedActionsRequest) -> dict:
    """Return allowed actions for a node path or block type within a profile.

    The caller may supply either:
    - ``node_path`` (legacy dot-separated path), or
    - ``block_type`` (semantic type like ``"section"``, ``"paragraph"``).

    When both are provided, ``block_type`` takes precedence for parent
    lookups.
    """
    try:
        return get_allowed_actions(
            req.profile_id,
            node_path=req.node_path,
            block_type=req.block_type,
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
