"""
Baseline crawl service for establishing initial product data.
"""

from datetime import datetime
from typing import Any, Dict, List
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.src.core.logging import get_logger
from backend.src.models.crawl_log import CrawlExecutionLog
from backend.src.models.product import Product
from backend.src.models.website import MonitoredWebsite
from backend.src.services.crawler_service import crawler_service

logger = get_logger(__name__)


class BaselineCrawlService:
    """Service for performing baseline crawls on approved products."""

    async def crawl_approved_products(
        self,
        website_id: UUID,
        product_urls: List[str],
        db: AsyncSession,
    ) -> Dict[str, Any]:
        """
        Perform baseline crawl on approved products.

        Args:
            website_id: Website ID
            product_urls: List of approved product URLs
            db: Database session

        Returns:
            Crawl results dictionary
        """
        logger.info(
            "Starting baseline crawl",
            extra={
                "website_id": str(website_id),
                "product_count": len(product_urls),
            },
        )

        # Create crawl log
        crawl_log = CrawlExecutionLog(
            website_id=website_id,
            started_at=datetime.utcnow(),
            status="running",
            triggered_by="discovery",
        )
        db.add(crawl_log)
        await db.commit()
        await db.refresh(crawl_log)

        products_created = []
        errors = []

        try:
            # Crawl each product
            for url in product_urls:
                try:
                    product_data = await crawler_service.crawl_product(url)

                    # Create product record
                    product = Product(
                        website_id=website_id,
                        original_url=url,
                        normalized_url=product_data["normalized_url"],
                        extracted_product_id=product_data.get("product_id"),
                        extraction_method=product_data["extraction_method"],
                        product_name=product_data.get("product_name") or "Unknown Product",
                        current_price=product_data.get("price"),
                        current_currency=product_data.get("currency", "USD"),
                        current_stock_status=product_data.get("stock_status", "unknown"),
                        last_crawled_at=product_data["crawled_at"],
                        is_active=True,
                    )

                    db.add(product)
                    products_created.append(product)

                    logger.info(
                        "Product created from baseline crawl",
                        extra={
                            "url": url,
                            "product_id": product.id,
                            "price": product.current_price,
                        },
                    )

                except Exception as e:
                    logger.error(
                        "Failed to crawl product during baseline",
                        extra={"url": url, "error": str(e)},
                        exc_info=True,
                    )
                    errors.append({"url": url, "error": str(e)})

            # Commit all products
            await db.commit()

            # Update crawl log
            crawl_log.completed_at = datetime.utcnow()
            crawl_log.duration_seconds = int(
                (crawl_log.completed_at - crawl_log.started_at).total_seconds()
            )
            crawl_log.products_processed = len(products_created)
            crawl_log.errors_count = len(errors)
            crawl_log.status = "success" if len(errors) == 0 else "partial_success"

            if errors:
                crawl_log.error_details = {"errors": errors}

            await db.commit()

            # Update website status
            website_result = await db.execute(
                select(MonitoredWebsite).where(MonitoredWebsite.id == website_id)
            )
            website = website_result.scalar_one()

            website.status = "active"
            website.approved_product_count = len(products_created)
            website.last_successful_crawl_at = datetime.utcnow()
            website.last_crawl_status = "success"
            await db.commit()

            logger.info(
                "Baseline crawl completed",
                extra={
                    "website_id": str(website_id),
                    "products_created": len(products_created),
                    "errors": len(errors),
                    "status": crawl_log.status,
                },
            )

            return {
                "crawl_log_id": crawl_log.id,
                "status": crawl_log.status,
                "products_created": len(products_created),
                "errors_count": len(errors),
                "duration_seconds": crawl_log.duration_seconds,
            }

        except Exception as e:
            logger.error(
                "Baseline crawl failed",
                extra={
                    "website_id": str(website_id),
                    "error": str(e),
                },
                exc_info=True,
            )

            # Update crawl log with failure
            crawl_log.completed_at = datetime.utcnow()
            crawl_log.status = "failed"
            crawl_log.error_details = {"error": str(e)}
            await db.commit()

            raise


# Global instance
baseline_crawl_service = BaselineCrawlService()
