"""
Inngest function for webhook delivery with automatic retry.

Handles async webhook delivery with exponential backoff retry logic.
"""

from datetime import datetime
from typing import Any, Dict
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from backend.src.api.schemas.webhook_schemas import PriceChangeEvent, StockChangeEvent
from backend.src.core.database import get_db
from backend.src.core.inngest import create_inngest_function
from backend.src.core.logging import get_logger
from backend.src.services.webhook_service import webhook_service

logger = get_logger(__name__)


@create_inngest_function(
    fn_id="deliver-webhook",
    trigger={"event": "webhook.deliver"},
)
async def deliver_webhook_function(ctx, step):
    """
    Inngest function for webhook delivery with retry.

    Triggered by: webhook.deliver event
    Event data:
        - website_id: Website UUID
        - product_history_id: Product history record UUID
        - target_url: Webhook endpoint URL
        - webhook_secret: Client webhook secret
        - payload: Webhook payload dict
        - event_type: Event type (product.price_changed or product.stock_changed)

    Steps:
    1. Deserialize webhook payload
    2. Attempt delivery (with automatic retry on failure)
    3. Log delivery result
    """
    event_data = ctx.event.data

    website_id = UUID(event_data["website_id"])
    product_history_id = UUID(event_data["product_history_id"])
    target_url = event_data["target_url"]
    webhook_secret = event_data["webhook_secret"]
    payload_dict = event_data["payload"]
    event_type = event_data["event_type"]

    logger.info(
        "Webhook delivery function triggered",
        extra={
            "website_id": str(website_id),
            "product_history_id": str(product_history_id),
            "event_type": event_type,
        },
    )

    # Step 1: Deserialize payload
    @step.run("deserialize-payload")
    async def deserialize_payload() -> Dict[str, Any]:
        """Deserialize webhook payload to Pydantic model."""
        try:
            if event_type == "product.price_changed":
                payload = PriceChangeEvent(**payload_dict)
            elif event_type == "product.stock_changed":
                payload = StockChangeEvent(**payload_dict)
            else:
                raise ValueError(f"Unknown event type: {event_type}")

            logger.debug(
                "Webhook payload deserialized",
                extra={"event_type": event_type},
            )

            return {"payload": payload, "success": True}

        except Exception as e:
            logger.error(
                "Failed to deserialize webhook payload",
                extra={
                    "event_type": event_type,
                    "error": str(e),
                },
                exc_info=True,
            )
            return {"error": str(e), "success": False}

    deserialize_result = await deserialize_payload()

    if not deserialize_result["success"]:
        return {"error": "Failed to deserialize payload", "details": deserialize_result["error"]}

    payload = deserialize_result["payload"]

    # Step 2: Attempt delivery with retry
    @step.run("deliver-webhook")
    async def deliver_webhook_with_retry() -> Dict[str, Any]:
        """
        Deliver webhook with automatic retry.

        Inngest will automatically retry failed steps with exponential backoff.
        """
        async for db in get_db():
            try:
                # Attempt 1: Immediate delivery
                delivery_log = await webhook_service.deliver_webhook(
                    target_url=target_url,
                    payload=payload,
                    webhook_secret=webhook_secret,
                    website_id=website_id,
                    product_history_id=product_history_id,
                    attempt_number=1,
                    db=db,
                )

                if delivery_log.status == "success":
                    logger.info(
                        "Webhook delivered successfully on first attempt",
                        extra={
                            "delivery_id": str(delivery_log.id),
                            "website_id": str(website_id),
                        },
                    )
                    return {
                        "success": True,
                        "delivery_id": str(delivery_log.id),
                        "status": delivery_log.status,
                        "attempt_number": 1,
                    }

                # If failed, retry with delays
                attempt_number = 2
                while attempt_number <= webhook_service.MAX_ATTEMPTS:
                    logger.info(
                        "Retrying webhook delivery",
                        extra={
                            "website_id": str(website_id),
                            "attempt_number": attempt_number,
                        },
                    )

                    # Wait for retry delay (Inngest handles this via step retry)
                    delivery_log = await webhook_service.deliver_webhook(
                        target_url=target_url,
                        payload=payload,
                        webhook_secret=webhook_secret,
                        website_id=website_id,
                        product_history_id=product_history_id,
                        attempt_number=attempt_number,
                        db=db,
                    )

                    if delivery_log.status == "success":
                        logger.info(
                            "Webhook delivered successfully after retry",
                            extra={
                                "delivery_id": str(delivery_log.id),
                                "attempt_number": attempt_number,
                            },
                        )
                        return {
                            "success": True,
                            "delivery_id": str(delivery_log.id),
                            "status": delivery_log.status,
                            "attempt_number": attempt_number,
                        }

                    attempt_number += 1

                # All attempts exhausted
                logger.error(
                    "Webhook delivery exhausted all retry attempts",
                    extra={
                        "delivery_id": str(delivery_log.id),
                        "website_id": str(website_id),
                        "final_status": delivery_log.status,
                    },
                )

                return {
                    "success": False,
                    "delivery_id": str(delivery_log.id),
                    "status": delivery_log.status,
                    "error": delivery_log.error_message,
                    "attempt_number": webhook_service.MAX_ATTEMPTS,
                }

            except Exception as e:
                logger.error(
                    "Webhook delivery failed with unexpected error",
                    extra={
                        "website_id": str(website_id),
                        "error": str(e),
                    },
                    exc_info=True,
                )
                return {
                    "success": False,
                    "error": str(e),
                }

    delivery_result = await deliver_webhook_with_retry()

    # Step 3: Log final result
    @step.run("log-delivery-result")
    async def log_delivery_result():
        """Log final delivery result for monitoring."""
        logger.info(
            "Webhook delivery completed",
            extra={
                "website_id": str(website_id),
                "product_history_id": str(product_history_id),
                "success": delivery_result.get("success", False),
                "attempt_number": delivery_result.get("attempt_number", 1),
            },
        )
        return {"logged": True}

    await log_delivery_result()

    return delivery_result


# Export
__all__ = ["deliver_webhook_function"]
