"""Top-level API routes grouped by health and bounded context."""

from fastapi import APIRouter, Depends

from api.core.router_discovery import mount_discovered_routes
from api.core.security.request_identity import authenticated_identity
from api.health.metrics import router as metrics_router
from api.health.routes import router as health_router

router = APIRouter()
router.include_router(health_router)
router.include_router(metrics_router)
mount_discovered_routes(
    router,
    ["api.identity", "api.platform"],
    prefix="/api/v1",
    dependencies_by_package={"api.identity": [Depends(authenticated_identity)]},
)
