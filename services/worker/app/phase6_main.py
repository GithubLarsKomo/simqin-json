"""Worker entrypoint with the Phase 6 content API mounted.

Use ``uvicorn app.phase6_main:app`` while the legacy worker entrypoint remains
available as ``app.main:app`` for backward compatibility.
"""

from .main import app
from .phase6_api import router as phase6_router
from .phase6_canonical_content_api import router as phase6_canonical_content_router
from .phase6_configuration_api import router as phase6_configuration_router
from .phase6_release_api import router as phase6_release_router
from .phase6_ruleset_api import router as phase6_ruleset_router
from .phase6_terminology_api import router as phase6_terminology_router
from .phase6_translation_store_api import router as phase6_translation_store_router


app.include_router(phase6_router)
app.include_router(phase6_canonical_content_router)
app.include_router(phase6_configuration_router)
app.include_router(phase6_ruleset_router)
app.include_router(phase6_terminology_router)
app.include_router(phase6_release_router)
app.include_router(phase6_translation_store_router)
