"""
Webhook delivery service with retry logic and status tracking.

Handles HTTP delivery of webhook notifications with HMAC signatures,
timeout handling, and exponential backoff retry strategy.
"""

import json
from datetime import datetime, timedelta
from typing import Optional
from uuid import UUID, uuid4

import httpx
from sqlalchemy.ext.asyncio import AsyncSession

from backend.src.api.schemas.webhook_schemas import PriceChangeEvent, StockChangeEvent
from backend.src.core.logging import get_logger
from backend.src.core.webhook_security import webhook_security
from backend.src.models.webhook_log import WebhookDeliveryLog

logger = get_logger(__name__)


class WebhookDeliveryService:
    """
    Service for delivering webhook notifications to client endpoints.

    Features:
    - HMAC-SHA256 signature generation
    - 10-second HTTP timeout
    - Exponential backoff retry (immediate, +5min, +30min)
    - Delivery status tracking
    - Response logging for debugging
    """

    # HTTP client timeout (seconds)
    DELIVERY_TIMEOUT = 10.0

    # Retry schedule (in minutes after previous attempt)
    RETRY_SCHEDULE = [0, 5, 30]  # Attempt 1: immediate, 2: +5min, 3: +30min

    # Maximum attempts
    MAX_ATTEMPTS = 3

    def __init__(self):
        """Initialize webhook delivery service."""
        self._http_client: Optional[httpx.AsyncClient] = None

    async def _get_http_client(self) -> httpx.AsyncClient:
        """Get or create HTTP client."""
        if self._http_client is None:
            self._http_client = httpx.AsyncClient(
                timeout=httpx.Timeout(self.DELIVERY_TIMEOUT),
                follow_redirects=True,
                headers={
                    "User-Agent": "Obsrv-Webhook/1.0",
                },
            )
        return self._http_client

    async def close(self):
        """Close HTTP client."""
        if self._http_client:
            await self._http_client.aclose()
            self._http_client = None

    async def deliver_webhook(
        self,
        target_url: str,
        payload: PriceChangeEvent | StockChangeEvent,
        webhook_secret: str,
        website_id: UUID,
        product_history_id: UUID,
        attempt_number: int = 1,
        db: AsyncSession = None,
    ) -> WebhookDeliveryLog:
        """
        Deliver webhook notification to client endpoint.

        Args:
            target_url: Webhook endpoint URL
            payload: Webhook payload (price or stock change event)
            webhook_secret: Client's webhook secret for signing
            website_id: Website UUID
            product_history_id: Product history record UUID
            attempt_number: Current attempt number (1-3)
            db: Database session (optional, for logging)

        Returns:
            WebhookDeliveryLog with delivery result
        """
        delivery_id = uuid4()
        event_type = payload.event_type
        event_id = payload.event_id

        logger.info(
            "Delivering webhook",
            extra={
                "delivery_id": str(delivery_id),
                "target_url": target_url,
                "event_type": event_type,
                "event_id": str(event_id),
                "attempt_number": attempt_number,
            },
        )

        # Serialize payload to JSON
        payload_json = payload.model_dump_json()

        # Generate HMAC signature
        signature_header, timestamp = webhook_security.generate_signature(
            payload=payload_json,
            webhook_secret=webhook_secret,
        )

        # Prepare HTTP request
        headers = {
            "Content-Type": "application/json",
            "X-Obsrv-Signature": signature_header,
            "X-Obsrv-Event": event_type,
            "X-Obsrv-Delivery-ID": str(delivery_id),
        }

        # Attempt delivery
        http_status_code = None
        response_body = None
        error_message = None
        status = "pending"

        try:
            client = await self._get_http_client()

            response = await client.post(
                url=target_url,
                content=payload_json,
                headers=headers,
            )

            http_status_code = response.status_code
            response_body = response.text[:1000]  # Limit to 1KB

            # Check if delivery was successful (2xx status)
            if 200 <= http_status_code < 300:
                status = "success"
                logger.info(
                    "Webhook delivered successfully",
                    extra={
                        "delivery_id": str(delivery_id),
                        "http_status": http_status_code,
                        "attempt_number": attempt_number,
                    },
                )
            else:
                status = "failed"
                error_message = f"HTTP {http_status_code}: {response_body}"
                logger.warning(
                    "Webhook delivery failed - non-2xx status",
                    extra={
                        "delivery_id": str(delivery_id),
                        "http_status": http_status_code,
                        "attempt_number": attempt_number,
                    },
                )

        except httpx.TimeoutException as e:
            status = "failed"
            error_message = f"Request timeout after {self.DELIVERY_TIMEOUT}s"
            logger.warning(
                "Webhook delivery failed - timeout",
                extra={
                    "delivery_id": str(delivery_id),
                    "error": str(e),
                    "attempt_number": attempt_number,
                },
            )

        except httpx.RequestError as e:
            status = "failed"
            error_message = f"Request error: {str(e)}"
            logger.warning(
                "Webhook delivery failed - request error",
                extra={
                    "delivery_id": str(delivery_id),
                    "error": str(e),
                    "attempt_number": attempt_number,
                },
            )

        except Exception as e:
            status = "failed"
            error_message = f"Unexpected error: {str(e)}"
            logger.error(
                "Webhook delivery failed - unexpected error",
                extra={
                    "delivery_id": str(delivery_id),
                    "error": str(e),
                    "attempt_number": attempt_number,
                },
                exc_info=True,
            )

        # Determine next status and retry time
        next_retry_at = None
        if status == "failed":
            if attempt_number < self.MAX_ATTEMPTS:
                status = "retrying"
                # Calculate next retry time
                retry_delay_minutes = self.RETRY_SCHEDULE[attempt_number]  # Next attempt delay
                next_retry_at = datetime.utcnow() + timedelta(minutes=retry_delay_minutes)

                logger.info(
                    "Webhook will be retried",
                    extra={
                        "delivery_id": str(delivery_id),
                        "attempt_number": attempt_number,
                        "next_attempt": attempt_number + 1,
                        "next_retry_at": next_retry_at.isoformat(),
                    },
                )
            else:
                status = "exhausted"
                logger.error(
                    "Webhook delivery exhausted all retries",
                    extra={
                        "delivery_id": str(delivery_id),
                        "attempt_number": attempt_number,
                        "final_error": error_message,
                    },
                )

        # Create delivery log
        delivery_log = WebhookDeliveryLog(
            id=delivery_id,
            product_history_id=product_history_id,
            website_id=website_id,
            target_url=target_url,
            payload=json.loads(payload_json),
            signature=signature_header,
            timestamp_header=datetime.fromtimestamp(timestamp),
            attempt_number=attempt_number,
            delivery_timestamp=datetime.utcnow(),
            http_status_code=http_status_code,
            status=status,
            response_body=response_body,
            error_message=error_message,
            next_retry_at=next_retry_at,
        )

        # Save to database if session provided
        if db:
            db.add(delivery_log)
            await db.commit()
            await db.refresh(delivery_log)

        return delivery_log

    async def should_retry(self, delivery_log: WebhookDeliveryLog) -> bool:
        """
        Check if a failed webhook delivery should be retried.

        Args:
            delivery_log: Previous delivery attempt log

        Returns:
            True if retry should be attempted
        """
        # Only retry if status is "retrying" and not exhausted
        if delivery_log.status != "retrying":
            return False

        # Check if retry time has passed
        if delivery_log.next_retry_at and datetime.utcnow() >= delivery_log.next_retry_at:
            return True

        return False

    def get_next_attempt_number(self, current_attempt: int) -> int:
        """
        Get next attempt number for retry.

        Args:
            current_attempt: Current attempt number

        Returns:
            Next attempt number (capped at MAX_ATTEMPTS)
        """
        return min(current_attempt + 1, self.MAX_ATTEMPTS)


# Singleton instance
webhook_service = WebhookDeliveryService()

# Export
__all__ = ["WebhookDeliveryService", "webhook_service"]
