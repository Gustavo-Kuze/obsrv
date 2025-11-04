"""
Inngest function for scheduled product crawls.

Processes all active websites, crawls their products, detects changes,
and triggers webhook notifications for detected changes.
"""

from datetime import datetime
from typing import Any, Dict
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.src.api.schemas.webhook_schemas import (
    PriceChangeDetails,
    PriceChangeEvent,
    PriceChangeMetadata,
    ProductInfo,
    StockChangeDetails,
    StockChangeEvent,
    StockChangeMetadata,
    WebsiteInfo,
)
from backend.src.core.database import get_db
from backend.src.core.inngest import create_inngest_function, send_event
from backend.src.core.logging import get_logger
from backend.src.models.client import Client
from backend.src.models.crawl_log import CrawlExecutionLog
from backend.src.models.product import Product
from backend.src.models.product_history import ProductHistoryRecord
from backend.src.models.website import MonitoredWebsite
from backend.src.services.change_detector import change_detection_service
from backend.src.services.crawler_service import crawler_service

logger = get_logger(__name__)


async def process_scheduled_crawl(website_id: UUID) -> Dict[str, Any]:
    """
    Process scheduled crawl for a website.

    Args:
        website_id: Website UUID to crawl

    Returns:
        Crawl statistics dictionary
    """
    async for db in get_db():
        try:
            # Fetch website with products
            query = (
                select(MonitoredWebsite)
                .where(
                    MonitoredWebsite.id == website_id,
                    MonitoredWebsite.status == "active",
                )
            )
            result = await db.execute(query)
            website = result.scalar_one_or_none()

            if not website:
                logger.warning(
                    "Website not found or not active for scheduled crawl",
                    extra={"website_id": str(website_id)},
                )
                return {"error": "Website not found or not active"}

            # Fetch client for webhook secret
            client_query = select(Client).where(Client.id == website.client_id)
            client_result = await db.execute(client_query)
            client = client_result.scalar_one_or_none()

            if not client:
                logger.error(
                    "Client not found for website",
                    extra={"website_id": str(website_id), "client_id": str(website.client_id)},
                )
                return {"error": "Client not found"}

            # Create crawl execution log
            crawl_log = CrawlExecutionLog(
                website_id=website_id,
                status="running",
                triggered_by="scheduled",
            )
            db.add(crawl_log)
            await db.commit()
            await db.refresh(crawl_log)

            logger.info(
                "Starting scheduled crawl",
                extra={
                    "website_id": str(website_id),
                    "crawl_log_id": str(crawl_log.id),
                    "base_url": website.base_url,
                },
            )

            # Fetch active products
            products_query = (
                select(Product)
                .where(
                    Product.website_id == website_id,
                    Product.is_active == True,
                )
            )
            products_result = await db.execute(products_query)
            products = list(products_result.scalars().all())

            if not products:
                logger.info(
                    "No active products to crawl for website",
                    extra={"website_id": str(website_id)},
                )
                crawl_log.status = "success"
                crawl_log.completed_at = datetime.utcnow()
                await db.commit()
                return {"products_processed": 0, "changes_detected": 0}

            # Crawl each product and detect changes
            products_processed = 0
            changes_detected = 0
            errors_count = 0
            error_details = []

            for product in products:
                try:
                    # Crawl product
                    crawl_result = await crawler_service.crawl_product(product.original_url)

                    if crawl_result and "error" not in crawl_result:
                        # Update product current state
                        product.current_price = crawl_result.get("price")
                        product.current_stock_status = crawl_result.get("stock_status", "unknown")
                        product.product_name = crawl_result.get("name", product.product_name)
                        product.last_crawled_at = datetime.utcnow()
                        product.updated_at = datetime.utcnow()

                        # Detect changes
                        change_result = await change_detection_service.detect_changes(
                            product=product,
                            website=website,
                            db=db,
                        )

                        # Create history record
                        history_record = ProductHistoryRecord(
                            product_id=product.id,
                            website_id=website_id,
                            crawl_timestamp=datetime.utcnow(),
                            price=product.current_price,
                            currency=product.current_currency,
                            stock_status=product.current_stock_status,
                            price_changed=change_result.price_changed,
                            stock_changed=change_result.stock_changed,
                            price_change_pct=change_result.price_change_pct,
                            raw_crawl_data=crawl_result,
                            crawl_log_id=crawl_log.id,
                        )
                        db.add(history_record)
                        await db.flush()  # Get history_record.id

                        # If changes detected and webhook enabled, trigger webhook
                        if change_result.has_changes() and website.webhook_enabled and website.webhook_endpoint_url:
                            await trigger_webhook_for_change(
                                change_result=change_result,
                                product=product,
                                website=website,
                                client=client,
                                history_record_id=history_record.id,
                                crawl_log_id=crawl_log.id,
                            )
                            changes_detected += 1

                        products_processed += 1

                    else:
                        errors_count += 1
                        error_msg = crawl_result.get("error") if crawl_result else "No result"
                        error_details.append({
                            "product_id": str(product.id),
                            "product_url": product.original_url,
                            "error": error_msg,
                        })
                        logger.warning(
                            "Failed to crawl product",
                            extra={
                                "product_id": str(product.id),
                                "error": error_msg,
                            },
                        )

                except Exception as e:
                    errors_count += 1
                    error_details.append({
                        "product_id": str(product.id),
                        "product_url": product.original_url,
                        "error": str(e),
                    })
                    logger.error(
                        "Error processing product during crawl",
                        extra={"product_id": str(product.id), "error": str(e)},
                        exc_info=True,
                    )

            # Update crawl log
            crawl_log.products_processed = products_processed
            crawl_log.changes_detected = changes_detected
            crawl_log.errors_count = errors_count
            crawl_log.error_details = error_details if error_details else None
            crawl_log.completed_at = datetime.utcnow()
            crawl_log.duration_seconds = int(
                (crawl_log.completed_at - crawl_log.started_at).total_seconds()
            )

            # Determine final status
            if errors_count == 0:
                crawl_log.status = "success"
            elif products_processed > 0:
                crawl_log.status = "partial_success"
            else:
                crawl_log.status = "failed"

            # Update website crawl status
            website.last_successful_crawl_at = datetime.utcnow()
            website.last_crawl_status = crawl_log.status

            if crawl_log.status == "failed":
                website.consecutive_failures += 1
            else:
                website.consecutive_failures = 0

            # Auto-pause website after 3 consecutive failures
            if website.consecutive_failures >= 3:
                website.status = "paused"
                logger.warning(
                    "Website auto-paused due to consecutive failures",
                    extra={
                        "website_id": str(website_id),
                        "consecutive_failures": website.consecutive_failures,
                    },
                )

            await db.commit()

            logger.info(
                "Scheduled crawl completed",
                extra={
                    "website_id": str(website_id),
                    "crawl_log_id": str(crawl_log.id),
                    "status": crawl_log.status,
                    "products_processed": products_processed,
                    "changes_detected": changes_detected,
                    "errors_count": errors_count,
                },
            )

            return {
                "crawl_log_id": str(crawl_log.id),
                "status": crawl_log.status,
                "products_processed": products_processed,
                "changes_detected": changes_detected,
                "errors_count": errors_count,
            }

        except Exception as e:
            logger.error(
                "Scheduled crawl failed with unexpected error",
                extra={"website_id": str(website_id), "error": str(e)},
                exc_info=True,
            )
            return {"error": str(e)}


