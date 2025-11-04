"""
Webhook delivery log entity model.

Tracks webhook delivery attempts with retry logic and status tracking.
"""

from datetime import datetime
from typing import TYPE_CHECKING, Optional
from uuid import UUID

from sqlalchemy import (
    DateTime,
    ForeignKey,
    Integer,
    String,
    Text,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from backend.src.core.database import Base

if TYPE_CHECKING:
    from backend.src.models.website import MonitoredWebsite


class WebhookDeliveryLog(Base):
    """
    Webhook delivery log entity.

    Tracks attempts to deliver change notifications to client endpoints
    with retry logic and response tracking.

    Attributes:
        id: Unique delivery attempt identifier
        product_history_id: Change that triggered webhook (FK to product_history)
        website_id: Target website (for filtering and cascade)
        target_url: Webhook endpoint URL
        payload: Complete webhook payload sent
        signature: HMAC-SHA256 signature value
        timestamp_header: Timestamp included in signature
        attempt_number: Retry attempt number (1-3)
        delivery_timestamp: Delivery attempt timestamp
        http_status_code: HTTP response code (NULL = network error)
        status: Delivery status (pending, success, failed, retrying, exhausted)
        response_body: HTTP response body (for debugging)
        error_message: Error details if delivery failed
        next_retry_at: Scheduled retry timestamp
    """

    __tablename__ = "webhook_delivery_logs"

    # Primary key
    id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        primary_key=True,
        server_default=text("gen_random_uuid()"),
    )

    # Foreign keys
    product_history_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        nullable=False,
        index=True,
        comment="Reference to product_history.id (not explicit FK due to partitioning)",
    )

    website_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("monitored_websites.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    # Webhook details
    target_url: Mapped[str] = mapped_column(
        String(2048),
        nullable=False,
    )

    payload: Mapped[dict] = mapped_column(
        JSONB,
        nullable=False,
    )

    signature: Mapped[str] = mapped_column(
        String(128),
        nullable=False,
    )

    timestamp_header: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
    )

    # Delivery tracking
    attempt_number: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        server_default=text("1"),
    )

    delivery_timestamp: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=text("NOW()"),
    )

    http_status_code: Mapped[Optional[int]] = mapped_column(
        Integer,
        nullable=True,
    )

    status: Mapped[str] = mapped_column(
        String(10),
        nullable=False,
    )

    response_body: Mapped[Optional[str]] = mapped_column(
        Text,
        nullable=True,
    )

    error_message: Mapped[Optional[str]] = mapped_column(
        Text,
        nullable=True,
    )

    next_retry_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )

    # Relationships
    website: Mapped["MonitoredWebsite"] = relationship(
        "MonitoredWebsite",
        back_populates="webhook_logs",
    )

    def __repr__(self) -> str:
        """String representation."""
        return (
            f"<WebhookDeliveryLog(id={self.id}, "
            f"website_id={self.website_id}, "
            f"status={self.status}, "
            f"attempt_number={self.attempt_number})>"
        )


# Export
__all__ = ["WebhookDeliveryLog"]
