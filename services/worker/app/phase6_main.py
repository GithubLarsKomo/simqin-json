"""Worker entrypoint with the Phase 6 content API mounted.

Use ``uvicorn app.phase6_main:app`` while the legacy worker entrypoint remains
available as ``app.main:app`` for backward compatibility.
"""

from .main import app
from .phase6_api import router as phase6_router


app.include_router(phase6_router)
