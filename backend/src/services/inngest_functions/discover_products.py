"""
Inngest function for product discovery from seed URLs.
"""

from typing import Any, Dict
from uuid import UUID

from sqlalchemy import select

from backend.src.core.database import AsyncSessionLocal
from backend.src.core.inngest import create_inngest_function
from backend.src.core.logging import get_logger
from backend.src.models.website import MonitoredWebsite
from backend.src.services.discovery_service import discovery_service

logger = get_logger(__name__)


@create_inngest_function(
    fn_id="discover-products",
    name="Discover Products from Seed URLs",
    trigger={"event": "website.registered"},
    retries=3,
)
async def discover_products_function(ctx, step):
    """
    Inngest function to discover products from seed URLs.

    Args:
        ctx: Inngest context
        step: Inngest step for managing workflow

    Workflow:
        1. Fetch website details
        2. Discover products from seed URLs
        3. Store discovered products
        4. Send completion event
    """
    website_id = UUID(ctx.event.data["website_id"])

    @step.run("fetch-website")
    async def fetch_website():
        """Fetch website details from database."""
        async with AsyncSessionLocal() as db:
            result = await db.execute(
                select(MonitoredWebsite).where(MonitoredWebsite.id == website_id)
            )
            website = result.scalar_one_or_none()

            if not website:
                logger.error(f"Website {website_id} not found")
                raise ValueError(f"Website {website_id} not found")

            return {
                "base_url": website.base_url,
                "seed_urls": website.seed_urls,
                "max_products": website.client.max_products_per_website,
            }

    @step.run("discover-products")
    async def discover_products(website_data: Dict[str, Any]):
        """Discover products from seed URLs."""
        logger.info(
            "Discovering products",
            extra={
                "website_id": str(website_id),
                "base_url": website_data["base_url"],
                "seed_count": len(website_data["seed_urls"]),
            },
        )

        products = await discovery_service.discover_products(
            base_url=website_data["base_url"],
            seed_urls=website_data["seed_urls"],
            max_products=website_data["max_products"],
        )

        logger.info(
            "Products discovered",
            extra={
                "website_id": str(website_id),
                "count": len(products),
            },
        )

        return products

    @step.run("store-discovered-products")
    async def store_discovered_products(products: list):
        """Store discovered products in database."""
        async with AsyncSessionLocal() as db:
            result = await db.execute(
                select(MonitoredWebsite).where(MonitoredWebsite.id == website_id)
            )
            website = result.scalar_one()

            # Store discovered products as pending
            website.discovered_products_pending = {
                "products": products,
                "discovered_at": str(ctx.event.ts),
                "total_count": len(products),
            }

            await db.commit()

            logger.info(
                "Discovered products stored",
                extra={
                    "website_id": str(website_id),
                    "product_count": len(products),
                },
            )

            return len(products)

    # Execute workflow steps
    website_data = await fetch_website()
    products = await discover_products(website_data)
    count = await store_discovered_products(products)

    logger.info(
        "Product discovery completed",
        extra={
            "website_id": str(website_id),
            "products_discovered": count,
        },
    )

    return {
        "website_id": str(website_id),
        "products_discovered": count,
        "status": "completed",
    }
