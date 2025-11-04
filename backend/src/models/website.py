"""
Monitored Website data model.
"""

from datetime import datetime
from typing import Any, Dict, List
from uuid import UUID, uuid4

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, Numeric, String
from sqlalchemy.dialects.postgresql import JSONB, UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from backend.src.core.database import Base


class MonitoredWebsite(Base):
    """Monitored Website model for e-commerce sites being tracked."""

    __tablename__ = "monitored_websites"

    # Primary key
    id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        primary_key=True,
        default=uuid4,
    )

    # Foreign keys
    client_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("clients.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    # Website info
    base_url: Mapped[str] = mapped_column(String(2048), nullable=False)
    seed_urls: Mapped[List[str]] = mapped_column(JSONB, nullable=False)

    # Timestamps
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=datetime.utcnow,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=datetime.utcnow,
        onupdate=datetime.utcnow,
    )

    # Status
    status: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        default="pending_approval",
        index=True,
    )

    # Crawl configuration
    crawl_frequency_minutes: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=1440,  # Daily
    )
    price_change_threshold_pct: Mapped[float] = mapped_column(
        Numeric(5, 2),
        nullable=False,
        default=1.00,
    )
    retention_days: Mapped[int] = mapped_column(Integer, nullable=False, default=90)

    # Product discovery
    discovered_products_pending: Mapped[Dict[str, Any] | None] = mapped_column(
        JSONB,
        nullable=True,
    )
    approved_product_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    # Crawl status tracking
    last_successful_crawl_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    last_crawl_status: Mapped[str | None] = mapped_column(String(50), nullable=True)
    consecutive_failures: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    # Webhook configuration
    webhook_endpoint_url: Mapped[str | None] = mapped_column(String(2048), nullable=True)
    webhook_enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)

    # Relationships
    client: Mapped["Client"] = relationship("Client", back_populates="monitored_websites")
    products: Mapped[list["Product"]] = relationship(
        "Product",
        back_populates="website",
        cascade="all, delete-orphan",
    )
    crawl_logs: Mapped[list["CrawlExecutionLog"]] = relationship(
        "CrawlExecutionLog",
        back_populates="website",
        cascade="all, delete-orphan",
    )
    webhook_logs: Mapped[list["WebhookDeliveryLog"]] = relationship(
        "WebhookDeliveryLog",
        back_populates="website",
        cascade="all, delete-orphan",
    )

    def __repr__(self) -> str:
        return f"<MonitoredWebsite(id={self.id}, base_url={self.base_url}, status={self.status})>"
