"""
Webhook payload schemas for change notifications.

Defines request/response models for price and stock change events
according to the webhook payload specification.
"""

from datetime import datetime
from decimal import Decimal
from typing import Literal, Optional
from uuid import UUID

from pydantic import BaseModel, Field


class WebsiteInfo(BaseModel):
    """Website information in webhook payload."""

    id: UUID = Field(..., description="Monitored website identifier")
    base_url: str = Field(..., description="Website base URL", min_length=10, max_length=2048)
    name: str = Field(..., description="Human-readable website name", max_length=255)


class ProductInfo(BaseModel):
    """Product information in webhook payload."""

    id: UUID = Field(..., description="Product identifier")
    url: str = Field(..., description="Product page URL", min_length=10, max_length=2048)
    name: str = Field(..., description="Product display name", max_length=500)
    extracted_product_id: Optional[str] = Field(
        None,
        description="Extracted SKU/product code",
        max_length=255,
    )


class PriceChangeDetails(BaseModel):
    """Details of a price change."""

    type: Literal["price"] = Field(..., description="Change type (always 'price')")
    old_value: Optional[Decimal] = Field(..., description="Previous price", ge=0)
    new_value: Optional[Decimal] = Field(..., description="Current price", ge=0)
    currency: str = Field(..., description="ISO 4217 currency code", min_length=3, max_length=3)
    change_pct: Decimal = Field(..., description="Percentage change (negative = decrease)")
    absolute_change: Decimal = Field(..., description="Absolute price difference")
    detected_at: datetime = Field(..., description="When change was detected")


class StockChangeDetails(BaseModel):
    """Details of a stock status change."""

    type: Literal["stock"] = Field(..., description="Change type (always 'stock')")
    old_value: str = Field(
        ...,
        description="Previous stock status",
        pattern="^(in_stock|out_of_stock|limited_availability|unknown)$",
    )
    new_value: str = Field(
        ...,
        description="Current stock status",
        pattern="^(in_stock|out_of_stock|limited_availability|unknown)$",
    )
    detected_at: datetime = Field(..., description="When change was detected")


class PriceChangeMetadata(BaseModel):
    """Metadata for price change event."""

    crawl_id: UUID = Field(..., description="Crawl execution identifier")
    threshold_pct: Decimal = Field(..., description="Configured threshold percentage", ge=0)
    exceeded_threshold: bool = Field(..., description="Whether change exceeded threshold")


class StockChangeMetadata(BaseModel):
    """Metadata for stock change event."""

    crawl_id: UUID = Field(..., description="Crawl execution identifier")
    price_at_change: Optional[Decimal] = Field(
        None,
        description="Product price at time of stock change",
        ge=0,
    )
    currency: str = Field(..., description="ISO 4217 currency code", min_length=3, max_length=3)


class PriceChangeEvent(BaseModel):
    """
    Price change webhook payload.

    Sent when product price changes beyond configured threshold.

    Example:
        ```json
        {
          "event_type": "product.price_changed",
          "event_id": "a1b2c3d4-e5f6-7890-abcd-ef1234567890",
          "timestamp": "2025-11-03T14:30:00Z",
          "website": {
            "id": "website-uuid",
            "base_url": "https://example-shop.com",
            "name": "Example Shop"
          },
          "product": {
            "id": "product-uuid",
            "url": "https://example-shop.com/products/laptop-xyz",
            "name": "Gaming Laptop XYZ",
            "extracted_product_id": "SKU-12345"
          },
          "change": {
            "type": "price",
            "old_value": 1299.99,
            "new_value": 1199.99,
            "currency": "USD",
            "change_pct": -7.69,
            "absolute_change": -100.00,
            "detected_at": "2025-11-03T14:28:45Z"
          },
          "metadata": {
            "crawl_id": "crawl-uuid",
            "threshold_pct": 1.0,
            "exceeded_threshold": true
          }
        }
        ```
    """

    event_type: Literal["product.price_changed"] = Field(
        ...,
        description="Event type identifier",
    )
    event_id: UUID = Field(..., description="Unique event identifier")
    timestamp: datetime = Field(..., description="Webhook generation timestamp")
    website: WebsiteInfo = Field(..., description="Website information")
    product: ProductInfo = Field(..., description="Product information")
    change: PriceChangeDetails = Field(..., description="Price change details")
    metadata: PriceChangeMetadata = Field(..., description="Additional metadata")

    model_config = {"json_schema_extra": {"title": "Price Change Event"}}


class StockChangeEvent(BaseModel):
    """
    Stock change webhook payload.

    Sent when product stock status changes (e.g., in stock → out of stock).

    Example:
        ```json
        {
          "event_type": "product.stock_changed",
          "event_id": "b2c3d4e5-f6g7-8901-bcde-fg2345678901",
          "timestamp": "2025-11-03T15:45:00Z",
          "website": {
            "id": "website-uuid",
            "base_url": "https://example-shop.com",
            "name": "Example Shop"
          },
          "product": {
            "id": "product-uuid",
            "url": "https://example-shop.com/products/monitor-abc",
            "name": "4K Monitor ABC",
            "extracted_product_id": "SKU-67890"
          },
          "change": {
            "type": "stock",
            "old_value": "in_stock",
            "new_value": "out_of_stock",
            "detected_at": "2025-11-03T15:43:12Z"
          },
          "metadata": {
            "crawl_id": "crawl-uuid",
            "price_at_change": 599.99,
            "currency": "USD"
          }
        }
        ```
    """

    event_type: Literal["product.stock_changed"] = Field(
        ...,
        description="Event type identifier",
    )
    event_id: UUID = Field(..., description="Unique event identifier")
    timestamp: datetime = Field(..., description="Webhook generation timestamp")
    website: WebsiteInfo = Field(..., description="Website information")
    product: ProductInfo = Field(..., description="Product information")
    change: StockChangeDetails = Field(..., description="Stock change details")
    metadata: StockChangeMetadata = Field(..., description="Additional metadata")

    model_config = {"json_schema_extra": {"title": "Stock Change Event"}}


# Export all schemas
__all__ = [
    "WebsiteInfo",
    "ProductInfo",
    "PriceChangeDetails",
    "StockChangeDetails",
    "PriceChangeMetadata",
    "StockChangeMetadata",
    "PriceChangeEvent",
    "StockChangeEvent",
]
