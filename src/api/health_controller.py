# src/api/health_controller.py

from fastapi import APIRouter

from src.integrations.auth_service_client import get_auth_client

router = APIRouter(tags=["Health"])


@router.get("/health")
async def api_health_check():
    """API health check endpoint."""
    try:
        # Check auth service health
        auth_client = await get_auth_client()
        auth_service_healthy = await auth_client.health_check()
    except Exception as e:
        auth_service_healthy = False

    return {
        "status": "ok",
        "service": "ConvrseConnectBackend",
        "auth_service_healthy": auth_service_healthy,
    }
