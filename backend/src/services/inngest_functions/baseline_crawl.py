"""
Inngest function for baseline crawl of approved products.
"""

from typing import Any, Dict, List
from uuid import UUID

from sqlalchemy import select

from backend.src.core.database import AsyncSessionLocal
from backend.src.core.inngest import create_inngest_function
from backend.src.core.logging import get_logger
from backend.src.models.website import MonitoredWebsite
from backend.src.services.baseline_crawl_service import baseline_crawl_service

logger = get_logger(__name__)


@create_inngest_function(
    fn_id="baseline-crawl",
    name="Perform Baseline Crawl on Approved Products",
    trigger={"event": "products.approved"},
    retries=3,
)
async def baseline_crawl_function(ctx, step):
    """
    Inngest function to perform baseline crawl on approved products.

    Args:
        ctx: Inngest context
        step: Inngest step for managing workflow

    Workflow:
        1. Fetch approved product URLs
        2. Crawl each product
        3. Store baseline data
        4. Update website status to active
    """
    website_id = UUID(ctx.event.data["website_id"])
    product_urls = ctx.event.data["product_urls"]

    @step.run("validate-input")
    async def validate_input():
        """Validate input parameters."""
        if not product_urls:
            raise ValueError("No product URLs provided for baseline crawl")

        logger.info(
            "Starting baseline crawl",
            extra={
                "website_id": str(website_id),
                "product_count": len(product_urls),
            },
        )

        return True

    @step.run("perform-baseline-crawl")
    async def perform_baseline_crawl():
        """Crawl approved products and store baseline data."""
        async with AsyncSessionLocal() as db:
            result = await baseline_crawl_service.crawl_approved_products(
                website_id=website_id,
                product_urls=product_urls,
                db=db,
            )

            logger.info(
                "Baseline crawl completed",
                extra={
                    "website_id": str(website_id),
                    "products_created": result["products_created"],
                    "errors": result["errors_count"],
                },
            )

            return result

    # Execute workflow steps
    await validate_input()
    result = await perform_baseline_crawl()

    return {
        "website_id": str(website_id),
        "status": result["status"],
        "products_created": result["products_created"],
        "errors_count": result["errors_count"],
        "duration_seconds": result["duration_seconds"],
    }
