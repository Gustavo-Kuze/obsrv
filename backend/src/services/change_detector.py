"""
Change detection service for product monitoring.

Compares current product data against previous snapshots to detect
price and stock changes that exceed configured thresholds.
"""

from decimal import Decimal
from typing import Optional
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.src.core.logging import get_logger
from backend.src.models.product import Product
from backend.src.models.product_history import ProductHistoryRecord
from backend.src.models.website import MonitoredWebsite

logger = get_logger(__name__)


class ChangeDetectionResult:
    """Result of change detection for a product."""

    def __init__(
        self,
        product_id: UUID,
        price_changed: bool = False,
        stock_changed: bool = False,
        old_price: Optional[Decimal] = None,
        new_price: Optional[Decimal] = None,
        price_change_pct: Optional[Decimal] = None,
        old_stock_status: Optional[str] = None,
        new_stock_status: Optional[str] = None,
        exceeded_threshold: bool = False,
    ):
        """
        Initialize change detection result.

        Args:
            product_id: Product UUID
            price_changed: Whether price changed
            stock_changed: Whether stock status changed
            old_price: Previous price
            new_price: Current price
            price_change_pct: Percentage price change
            old_stock_status: Previous stock status
            new_stock_status: Current stock status
            exceeded_threshold: Whether price change exceeded threshold
        """
        self.product_id = product_id
        self.price_changed = price_changed
        self.stock_changed = stock_changed
        self.old_price = old_price
        self.new_price = new_price
        self.price_change_pct = price_change_pct
        self.old_stock_status = old_stock_status
        self.new_stock_status = new_stock_status
        self.exceeded_threshold = exceeded_threshold

    def has_changes(self) -> bool:
        """Check if any changes were detected."""
        return self.price_changed or self.stock_changed

    def __repr__(self) -> str:
        """String representation."""
        return (
            f"<ChangeDetectionResult("
            f"product_id={self.product_id}, "
            f"price_changed={self.price_changed}, "
            f"stock_changed={self.stock_changed}, "
            f"exceeded_threshold={self.exceeded_threshold})>"
        )


class ChangeDetectionService:
    """
    Service for detecting product changes.

    Compares current product data against latest history record to identify:
    - Price changes that exceed configured threshold
    - Stock status transitions
    """

    async def detect_changes(
        self,
        product: Product,
        website: MonitoredWebsite,
        db: AsyncSession,
    ) -> ChangeDetectionResult:
        """
        Detect changes for a product by comparing with previous data.

        Args:
            product: Current product data
            website: Website configuration (for threshold)
            db: Database session

        Returns:
            ChangeDetectionResult with detected changes
        """
        # Get latest history record for comparison
        previous_record = await self._get_latest_history_record(product.id, db)

        # If no previous record, this is first crawl - no changes yet
        if previous_record is None:
            logger.debug(
                "No previous history for product - first crawl",
                extra={"product_id": str(product.id)},
            )
            return ChangeDetectionResult(product_id=product.id)

        # Detect price changes
        price_changed, price_change_pct, exceeded_threshold = self._detect_price_change(
            old_price=previous_record.price,
            new_price=product.current_price,
            threshold_pct=float(website.price_change_threshold_pct),
        )

        # Detect stock changes
        stock_changed = self._detect_stock_change(
            old_status=previous_record.stock_status,
            new_status=product.current_stock_status,
        )

        result = ChangeDetectionResult(
            product_id=product.id,
            price_changed=price_changed,
            stock_changed=stock_changed,
            old_price=previous_record.price,
            new_price=product.current_price,
            price_change_pct=price_change_pct,
            old_stock_status=previous_record.stock_status,
            new_stock_status=product.current_stock_status,
            exceeded_threshold=exceeded_threshold,
        )

        if result.has_changes():
            logger.info(
                "Changes detected for product",
                extra={
                    "product_id": str(product.id),
                    "product_name": product.product_name,
                    "price_changed": price_changed,
                    "stock_changed": stock_changed,
                    "exceeded_threshold": exceeded_threshold,
                    "price_change_pct": float(price_change_pct) if price_change_pct else None,
                },
            )

        return result

    async def _get_latest_history_record(
        self,
        product_id: UUID,
        db: AsyncSession,
    ) -> Optional[ProductHistoryRecord]:
        """
        Get the most recent history record for a product.

        Args:
            product_id: Product UUID
            db: Database session

        Returns:
            Latest ProductHistoryRecord or None if no history
        """
        query = (
            select(ProductHistoryRecord)
            .where(ProductHistoryRecord.product_id == product_id)
            .order_by(ProductHistoryRecord.crawl_timestamp.desc())
            .limit(1)
        )

        result = await db.execute(query)
        return result.scalar_one_or_none()

    def _detect_price_change(
        self,
        old_price: Optional[Decimal],
        new_price: Optional[Decimal],
        threshold_pct: float,
    ) -> tuple[bool, Optional[Decimal], bool]:
        """
        Detect if price has changed and if it exceeds threshold.

        Args:
            old_price: Previous price
            new_price: Current price
            threshold_pct: Threshold percentage (e.g., 1.0 for 1%)

        Returns:
            Tuple of (price_changed, price_change_pct, exceeded_threshold)
        """
        # Handle cases where price is None (out of stock products)
        if old_price is None and new_price is None:
            return False, None, False

        if old_price is None or new_price is None:
            # Price became available or unavailable
            return True, None, True

        # Calculate percentage change
        if old_price == 0:
            # Avoid division by zero
            return True, None, True

        price_change_pct = ((new_price - old_price) / old_price) * Decimal("100")

        # Check if price actually changed
        if old_price == new_price:
            return False, Decimal("0"), False

        # Check if change exceeds threshold (absolute value)
        exceeded_threshold = abs(price_change_pct) >= Decimal(str(threshold_pct))

        return True, price_change_pct, exceeded_threshold

    def _detect_stock_change(
        self,
        old_status: str,
        new_status: str,
    ) -> bool:
        """
        Detect if stock status has changed.

        Args:
            old_status: Previous stock status
            new_status: Current stock status

        Returns:
            True if stock status changed
        """
        return old_status != new_status


# Singleton instance
change_detection_service = ChangeDetectionService()

# Export
__all__ = ["ChangeDetectionService", "ChangeDetectionResult", "change_detection_service"]
