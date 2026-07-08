from __future__ import annotations

import os
from typing import Optional

from fastapi import FastAPI, File, UploadFile
from .parser import convert_xml
from .mapper import MappingProfile

app = FastAPI(title="SIMQIN JSON Worker", version="0.1.0")

# Load default mapping profile at startup
_default_profile: MappingProfile | None = None
_profile_path = MappingProfile.default_profile_path()
if os.path.isfile(_profile_path):
    _default_profile = MappingProfile.from_yaml(_profile_path)


@app.get("/health")
def health() -> dict:
    return {"status": "ok", "service": "worker"}


@app.post("/api/v1/convert")
async def convert(
    file: UploadFile = File(...),
    dtd: UploadFile | None = File(None),
    mapping: UploadFile | None = File(None),
) -> dict:
    xml_bytes = await file.read()
    dtd_bytes = await dtd.read() if dtd else None

    # Use uploaded mapping profile, else fall back to default
    if mapping is not None:
        mapping_bytes = await mapping.read()
        try:
            profile = MappingProfile.from_bytes(mapping_bytes)
        except Exception:
            profile = _default_profile
    else:
        profile = _default_profile

    return convert_xml(
        xml_bytes=xml_bytes,
        filename=file.filename or "document.xml",
        dtd_bytes=dtd_bytes,
        mapping_profile=profile,
    )