async def trigger_webhook_for_change(
    change_result: Any,
    product: Product,
    website: MonitoredWebsite,
    client: Client,
    history_record_id: UUID,
    crawl_log_id: UUID,
):
    """
    Trigger webhook delivery for detected change.

    Args:
        change_result: ChangeDetectionResult
        product: Product with changes
        website: Website configuration
        client: Client for webhook secret
        history_record_id: Product history record UUID
        crawl_log_id: Crawl log UUID
    """
    # Build webhook payloads based on change type
    event_id = None

    if change_result.price_changed and change_result.exceeded_threshold:
        # Price change event
        event = PriceChangeEvent(
            event_type="product.price_changed",
            event_id=history_record_id,  # Use history record ID as event ID
            timestamp=datetime.utcnow(),
            website=WebsiteInfo(
                id=website.id,
                base_url=website.base_url,
                name=website.base_url,  # Use base_url as name for now
            ),
            product=ProductInfo(
                id=product.id,
                url=product.original_url,
                name=product.product_name,
                extracted_product_id=product.extracted_product_id,
            ),
            change=PriceChangeDetails(
                type="price",
                old_value=change_result.old_price,
                new_value=change_result.new_price,
                currency=product.current_currency,
                change_pct=change_result.price_change_pct,
                absolute_change=change_result.new_price - change_result.old_price if change_result.new_price and change_result.old_price else 0,
                detected_at=datetime.utcnow(),
            ),
            metadata=PriceChangeMetadata(
                crawl_id=crawl_log_id,
                threshold_pct=website.price_change_threshold_pct,
                exceeded_threshold=True,
            ),
        )
        event_id = history_record_id

    if change_result.stock_changed:
        # Stock change event
        event = StockChangeEvent(
            event_type="product.stock_changed",
            event_id=history_record_id,  # Use history record ID as event ID
            timestamp=datetime.utcnow(),
            website=WebsiteInfo(
                id=website.id,
                base_url=website.base_url,
                name=website.base_url,
            ),
            product=ProductInfo(
                id=product.id,
                url=product.original_url,
                name=product.product_name,
                extracted_product_id=product.extracted_product_id,
            ),
            change=StockChangeDetails(
                type="stock",
                old_value=change_result.old_stock_status,
                new_value=change_result.new_stock_status,
                detected_at=datetime.utcnow(),
            ),
            metadata=StockChangeMetadata(
                crawl_id=crawl_log_id,
                price_at_change=product.current_price,
                currency=product.current_currency,
            ),
        )
        event_id = history_record_id

    # Send webhook delivery event to Inngest
    if event_id:
        await send_event(
            name="webhook.deliver",
            data={
                "website_id": str(website.id),
                "product_history_id": str(history_record_id),
                "target_url": website.webhook_endpoint_url,
                "webhook_secret": client.webhook_secret_current,
                "payload": event.model_dump(mode="json"),
                "event_type": event.event_type,
            },
        )
        logger.info(
            "Triggered webhook delivery event",
            extra={
                "event_id": str(event_id),
                "event_type": event.event_type,
                "product_id": str(product.id),
            },
        )


