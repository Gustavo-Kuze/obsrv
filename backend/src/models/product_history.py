"""
Product history record entity model.

Represents point-in-time snapshots of product data with change detection.
Table is partitioned by month for efficient time-series queries.
"""

from datetime import datetime
from decimal import Decimal
from typing import TYPE_CHECKING, Optional
from uuid import UUID

from sqlalchemy import (
    Boolean,
    DateTime,
    Enum as SQLEnum,
    ForeignKey,
    Numeric,
    String,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from backend.src.models.base import Base

if TYPE_CHECKING:
    from backend.src.models.crawl_log import CrawlExecutionLog
    from backend.src.models.product import Product
    from backend.src.models.website import MonitoredWebsite


class ProductHistoryRecord(Base):
    """
    Product history record entity.

    Stores point-in-time snapshots of product data with change detection flags.
    Table is partitioned by crawl_timestamp (monthly) for efficient queries.

    Attributes:
        id: Unique history record identifier
        product_id: Referenced product
        website_id: Denormalized website reference for partition key
        crawl_timestamp: Snapshot timestamp (partition key)
        price: Price at this snapshot
        currency: Currency code (ISO 4217)
        stock_status: Stock status at this snapshot
        price_changed: Flag indicating price change from previous
        stock_changed: Flag indicating stock change from previous
        price_change_pct: Percentage change from previous price
        raw_crawl_data: Full crawled data (flexible JSONB)
        crawl_log_id: Associated crawl execution
    """

    __tablename__ = "product_history"

    # Primary key
    id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        primary_key=True,
        server_default=text("gen_random_uuid()"),
    )

    # Foreign keys
    product_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("products.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    website_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("monitored_websites.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    crawl_log_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("crawl_execution_logs.id", ondelete="CASCADE"),
        nullable=False,
    )

    # Timestamp (partition key)
    crawl_timestamp: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        index=True,
    )

    # Product data snapshot
    price: Mapped[Optional[Decimal]] = mapped_column(
        Numeric(12, 2),
        nullable=True,
    )

    currency: Mapped[str] = mapped_column(
        String(3),
        nullable=False,
    )

    stock_status: Mapped[str] = mapped_column(
        SQLEnum(
            "in_stock",
            "out_of_stock",
            "limited_availability",
            "unknown",
            name="stock_status",
        ),
        nullable=False,
    )

    # Change detection flags
    price_changed: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        server_default=text("FALSE"),
    )

    stock_changed: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        server_default=text("FALSE"),
    )

    price_change_pct: Mapped[Optional[Decimal]] = mapped_column(
        Numeric(6, 2),
        nullable=True,
    )

    # Raw crawl data
    raw_crawl_data: Mapped[dict] = mapped_column(
        JSONB,
        nullable=False,
    )

    # Relationships
    product: Mapped["Product"] = relationship(
        "Product",
        back_populates="history_records",
    )

    website: Mapped["MonitoredWebsite"] = relationship(
        "MonitoredWebsite",
        foreign_keys=[website_id],
    )

    crawl_log: Mapped["CrawlExecutionLog"] = relationship(
        "CrawlExecutionLog",
        foreign_keys=[crawl_log_id],
    )

    def __repr__(self) -> str:
        """String representation."""
        return (
            f"<ProductHistoryRecord(id={self.id}, "
            f"product_id={self.product_id}, "
            f"crawl_timestamp={self.crawl_timestamp}, "
            f"price_changed={self.price_changed}, "
            f"stock_changed={self.stock_changed})>"
        )


# Export
__all__ = ["ProductHistoryRecord"]
