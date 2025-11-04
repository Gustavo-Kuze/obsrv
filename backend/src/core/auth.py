"""
API key authentication middleware with bcrypt verification and rate limiting.
"""

import time
from collections import defaultdict
from datetime import datetime, timedelta
from typing import Dict, Optional, Tuple
from uuid import UUID

import bcrypt
from fastapi import Depends, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from backend.src.core.database import get_db
from backend.src.core.exceptions import (
    AuthenticationError,
    AuthorizationError,
    InvalidAPIKeyError,
    RateLimitExceededError,
)
from backend.src.core.logging import get_logger

logger = get_logger(__name__)

# Security scheme
security = HTTPBearer(auto_error=False)

# In-memory rate limiting storage (should be Redis in production)
_rate_limit_storage: Dict[str, list] = defaultdict(list)


class AuthenticatedClient:
    """Represents an authenticated client."""

    def __init__(
        self,
        client_id: UUID,
        api_key_id: UUID,
        permissions: list[str],
    ):
        self.client_id = client_id
        self.api_key_id = api_key_id
        self.permissions = permissions

    def has_permission(self, required_scope: str) -> bool:
        """
        Check if client has required permission.

        Args:
            required_scope: Required permission scope

        Returns:
            True if client has permission
        """
        return required_scope in self.permissions or "admin" in self.permissions


async def verify_api_key(api_key: str, db: AsyncSession) -> Optional[Tuple[UUID, UUID, list]]:
    """
    Verify API key against database.

    Args:
        api_key: API key to verify
        db: Database session

    Returns:
        Tuple of (client_id, api_key_id, permissions) if valid, None otherwise
    """
    # Import here to avoid circular dependency
    from backend.src.models.api_key import APIKey

    # Query for API key by prefix
    key_prefix = api_key[:8]

    query = select(APIKey).where(
        APIKey.key_prefix == key_prefix,
        APIKey.invalidated_at.is_(None),
    )

    result = await db.execute(query)
    api_key_record = result.scalar_one_or_none()

    if not api_key_record:
        return None

    # Verify hash using bcrypt
    if not bcrypt.checkpw(api_key.encode("utf-8"), api_key_record.key_hash.encode("utf-8")):
        return None

    # Update last_used_at timestamp
    await db.execute(
        update(APIKey)
        .where(APIKey.id == api_key_record.id)
        .values(last_used_at=datetime.utcnow())
    )
    await db.commit()

    return (
        api_key_record.client_id,
        api_key_record.id,
        api_key_record.permissions_scope,
    )


async def check_rate_limit(client_id: UUID, limit: int = 1000, window_seconds: int = 3600) -> None:
    """
    Check rate limit for client.

    Args:
        client_id: Client ID
        limit: Request limit
        window_seconds: Time window in seconds

    Raises:
        RateLimitExceededError: If rate limit exceeded
    """
    now = time.time()
    client_key = str(client_id)

    # Clean old entries
    cutoff = now - window_seconds
    _rate_limit_storage[client_key] = [
        ts for ts in _rate_limit_storage[client_key] if ts > cutoff
    ]

    # Check limit
    if len(_rate_limit_storage[client_key]) >= limit:
        retry_after = int(window_seconds - (now - _rate_limit_storage[client_key][0]))
        raise RateLimitExceededError(
            message=f"Rate limit exceeded: {limit} requests per {window_seconds} seconds",
            retry_after=retry_after,
        )

    # Add current request
    _rate_limit_storage[client_key].append(now)


async def get_current_client(
    request: Request,
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(security),
    db: AsyncSession = Depends(get_db),
) -> AuthenticatedClient:
    """
    Dependency to get authenticated client from request.

    Args:
        request: FastAPI request
        credentials: HTTP bearer token credentials
        db: Database session

    Returns:
        Authenticated client

    Raises:
        AuthenticationError: If authentication fails
    """
    # Check for API key in Authorization header
    if not credentials:
        # Try X-API-Key header as fallback
        api_key = request.headers.get("X-API-Key")
        if not api_key:
            raise InvalidAPIKeyError("Missing API key")
    else:
        api_key = credentials.credentials

    # Verify API key
    auth_result = await verify_api_key(api_key, db)
    if not auth_result:
        logger.warning(
            "Invalid API key attempt",
            extra={"api_key_prefix": api_key[:8] if len(api_key) >= 8 else "invalid"},
        )
        raise InvalidAPIKeyError("Invalid or expired API key")

    client_id, api_key_id, permissions = auth_result

    # Check rate limit
    await check_rate_limit(client_id)

    logger.info(
        "Client authenticated",
        extra={
            "client_id": str(client_id),
            "api_key_id": str(api_key_id),
        },
    )

    return AuthenticatedClient(
        client_id=client_id,
        api_key_id=api_key_id,
        permissions=permissions,
    )


def require_permission(required_scope: str):
    """
    Dependency factory to require specific permission.

    Args:
        required_scope: Required permission scope

    Returns:
        Dependency function
    """

    async def permission_checker(
        client: AuthenticatedClient = Depends(get_current_client),
    ) -> AuthenticatedClient:
        """Check if client has required permission."""
        if not client.has_permission(required_scope):
            raise AuthorizationError(
                message=f"Requires '{required_scope}' permission",
                required_scope=required_scope,
            )
        return client

    return permission_checker


# Convenience dependencies for common permission checks
require_read = require_permission("read")
require_write = require_permission("write")
require_admin = require_permission("admin")
