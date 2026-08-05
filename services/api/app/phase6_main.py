"""API gateway entry point with additive Phase 6 routes."""

from .main import app
from .phase6_proxy import router as phase6_router

app.include_router(phase6_router)
