from __future__ import annotations

import os
from typing import Optional

import httpx
from fastapi import FastAPI, File, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware

WORKER_BASE_URL = os.getenv("WORKER_BASE_URL", "http://localhost:8090")
MAX_UPLOAD_MB = int(os.getenv("MAX_UPLOAD_MB", "25"))
CORS_ORIGINS = os.getenv("CORS_ORIGINS", '["http://localhost:5173"]')

app = FastAPI(title="SIMQIN JSON API", version="0.1.0")

import json
cors_origins = json.loads(CORS_ORIGINS) if isinstance(CORS_ORIGINS, str) else CORS_ORIGINS

app.add_middleware(
    CORSMiddleware,
    allow_origins=cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/health")
def health() -> dict:
    return {"status": "ok", "service": "api"}


@app.post("/api/v1/documents")
async def upload_document(
    file: UploadFile = File(...),
    dtd: Optional[UploadFile] = File(None),
) -> dict:
    xml_bytes = await file.read()
    if len(xml_bytes) > MAX_UPLOAD_MB * 1024 * 1024:
        raise HTTPException(status_code=413, detail="File too large")

    files = {"file": (file.filename, xml_bytes, file.content_type or "application/xml")}
    if dtd is not None:
        dtd_bytes = await dtd.read()
        files["dtd"] = (dtd.filename, dtd_bytes, dtd.content_type or "application/xml-dtd")

    async with httpx.AsyncClient(timeout=60) as client:
        response = await client.post(f"{WORKER_BASE_URL}/api/v1/convert", files=files)

    if response.status_code >= 400:
        raise HTTPException(status_code=response.status_code, detail=response.text)

    return response.json()
