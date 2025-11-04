"""
Authentication and authorization API endpoints.

Includes webhook secret rotation and other auth-related operations.
"""

import secrets
from datetime import datetime, timedelta

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from backend.src.api.schemas.auth_schemas import (
    WebhookSecretRotationRequest,
    WebhookSecretRotationResponse,
)
from backend.src.core.auth import AuthenticatedClient, get_current_client, require_write
from backend.src.core.database import get_db
from backend.src.core.logging import get_logger
from backend.src.models.client import Client

logger = get_logger(__name__)

router = APIRouter(prefix="/v1/auth", tags=["Authentication"])


@router.post(
    "/webhook-secret",
    response_model=WebhookSecretRotationResponse,
    status_code=status.HTTP_200_OK,
    summary="Rotate webhook secret",
    dependencies=[Depends(require_write)],
)
async def rotate_webhook_secret(
    request: WebhookSecretRotationRequest,
    client: AuthenticatedClient = Depends(get_current_client),
    db: AsyncSession = Depends(get_db),
) -> WebhookSecretRotationResponse:
    """
    Rotate webhook secret with 1-hour grace period.

    This endpoint generates a new webhook secret and keeps the previous
    secret valid for 1 hour to allow gradual migration of webhook receivers.

    During the grace period (1 hour), both the old and new secrets will
    verify webhook signatures successfully.

    **Important**: The new secret is returned only once. Save it securely!

    **Migration Process**:
    1. Call this endpoint to generate new secret
    2. Update webhook receiver with new secret
    3. Test webhook receiver with test endpoint
    4. Old secret expires automatically after 1 hour

    Example:
        ```bash
        curl -X POST http://localhost:8000/v1/auth/webhook-secret \\
          -H "X-API-Key: your-api-key" \\
          -H "Content-Type: application/json" \\
          -d '{}'
        ```

    Returns:
        New webhook secret and expiration time for old secret
    """
    try:
        # Fetch client
        client_record = await db.get(Client, client.client_id)

        if not client_record:
            logger.error(
                "Client not found during webhook secret rotation",
                extra={"client_id": str(client.client_id)},
            )
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Client not found",
            )

        # Generate new webhook secret
        new_secret = secrets.token_urlsafe(48)  # 64 characters base64url

        # Move current secret to previous
        client_record.webhook_secret_previous = client_record.webhook_secret_current
        client_record.webhook_secret_current = new_secret

        # Set expiration for previous secret (1 hour grace period)
        expiration_time = datetime.utcnow() + timedelta(hours=1)
        client_record.secret_rotation_expires_at = expiration_time

        # Update timestamp
        client_record.updated_at = datetime.utcnow()

        await db.commit()

        logger.info(
            "Webhook secret rotated successfully",
            extra={
                "client_id": str(client.client_id),
                "expiration_time": expiration_time.isoformat(),
            },
        )

        return WebhookSecretRotationResponse(
            new_secret=new_secret,
            previous_secret_expires_at=expiration_time,
            rotation_timestamp=datetime.utcnow(),
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(
            "Webhook secret rotation failed",
            extra={
                "client_id": str(client.client_id),
                "error": str(e),
            },
            exc_info=True,
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to rotate webhook secret",
        )


# Export router
__all__ = ["router"]
