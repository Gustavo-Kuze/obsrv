"""
Authentication and authorization schemas.

Request/response models for webhook secret rotation and other auth operations.
"""

from datetime import datetime
from typing import Optional
from uuid import UUID

from pydantic import BaseModel, Field


class WebhookSecretRotationRequest(BaseModel):
    """
    Request to rotate webhook secret.

    The new secret will be generated automatically. The previous secret
    remains valid for 1 hour to allow gradual migration.
    """

    pass  # No input required - secret is generated server-side


class WebhookSecretRotationResponse(BaseModel):
    """
    Response after webhook secret rotation.

    Contains the new secret (shown once) and expiration time for old secret.
    """

    new_secret: str = Field(
        ...,
        description="New webhook secret (save this - won't be shown again)",
        min_length=64,
        max_length=64,
    )
    previous_secret_expires_at: datetime = Field(
        ...,
        description="When the previous secret will stop working (1 hour grace period)",
    )
    rotation_timestamp: datetime = Field(
        ...,
        description="When rotation occurred",
    )

    model_config = {
        "json_schema_extra": {
            "example": {
                "new_secret": "wh_sec_" + "x" * 57,
                "previous_secret_expires_at": "2025-11-03T15:00:00Z",
                "rotation_timestamp": "2025-11-03T14:00:00Z",
            }
        }
    }


# Export
__all__ = [
    "WebhookSecretRotationRequest",
    "WebhookSecretRotationResponse",
]
