"""
Client Account data model.
"""

from datetime import datetime
from uuid import UUID, uuid4

from sqlalchemy import Boolean, DateTime, Integer, String
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from backend.src.core.database import Base


class Client(Base):
    """Client Account model representing a customer of the Obsrv service."""

    __tablename__ = "clients"

    # Primary key
    id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        primary_key=True,
        default=uuid4,
    )

    # Basic info
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    email: Mapped[str] = mapped_column(String(255), nullable=False, unique=True, index=True)

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

    # Subscription and status
    subscription_tier: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        default="basic",
    )
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True, index=True)

    # Webhook secrets for HMAC signing
    webhook_secret_current: Mapped[str] = mapped_column(String(64), nullable=False)
    webhook_secret_previous: Mapped[str | None] = mapped_column(String(64), nullable=True)
    secret_rotation_expires_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )

    # Limits
    max_websites: Mapped[int] = mapped_column(Integer, nullable=False, default=20)
    max_products_per_website: Mapped[int] = mapped_column(Integer, nullable=False, default=100)

    # Relationships
    api_keys: Mapped[list["APIKey"]] = relationship(
        "APIKey",
        back_populates="client",
        cascade="all, delete-orphan",
    )
    monitored_websites: Mapped[list["MonitoredWebsite"]] = relationship(
        "MonitoredWebsite",
        back_populates="client",
        cascade="all, delete-orphan",
    )

    def __repr__(self) -> str:
        return f"<Client(id={self.id}, name={self.name}, email={self.email})>"
