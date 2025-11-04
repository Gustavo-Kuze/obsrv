"""
Pydantic schemas for website registration and management.
"""

from datetime import datetime
from typing import Any, Dict, List, Optional
from uuid import UUID

from pydantic import Field, HttpUrl, field_validator

from backend.src.models.base import BaseModel, IDMixin, TimestampMixin


class WebsiteRegistrationRequest(BaseModel):
    """Request schema for registering a new website."""

    base_url: str = Field(
        ...,
        description="Base URL of the e-commerce website",
        examples=["https://shop.example.com"],
        min_length=10,
        max_length=2048,
    )
    seed_urls: List[str] = Field(
        ...,
        description="Seed URLs for product discovery (category pages, sitemaps, etc.)",
        min_length=1,
        max_length=10,
        examples=[["https://shop.example.com/products"]],
    )
    crawl_frequency_minutes: int = Field(
        default=1440,
        description="Crawl frequency in minutes (360=6h, 480=8h, 720=12h, 1440=24h)",
        ge=360,
        le=1440,
    )
    price_change_threshold_pct: float = Field(
        default=1.0,
        description="Minimum price change percentage to trigger notification",
        ge=0.01,
        le=100.0,
    )
    retention_days: int = Field(
        default=90,
        description="Historical data retention period in days",
        ge=30,
        le=365,
    )
    webhook_endpoint_url: Optional[str] = Field(
        None,
        description="HTTPS URL for webhook notifications",
        max_length=2048,
    )
    webhook_enabled: bool = Field(
        default=True,
        description="Enable webhook notifications",
    )

    @field_validator("base_url", "webhook_endpoint_url")
    @classmethod
    def validate_url(cls, v: Optional[str]) -> Optional[str]:
        """Validate URL format."""
        if v is None:
            return v
        if not v.startswith(("http://", "https://")):
            raise ValueError("URL must start with http:// or https://")
        return v

    @field_validator("seed_urls")
    @classmethod
    def validate_seed_urls(cls, v: List[str]) -> List[str]:
        """Validate seed URLs."""
        for url in v:
            if not url.startswith(("http://", "https://")):
                raise ValueError("All seed URLs must start with http:// or https://")
        return v

    @field_validator("webhook_endpoint_url")
    @classmethod
    def validate_webhook_url(cls, v: Optional[str]) -> Optional[str]:
        """Validate webhook URL is HTTPS in production."""
        if v and not v.startswith("https://"):
            # Allow HTTP for development/testing
            import os
            if os.getenv("ENVIRONMENT", "development") == "production":
                raise ValueError("Webhook URL must use HTTPS in production")
        return v


class WebsiteUpdateRequest(BaseModel):
    """Request schema for updating website settings."""

    crawl_frequency_minutes: Optional[int] = Field(
        None,
        description="Crawl frequency in minutes",
        ge=360,
        le=1440,
    )
    price_change_threshold_pct: Optional[float] = Field(
        None,
        description="Price change threshold percentage",
        ge=0.01,
        le=100.0,
    )
    webhook_endpoint_url: Optional[str] = Field(
        None,
        description="Webhook endpoint URL",
        max_length=2048,
    )
    webhook_enabled: Optional[bool] = Field(
        None,
        description="Enable/disable webhooks",
    )


class DiscoveredProduct(BaseModel):
    """Schema for a discovered product pending approval."""

    url: str = Field(..., description="Product URL")
    normalized_url: str = Field(..., description="Normalized product URL")
    product_id: Optional[str] = Field(None, description="Extracted product ID")
    extraction_method: str = Field(..., description="Extraction method used")
    name: Optional[str] = Field(None, description="Product name (if available)")
    relevance_score: float = Field(
        ...,
        description="Relevance score (0.0-1.0)",
        ge=0.0,
        le=1.0,
    )


class Website(IDMixin, TimestampMixin):
    """Schema for monitored website."""

    client_id: UUID = Field(..., description="Owner client ID")
    base_url: str = Field(..., description="Base URL")
    status: str = Field(..., description="Website status")
    crawl_frequency_minutes: int = Field(..., description="Crawl frequency")
    price_change_threshold_pct: float = Field(..., description="Price change threshold")
    retention_days: int = Field(..., description="Data retention period")
    approved_product_count: int = Field(..., description="Number of approved products")
    last_successful_crawl_at: Optional[datetime] = Field(
        None,
        description="Last successful crawl timestamp",
    )
    last_crawl_status: Optional[str] = Field(None, description="Last crawl status")
    webhook_endpoint_url: Optional[str] = Field(None, description="Webhook URL")
    webhook_enabled: bool = Field(..., description="Webhook enabled")
    consecutive_failures: int = Field(..., description="Consecutive crawl failures")


class WebsiteRegistrationResponse(BaseModel):
    """Response schema for website registration."""

    website_id: UUID = Field(..., description="Registered website ID")
    status: str = Field(..., description="Website status")
    message: str = Field(..., description="Registration message")
    discovery_job_id: Optional[str] = Field(
        None,
        description="Inngest job ID for product discovery",
    )


class DiscoveredProductsResponse(BaseModel):
    """Response schema for discovered products."""

    website_id: UUID = Field(..., description="Website ID")
    discovered_count: int = Field(..., description="Number of products discovered")
    products: List[DiscoveredProduct] = Field(..., description="Discovered products")
    max_allowed: int = Field(..., description="Maximum products allowed")


class ApproveProductsRequest(BaseModel):
    """Request schema for approving discovered products."""

    product_urls: List[str] = Field(
        ...,
        description="List of product URLs to approve for monitoring",
        min_length=1,
        max_length=100,
    )

    @field_validator("product_urls")
    @classmethod
    def validate_product_count(cls, v: List[str]) -> List[str]:
        """Validate product count doesn't exceed limit."""
        if len(v) > 100:
            raise ValueError("Cannot approve more than 100 products per website")
        return v


class ApproveProductsResponse(BaseModel):
    """Response schema for product approval."""

    website_id: UUID = Field(..., description="Website ID")
    approved_count: int = Field(..., description="Number of products approved")
    message: str = Field(..., description="Approval message")
    baseline_crawl_job_id: Optional[str] = Field(
        None,
        description="Inngest job ID for baseline crawl",
    )


class WebsiteListResponse(BaseModel):
    """Response schema for website list."""

    websites: List[Website] = Field(..., description="List of websites")
    total: int = Field(..., description="Total number of websites")
    page: int = Field(..., description="Current page")
    page_size: int = Field(..., description="Page size")
