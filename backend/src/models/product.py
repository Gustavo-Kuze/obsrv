"""
Product data model.
"""

from datetime import datetime
from uuid import UUID, uuid4

from sqlalchemy import Boolean, DateTime, ForeignKey, Numeric, String, Text
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from backend.src.core.database import Base


class Product(Base):
    """Product model representing an individual product being tracked."""

    __tablename__ = "products"

    # Primary key
    id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        primary_key=True,
        default=uuid4,
    )

    # Foreign keys
    website_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("monitored_websites.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    # URL info
    original_url: Mapped[str] = mapped_column(String(2048), nullable=False)
    normalized_url: Mapped[str] = mapped_column(String(2048), nullable=False, index=True)

    # Product identification
    extracted_product_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    extraction_method: Mapped[str] = mapped_column(String(50), nullable=False)
    product_name: Mapped[str] = mapped_column(Text, nullable=False)

    # Current state
    current_price: Mapped[float | None] = mapped_column(Numeric(12, 2), nullable=True)
    current_currency: Mapped[str] = mapped_column(String(3), nullable=False, default="USD")
    current_stock_status: Mapped[str] = mapped_column(String(30), nullable=False)

    # Timestamps
    last_crawled_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        index=True,
    )
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
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True, index=True)
    delisted_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )

    # Relationships
    website: Mapped["MonitoredWebsite"] = relationship(
        "MonitoredWebsite",
        back_populates="products",
    )

    history_records: Mapped[list["ProductHistoryRecord"]] = relationship(
        "ProductHistoryRecord",
        back_populates="product",
        cascade="all, delete-orphan",
    )

    def __repr__(self) -> str:
        return f"<Product(id={self.id}, name={self.product_name[:50]}, price={self.current_price})>"
