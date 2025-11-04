"""
Website service for managing monitored websites.
"""

from datetime import datetime
from typing import Any, Dict, List, Optional
from uuid import UUID

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.src.core.exceptions import DuplicateResourceError, ResourceNotFoundError
from backend.src.core.inngest import send_event
from backend.src.core.logging import get_logger
from backend.src.core.url_utils import extract_base_domain, is_valid_url, normalize_url
from backend.src.models.website import MonitoredWebsite

logger = get_logger(__name__)


class WebsiteService:
    """Service for managing monitored websites."""

    async def register_website(
        self,
        client_id: UUID,
        base_url: str,
        seed_urls: List[str],
        crawl_frequency_minutes: int,
        price_change_threshold_pct: float,
        retention_days: int,
        webhook_endpoint_url: Optional[str],
        webhook_enabled: bool,
        db: AsyncSession,
    ) -> tuple[MonitoredWebsite, str]:
        """
        Register a new website for monitoring.

        Args:
            client_id: Client ID
            base_url: Base URL of the website
            seed_urls: List of seed URLs for discovery
            crawl_frequency_minutes: Crawl frequency
            price_change_threshold_pct: Price change threshold
            retention_days: Data retention period
            webhook_endpoint_url: Webhook URL
            webhook_enabled: Enable webhooks
            db: Database session

        Returns:
            Tuple of (website, discovery_job_id)

        Raises:
            DuplicateResourceError: If website already registered
        """
        # Normalize base URL
        normalized_base = normalize_url(base_url)
        base_domain = extract_base_domain(normalized_base)

        # Check for duplicate
        existing = await db.execute(
            select(MonitoredWebsite).where(
                MonitoredWebsite.client_id == client_id,
                MonitoredWebsite.base_url == normalized_base,
            )
        )
        if existing.scalar_one_or_none():
            raise DuplicateResourceError(
                "Website",
                identifier=base_domain,
            )

        # Validate webhook endpoint (T058: HTTPS required in production)
        if webhook_endpoint_url:
            await self._validate_webhook_endpoint(webhook_endpoint_url)

        # Create website record
        website = MonitoredWebsite(
            client_id=client_id,
            base_url=normalized_base,
            seed_urls=seed_urls,
            crawl_frequency_minutes=crawl_frequency_minutes,
            price_change_threshold_pct=price_change_threshold_pct,
            retention_days=retention_days,
            webhook_endpoint_url=webhook_endpoint_url,
            webhook_enabled=webhook_enabled,
            status="pending_approval",
        )

        db.add(website)
        await db.commit()
        await db.refresh(website)

        logger.info(
            "Website registered",
            extra={
                "website_id": str(website.id),
                "client_id": str(client_id),
                "base_url": base_domain,
            },
        )

        # Trigger product discovery via Inngest
        discovery_response = await send_event(
            name="website.registered",
            data={
                "website_id": str(website.id),
                "client_id": str(client_id),
                "base_url": normalized_base,
                "seed_urls": seed_urls,
            },
        )

        discovery_job_id = discovery_response.get("ids", [None])[0]

        logger.info(
            "Product discovery triggered",
            extra={
                "website_id": str(website.id),
                "job_id": discovery_job_id,
            },
        )

        return website, discovery_job_id

    async def get_website(
        self,
        website_id: UUID,
        client_id: UUID,
        db: AsyncSession,
    ) -> MonitoredWebsite:
        """
        Get website by ID.

        Args:
            website_id: Website ID
            client_id: Client ID (for ownership validation)
            db: Database session

        Returns:
            Website

        Raises:
            ResourceNotFoundError: If website not found or not owned by client
        """
        result = await db.execute(
            select(MonitoredWebsite).where(
                MonitoredWebsite.id == website_id,
                MonitoredWebsite.client_id == client_id,
            )
        )
        website = result.scalar_one_or_none()

        if not website:
            raise ResourceNotFoundError("Website", str(website_id))

        return website

    async def list_websites(
        self,
        client_id: UUID,
        status: Optional[str],
        page: int,
        page_size: int,
        db: AsyncSession,
    ) -> tuple[List[MonitoredWebsite], int]:
        """
        List websites for a client.

        Args:
            client_id: Client ID
            status: Optional status filter
            page: Page number (1-indexed)
            page_size: Items per page
            db: Database session

        Returns:
            Tuple of (websites, total_count)
        """
        # Build query
        query = select(MonitoredWebsite).where(MonitoredWebsite.client_id == client_id)

        if status:
            query = query.where(MonitoredWebsite.status == status)

        # Count total
        count_result = await db.execute(query)
        total = len(count_result.all())

        # Get page
        query = query.order_by(MonitoredWebsite.created_at.desc())
        query = query.offset((page - 1) * page_size).limit(page_size)

        result = await db.execute(query)
        websites = result.scalars().all()

        return list(websites), total

    async def update_website(
        self,
        website_id: UUID,
        client_id: UUID,
        updates: Dict[str, Any],
        db: AsyncSession,
    ) -> MonitoredWebsite:
        """
        Update website settings.

        Args:
            website_id: Website ID
            client_id: Client ID
            updates: Dictionary of updates
            db: Database session

        Returns:
            Updated website
        """
        website = await self.get_website(website_id, client_id, db)

        # Apply updates
        for key, value in updates.items():
            if value is not None and hasattr(website, key):
                setattr(website, key, value)

        website.updated_at = datetime.utcnow()
        await db.commit()
        await db.refresh(website)

        logger.info(
            "Website updated",
            extra={
                "website_id": str(website_id),
                "updates": list(updates.keys()),
            },
        )

        return website

    async def delete_website(
        self,
        website_id: UUID,
        client_id: UUID,
        db: AsyncSession,
    ) -> None:
        """
        Delete website and all associated data.

        Args:
            website_id: Website ID
            client_id: Client ID
            db: Database session
        """
        # Verify ownership
        website = await self.get_website(website_id, client_id, db)

        # Delete (cascade will handle products and logs)
        await db.delete(website)
        await db.commit()

        logger.info(
            "Website deleted",
            extra={
                "website_id": str(website_id),
                "client_id": str(client_id),
            },
        )

    async def get_discovered_products(
        self,
        website_id: UUID,
        client_id: UUID,
        db: AsyncSession,
    ) -> Dict[str, Any]:
        """
        Get discovered products awaiting approval.

        Args:
            website_id: Website ID
            client_id: Client ID
            db: AsyncSession

        Returns:
            Dictionary with discovered products

        Raises:
            ResourceNotFoundError: If no products discovered yet
        """
        website = await self.get_website(website_id, client_id, db)

        if not website.discovered_products_pending:
            raise ResourceNotFoundError(
                "Discovered products",
                f"No products discovered yet for website {website_id}",
            )

        return website.discovered_products_pending

    async def approve_products(
        self,
        website_id: UUID,
        client_id: UUID,
        product_urls: List[str],
        db: AsyncSession,
    ) -> str:
        """
        Approve discovered products for monitoring.

        Args:
            website_id: Website ID
            client_id: Client ID
            product_urls: List of product URLs to approve
            db: Database session

        Returns:
            Baseline crawl job ID

        Raises:
            ValueError: If too many products or products not found
        """
        website = await self.get_website(website_id, client_id, db)

        # Validate product count
        if len(product_urls) > 100:
            raise ValueError("Cannot approve more than 100 products")

        # Trigger baseline crawl via Inngest
        baseline_response = await send_event(
            name="products.approved",
            data={
                "website_id": str(website_id),
                "client_id": str(client_id),
                "product_urls": product_urls,
            },
        )

        baseline_job_id = baseline_response.get("ids", [None])[0]

        logger.info(
            "Products approved, baseline crawl triggered",
            extra={
                "website_id": str(website_id),
                "product_count": len(product_urls),
                "job_id": baseline_job_id,
            },
        )

        return baseline_job_id

    async def _validate_webhook_endpoint(self, webhook_url: str) -> None:
        """
        Validate webhook endpoint URL.

        Args:
            webhook_url: Webhook endpoint URL to validate

        Raises:
            ValueError: If webhook URL is invalid

        Validation rules (T058):
        - Must be a valid URL
        - Must use HTTPS in production (HTTP allowed in dev/test)
        """
        from backend.src.core.config import settings

        # Check if URL is valid
        if not is_valid_url(webhook_url):
            raise ValueError(f"Invalid webhook URL: {webhook_url}")

        # In production, require HTTPS
        if settings.ENVIRONMENT == "production" and not webhook_url.startswith("https://"):
            raise ValueError(
                "Webhook endpoint must use HTTPS in production environment. "
                f"Got: {webhook_url[:50]}..."
            )

        logger.debug(
            "Webhook endpoint validated",
            extra={
                "webhook_url": webhook_url,
                "environment": settings.ENVIRONMENT,
            },
        )


# Global instance
website_service = WebsiteService()
