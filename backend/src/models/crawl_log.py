"""
Crawl Execution Log data model.
"""

from datetime import datetime
from typing import Any, Dict
from uuid import UUID, uuid4

from sqlalchemy import DateTime, ForeignKey, Integer, String
from sqlalchemy.dialects.postgresql import JSONB, UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from backend.src.core.database import Base


class CrawlExecutionLog(Base):
    """Crawl Execution Log model for tracking crawl operations."""

    __tablename__ = "crawl_execution_logs"

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

    # Execution timing
    started_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=datetime.utcnow,
        index=True,
    )
    completed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    duration_seconds: Mapped[int | None] = mapped_column(Integer, nullable=True)

    # Status and metrics
    status: Mapped[str] = mapped_column(String(20), nullable=False, index=True)
    products_processed: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    changes_detected: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    errors_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    # Error details
    error_details: Mapped[Dict[str, Any] | None] = mapped_column(JSONB, nullable=True)

    # Retry tracking
    retry_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    triggered_by: Mapped[str] = mapped_column(String(50), nullable=False)

    # Relationships
    website: Mapped["MonitoredWebsite"] = relationship(
        "MonitoredWebsite",
        back_populates="crawl_logs",
    )

    def __repr__(self) -> str:
        return f"<CrawlExecutionLog(id={self.id}, website_id={self.website_id}, status={self.status})>"
