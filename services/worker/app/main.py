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
    use_mapping: bool = True,
) -> dict:
    xml_bytes = await file.read()
    dtd_bytes = await dtd.read() if dtd else None
    profile = _default_profile if use_mapping else None
    return convert_xml(
        xml_bytes=xml_bytes,
        filename=file.filename or "document.xml",
        dtd_bytes=dtd_bytes,
        mapping_profile=profile,
    )