# Create Inngest function with cron trigger (T053)
@create_inngest_function(
    fn_id="scheduled-crawl",
    trigger={
        "cron": "0 2 * * *",  # Daily at 2 AM UTC
    },
)
async def scheduled_crawl_function(ctx, step):
    """
    Inngest function for scheduled product crawls.

    Runs daily at 2 AM UTC, processes all active websites.

    Steps:
    1. Fetch all active websites
    2. Process each website in parallel
    3. Crawl products, detect changes, trigger webhooks
    """
    # Step 1: Fetch active websites
    @step.run("fetch-active-websites")
    async def fetch_active_websites():
        """Fetch all active websites that need crawling."""
        async for db in get_db():
            query = select(MonitoredWebsite).where(
                MonitoredWebsite.status == "active",
            )
            result = await db.execute(query)
            websites = list(result.scalars().all())

            logger.info(
                "Fetched active websites for scheduled crawl",
                extra={"count": len(websites)},
            )

            return [str(website.id) for website in websites]

    website_ids = await fetch_active_websites()

    # Step 2: Process each website
    results = []
    for website_id_str in website_ids:
        @step.run(f"crawl-website-{website_id_str}")
        async def crawl_website():
            """Crawl products for a single website."""
            website_id = UUID(website_id_str)
            return await process_scheduled_crawl(website_id)

        result = await crawl_website()
        results.append(result)

    return {
        "websites_processed": len(website_ids),
        "results": results,
    }


# Export
__all__ = ["scheduled_crawl_function", "process_scheduled_crawl"]
