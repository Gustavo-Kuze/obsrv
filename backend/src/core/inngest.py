"""
Inngest client configuration for background task processing.
"""

from typing import Any, Dict, Optional

from inngest import Inngest
from inngest.experimental import get_client

from backend.src.core.config import settings
from backend.src.core.logging import get_logger

logger = get_logger(__name__)

# Initialize Inngest client
inngest_client = Inngest(
    app_id=settings.INNGEST_APP_ID,
    event_key=settings.INNGEST_EVENT_KEY,
    signing_key=settings.INNGEST_SIGNING_KEY,
    logger=logger,
)


async def send_event(
    name: str,
    data: Dict[str, Any],
    user: Optional[Dict[str, Any]] = None,
    ts: Optional[int] = None,
) -> Dict[str, Any]:
    """
    Send an event to Inngest for background processing.

    Args:
        name: Event name (e.g., "website.registered")
        data: Event payload data
        user: Optional user context
        ts: Optional timestamp (milliseconds since epoch)

    Returns:
        Response from Inngest API

    Raises:
        InngestError: If event delivery fails

    Example:
        >>> await send_event(
        ...     name="product.discovery",
        ...     data={"website_id": "123", "seed_urls": ["https://example.com"]},
        ... )
    """
    try:
        event_data = {
            "name": name,
            "data": data,
        }

        if user:
            event_data["user"] = user
        if ts:
            event_data["ts"] = ts

        logger.info(
            "Sending Inngest event",
            extra={
                "event_name": name,
                "data_keys": list(data.keys()),
            },
        )

        # Send event to Inngest
        response = await inngest_client.send(event_data)

        logger.info(
            "Inngest event sent successfully",
            extra={
                "event_name": name,
                "event_ids": response.get("ids", []),
            },
        )

        return response

    except Exception as e:
        logger.error(
            "Failed to send Inngest event",
            extra={
                "event_name": name,
                "error": str(e),
            },
            exc_info=True,
        )
        from backend.src.core.exceptions import InngestError

        raise InngestError(
            message=f"Failed to send event '{name}' to Inngest",
            function_name=name,
        ) from e


async def send_batch_events(events: list[Dict[str, Any]]) -> Dict[str, Any]:
    """
    Send multiple events to Inngest in a single batch.

    Args:
        events: List of event dictionaries with 'name' and 'data' keys

    Returns:
        Response from Inngest API

    Example:
        >>> await send_batch_events([
        ...     {"name": "product.discovered", "data": {"product_id": "1"}},
        ...     {"name": "product.discovered", "data": {"product_id": "2"}},
        ... ])
    """
    try:
        logger.info(
            "Sending batch Inngest events",
            extra={"batch_size": len(events)},
        )

        response = await inngest_client.send(events)

        logger.info(
            "Batch events sent successfully",
            extra={
                "batch_size": len(events),
                "event_ids": response.get("ids", []),
            },
        )

        return response

    except Exception as e:
        logger.error(
            "Failed to send batch Inngest events",
            extra={
                "batch_size": len(events),
                "error": str(e),
            },
            exc_info=True,
        )
        from backend.src.core.exceptions import InngestError

        raise InngestError(
            message="Failed to send batch events to Inngest",
        ) from e


def create_inngest_function(
    fn_id: str,
    name: str,
    trigger: Dict[str, Any],
    retries: int = 3,
):
    """
    Decorator to create an Inngest function.

    Args:
        fn_id: Unique function identifier
        name: Human-readable function name
        trigger: Trigger configuration (event or cron)
        retries: Number of retry attempts

    Example:
        >>> @create_inngest_function(
        ...     fn_id="discover-products",
        ...     name="Discover Products from Seed URLs",
        ...     trigger={"event": "website.registered"},
        ...     retries=3,
        ... )
        ... async def discover_products(ctx, step):
        ...     website_id = ctx.event.data["website_id"]
        ...     # Implementation...
    """
    return inngest_client.create_function(
        fn_id=fn_id,
        name=name,
        trigger=trigger,
        retries=retries,
    )


async def check_inngest_health() -> Dict[str, Any]:
    """
    Check Inngest connectivity and health.

    Returns:
        Health status dictionary

    Example:
        >>> status = await check_inngest_health()
        >>> print(status["status"])  # "healthy" or "unhealthy"
    """
    try:
        # Try to get client info to verify connectivity
        client = get_client()
        if client:
            return {
                "status": "healthy",
                "service": "inngest",
                "app_id": settings.INNGEST_APP_ID,
            }
        else:
            return {
                "status": "unhealthy",
                "service": "inngest",
                "error": "Client not initialized",
            }
    except Exception as e:
        logger.error(
            "Inngest health check failed",
            extra={"error": str(e)},
            exc_info=True,
        )
        return {
            "status": "unhealthy",
            "service": "inngest",
            "error": str(e),
        }


# Export commonly used objects
__all__ = [
    "inngest_client",
    "send_event",
    "send_batch_events",
    "create_inngest_function",
    "check_inngest_health",
]
