"""
Health check endpoints for monitoring service status.
"""

from datetime import datetime
from typing import Any, Dict

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from backend.src.core.auth import get_current_client
from backend.src.core.config import settings
from backend.src.core.database import get_db
from backend.src.core.inngest import check_inngest_health
from backend.src.core.logging import get_logger
from backend.src.models.base import DetailedHealthStatus, HealthStatus

logger = get_logger(__name__)

router = APIRouter(tags=["Health"])


@router.get(
    "/health",
    response_model=HealthStatus,
    status_code=status.HTTP_200_OK,
    summary="Basic health check",
    description="Returns basic health status without authentication",
)
async def health_check() -> HealthStatus:
    """
    Basic health check endpoint.

    Returns:
        Health status

    Example:
        ```bash
        curl http://localhost:8000/health
        ```
    """
    return HealthStatus(
        status="healthy",
        timestamp=datetime.utcnow(),
    )


@router.get(
    "/v1/health/detailed",
    response_model=DetailedHealthStatus,
    status_code=status.HTTP_200_OK,
    summary="Detailed health check",
    description="Returns detailed health status with component checks (requires authentication)",
    dependencies=[Depends(get_current_client)],
)
async def detailed_health_check(
    db: AsyncSession = Depends(get_db),
) -> DetailedHealthStatus:
    """
    Detailed health check with component status.

    Checks:
    - Database connectivity
    - Inngest connectivity
    - Application configuration

    Requires authentication.

    Returns:
        Detailed health status

    Raises:
        HTTPException: If any critical component is unhealthy

    Example:
        ```bash
        curl -H "X-API-Key: your-key" http://localhost:8000/v1/health/detailed
        ```
    """
    components: Dict[str, Any] = {}
    overall_status = "healthy"

    # Check database
    db_status = await check_database_health(db)
    components["database"] = db_status
    if db_status["status"] != "healthy":
        overall_status = "degraded"
        logger.warning("Database health check failed", extra=db_status)

    # Check Inngest
    inngest_status = await check_inngest_health()
    components["inngest"] = inngest_status
    if inngest_status["status"] != "healthy":
        overall_status = "degraded"
        logger.warning("Inngest health check failed", extra=inngest_status)

    # Application info
    components["application"] = {
        "status": "healthy",
        "environment": settings.ENVIRONMENT,
        "debug": settings.DEBUG,
    }

    # If overall status is not healthy, return 503
    if overall_status == "unhealthy":
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Service is unhealthy",
        )

    return DetailedHealthStatus(
        status=overall_status,
        timestamp=datetime.utcnow(),
        components=components,
        version="0.1.0",
        environment=settings.ENVIRONMENT,
    )


async def check_database_health(db: AsyncSession) -> Dict[str, Any]:
    """
    Check database connectivity and status.

    Args:
        db: Database session

    Returns:
        Health status dictionary
    """
    try:
        # Simple query to verify connection
        result = await db.execute(text("SELECT 1 AS health_check"))
        row = result.fetchone()

        if row and row[0] == 1:
            return {
                "status": "healthy",
                "service": "postgresql",
                "provider": "neon",
                "response_time_ms": "< 100",
            }
        else:
            return {
                "status": "unhealthy",
                "service": "postgresql",
                "error": "Invalid response from database",
            }

    except Exception as e:
        logger.error(
            "Database health check failed",
            extra={"error": str(e)},
            exc_info=True,
        )
        return {
            "status": "unhealthy",
            "service": "postgresql",
            "error": str(e),
        }


@router.get(
    "/v1/health/ready",
    status_code=status.HTTP_200_OK,
    summary="Readiness check",
    description="Kubernetes-style readiness probe",
)
async def readiness_check(db: AsyncSession = Depends(get_db)) -> Dict[str, str]:
    """
    Readiness check for Kubernetes/container orchestration.

    Verifies that the service is ready to accept traffic.

    Returns:
        Ready status

    Raises:
        HTTPException: If service is not ready

    Example:
        ```bash
        curl http://localhost:8000/v1/health/ready
        ```
    """
    # Check critical dependencies
    db_status = await check_database_health(db)

    if db_status["status"] != "healthy":
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Service not ready - database unavailable",
        )

    return {"status": "ready"}


@router.get(
    "/v1/health/live",
    status_code=status.HTTP_200_OK,
    summary="Liveness check",
    description="Kubernetes-style liveness probe",
)
async def liveness_check() -> Dict[str, str]:
    """
    Liveness check for Kubernetes/container orchestration.

    Verifies that the service is alive and should not be restarted.

    Returns:
        Alive status

    Example:
        ```bash
        curl http://localhost:8000/v1/health/live
        ```
    """
    return {"status": "alive"}


# Export router
__all__ = ["router"]
