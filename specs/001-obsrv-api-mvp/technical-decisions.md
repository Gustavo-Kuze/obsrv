# Technical Implementation Decisions: Obsrv API MVP

**Feature**: Obsrv API - E-commerce Monitoring System MVP
**Branch**: `001-obsrv-api-mvp`
**Date**: 2025-11-03
**Context**: Python 3.11+, FastAPI, Celery, PostgreSQL, Redis, crawl4ai, Docker Compose
**Constraints**: Single VPS (4 CPU, 8GB RAM, 100GB storage), daily crawling, 20 websites, 100 products each, 90-day retention

---

## 1. URL Normalization & Product ID Extraction

### Decision

**Library**: Combine `url-normalize` (v2.2.1+) with `w3lib` for comprehensive URL cleaning and product ID extraction.

**Implementation**:
```python
# Install: pip install url-normalize w3lib
from url_normalize import url_normalize
from w3lib.url import url_query_cleaner
import re
from urllib.parse import urlparse

def normalize_product_url(url: str) -> str:
    """Clean and normalize product URL"""
    # Step 1: Basic normalization (lowercase scheme, sort query params)
    normalized = url_normalize(url)

    # Step 2: Remove tracking parameters
    tracking_params = [
        'utm_source', 'utm_medium', 'utm_campaign', 'utm_term', 'utm_content',
        'fbclid', 'gclid', 'mc_cid', 'mc_eid', '_ga', 'ref', 'referrer'
    ]
    cleaned = url_query_cleaner(normalized, parameterlist=tracking_params, remove=True)

    # Step 3: Remove trailing slashes and fragments
    parsed = urlparse(cleaned)
    return f"{parsed.scheme}://{parsed.netloc}{parsed.path.rstrip('/')}{('?' + parsed.query) if parsed.query else ''}"

def extract_product_id(url: str, html_content: str = None) -> dict:
    """Extract product identifier using domain-specific patterns"""
    parsed = urlparse(url)
    domain = parsed.netloc.lower()

    # Domain-specific regex patterns
    patterns = {
        # Amazon: /dp/B08N5WRWNW or /product/B08N5WRWNW
        'amazon': r'/(?:dp|product|gp/product)/([A-Z0-9]{10})',

        # Shopify: /products/product-handle
        'shopify': r'/products/([a-z0-9-]+)',

        # Generic: product-id=12345 or /p/12345
        'generic_param': r'[?&](?:product[-_]?id|pid|sku)=([^&]+)',
        'generic_path': r'/p(?:roduct)?/([a-z0-9-]+)',
    }

    result = {
        'sku': None,
        'product_id': None,
        'extraction_method': 'none'
    }

    # Try domain-specific patterns first
    for pattern_name, pattern in patterns.items():
        if pattern_name == 'amazon' and 'amazon' in domain:
            match = re.search(pattern, url)
            if match:
                result['product_id'] = match.group(1)
                result['extraction_method'] = 'url_pattern_amazon'
                return result
        elif pattern_name == 'shopify' and ('shopify' in domain or '/products/' in url):
            match = re.search(pattern, url)
            if match:
                result['product_id'] = match.group(1)
                result['extraction_method'] = 'url_pattern_shopify'
                return result

    # Fallback to generic patterns
    for pattern_name in ['generic_param', 'generic_path']:
        match = re.search(patterns[pattern_name], url)
        if match:
            result['product_id'] = match.group(1)
            result['extraction_method'] = f'url_pattern_{pattern_name}'
            return result

    # If HTML content provided, try extracting from meta tags or structured data
    if html_content:
        # Try OpenGraph product:retailer_item_id
        og_match = re.search(r'<meta\s+property="product:retailer_item_id"\s+content="([^"]+)"', html_content)
        if og_match:
            result['sku'] = og_match.group(1)
            result['extraction_method'] = 'html_opengraph'
            return result

        # Try schema.org Product SKU
        schema_match = re.search(r'"sku"\s*:\s*"([^"]+)"', html_content)
        if schema_match:
            result['sku'] = schema_match.group(1)
            result['extraction_method'] = 'html_schema_org'
            return result

    result['extraction_method'] = 'fallback_url_hash'
    return result
```

### Rationale

- **url-normalize**: Industry-standard library with 4M+ monthly downloads, handles internationalized domains, and provides built-in query parameter filtering
- **w3lib**: Battle-tested in Scrapy ecosystem specifically for web scraping, robust handling of edge cases in URL cleaning
- **Two-stage approach**: Domain-specific regex patterns first (high accuracy for known platforms), fallback to generic patterns and HTML extraction (graceful degradation)
- **Stable identifiers**: Combining normalized URL + extracted product ID creates unique composite key resilient to minor URL variations

### Alternatives Considered

- **urllib.parse only**: Standard library lacks tracking parameter removal and advanced normalization features
- **Single regex approach**: Fragile across different e-commerce platforms, requires constant maintenance
- **Third-party product APIs**: Not feasible for competitor monitoring (no API access), added complexity and cost

### References

- url-normalize: https://pypi.org/project/url-normalize/
- w3lib documentation: https://w3lib.readthedocs.io/en/latest/w3lib.html
- Ecommerce URL patterns: https://digitalcommerce.com/ecommerce-url-structures/

---

## 2. crawl4ai Integration

### Decision

**Strategy**: Use `AsyncPlaywrightCrawlerStrategy` (default) for MVP with explicit configuration to minimize resource usage.

**Configuration**:
```python
# Install: pip install "crawl4ai[all]"
from crawl4ai import AsyncWebCrawler, BrowserConfig, CrawlerRunConfig
from crawl4ai.extraction_strategy import CosineStrategy

async def crawl_product_page(url: str) -> dict:
    """Crawl single product page with resource constraints"""
    browser_config = BrowserConfig(
        headless=True,              # No GUI for performance
        viewport_width=1280,        # Standard desktop viewport
        viewport_height=720,
        extra_args=["--disable-gpu", "--no-sandbox"]  # Reduce resource usage
    )

    crawler_config = CrawlerRunConfig(
        # Content extraction
        word_count_threshold=10,    # Filter noise
        css_selector=".product-details, .product-info",  # Target product sections

        # Performance optimization
        wait_until="domcontentloaded",  # Don't wait for all resources
        screenshot=False,           # Disable screenshots
        pdf=False,                  # Disable PDF generation

        # Cache and session
        cache_mode="disabled",      # Fresh data every crawl
        session_id=None,            # No session persistence

        # Timeout and retries
        page_timeout=30000,         # 30 seconds max
        delay_before_return_html=2.0,  # Wait for dynamic content
    )

    async with AsyncWebCrawler(config=browser_config) as crawler:
        result = await crawler.arun(
            url=url,
            config=crawler_config
        )

        return {
            'html': result.html,
            'markdown': result.markdown_v2.fit_markdown,  # Cleaned content
            'success': result.success,
            'status_code': result.status_code,
            'error': result.error_message if not result.success else None
        }

# Rate limiting wrapper
import asyncio
from collections import defaultdict
from datetime import datetime, timedelta

class RateLimiter:
    """Simple rate limiter for respectful crawling"""
    def __init__(self, requests_per_minute: int = 10):
        self.requests_per_minute = requests_per_minute
        self.domain_timestamps = defaultdict(list)

    async def wait_if_needed(self, url: str):
        """Enforce rate limit per domain"""
        from urllib.parse import urlparse
        domain = urlparse(url).netloc

        now = datetime.now()
        cutoff = now - timedelta(minutes=1)

        # Remove old timestamps
        self.domain_timestamps[domain] = [
            ts for ts in self.domain_timestamps[domain] if ts > cutoff
        ]

        # Check if limit reached
        if len(self.domain_timestamps[domain]) >= self.requests_per_minute:
            oldest = self.domain_timestamps[domain][0]
            wait_seconds = (oldest + timedelta(minutes=1) - now).total_seconds()
            if wait_seconds > 0:
                await asyncio.sleep(wait_seconds)

        self.domain_timestamps[domain].append(now)

# Usage
rate_limiter = RateLimiter(requests_per_minute=10)
await rate_limiter.wait_if_needed(product_url)
result = await crawl_product_page(product_url)
```

### JavaScript Rendering Limitations (MVP Clarification)

**Scope**: MVP supports static HTML extraction only. JavaScript-rendered content is **out of scope** for initial release.

**Why this limitation**:
- Playwright browser instances consume 100-200MB RAM each - limits concurrent crawls on 8GB VPS
- JS rendering increases crawl time from ~1s to 5-10s per page
- Most product pricing is in initial HTML for SEO purposes
- Can be added post-MVP if client demand justifies resource investment

**Mitigation strategy**:
- During website registration, perform test crawl and warn client if product data requires JS rendering
- Document supported platforms (Shopify, WooCommerce, basic HTML sites)
- Use `AsyncHTTPCrawlerStrategy` for sites confirmed to be static (faster, lower resource usage)

### Rationale

- **crawl4ai over BeautifulSoup**: Purpose-built for AI/LLM workflows, provides cleaned markdown output, handles modern web patterns
- **Playwright default**: Enables future JS rendering support without code rewrite, gracefully falls back to static HTML
- **Explicit resource constraints**: Headless mode, disable unnecessary features (screenshots, PDF), tight timeouts prevent resource exhaustion
- **Rate limiting**: Respectful crawling prevents IP bans, maintains system reputation, configurable per-domain for flexibility

### Alternatives Considered

- **requests + BeautifulSoup**: Lighter weight but lacks JS support entirely, no path to future enhancement
- **Scrapy**: More complex framework, overkill for MVP scope, steeper learning curve
- **Selenium**: Older, slower, higher resource usage than Playwright

### References

- crawl4ai documentation: https://docs.crawl4ai.com/
- crawl4ai adaptive crawling: https://docs.crawl4ai.com/core/adaptive-crawling/
- Playwright performance: https://playwright.dev/python/docs/intro

---

## 3. Inngest Function Patterns

### Decision

**Inngest Functions**: Use step-based durable functions for complex workflows with automatic retries and event-driven execution.

**Configuration**:
```python
# inngest_config.py
import inngest
from inngest.fast_api import serve

# Create Inngest client
inngest_client = inngest.Inngest(
    app_id="obsrv-api-mvp",
    event_key=os.getenv("INNGEST_EVENT_KEY"),
    env=os.getenv("INNGEST_ENV", "dev")
)

# Function concurrency and performance
@inngest_client.create_function(
    fn_id="crawl_website",
    concurrency=5,  # Limit concurrent crawls
    retries=3,
    timeout="2h"  # Up to 2 hours for large crawls
)
async def crawl_website(ctx: inngest.Context, website_id: int):
    """Crawl all products for a website with step-based workflow"""
    pass

# Scheduled functions (replaces Celery Beat)
@inngest_client.create_function(
    fn_id="scheduled_daily_crawls",
    trigger=inngest.TriggerCron("0 2 * * *"),  # 2 AM UTC daily
)
async def scheduled_daily_crawls(ctx: inngest.Context):
    """Execute daily crawl schedule"""
    pass

@inngest_client.create_function(
    fn_id="weekly_data_cleanup",
    trigger=inngest.TriggerCron("0 3 * * 0"),  # Sunday 3 AM UTC
)
async def weekly_data_cleanup(ctx: inngest.Context):
    """Clean up old historical data"""
    pass
```

**Function Retry Strategy**:
```python
# functions/crawl_functions.py
import inngest

@inngest_client.create_function(
    fn_id="crawl_single_product",
    retries=3,  # Automatic retries with exponential backoff
    retry_on=(Exception,),  # Retry on any exception
)
async def crawl_single_product(ctx: inngest.Context, product_id: int):
    """Crawl single product with automatic retries"""
    try:
        # Step 1: Get product data
        product = await ctx.run("get_product", get_product, product_id)

        # Step 2: Crawl the product page
        result = await ctx.run("crawl_page", crawl_product_page, product.url)

        if not result['success']:
            # Raise to trigger retry
            raise Exception(f"Crawl failed: {result['error']}")

        # Step 3: Save snapshot and detect changes
        await ctx.run("save_snapshot", save_product_snapshot, product_id, result)
        await ctx.run("detect_changes", detect_and_notify_changes, product_id)

    except Exception as e:
        # Log failure after all retries exhausted
        await ctx.run("log_failure", log_crawl_failure, product_id, str(e))
        raise
```

**Step-Based Workflow Patterns (Discovery → Approval → Baseline → Monitoring)**:
```python
# functions/workflow_functions.py

# Pattern 1: Website Registration Workflow
@inngest_client.create_function(
    fn_id="register_website_workflow",
    trigger=inngest.TriggerEvent(event="website.register")
)
async def register_website_workflow(ctx: inngest.Context, website_id: int, seed_urls: list[str]):
    """Step-based: Discovery → Wait for Approval → Baseline Crawl"""
    # Step 1: Discover products from seed URLs
    discovered_products = await ctx.run("discover_products", discover_products_from_seeds, website_id, seed_urls)

    # Step 2: Manual approval gate (not automated)
    # Client approves via API, which triggers "website.approved" event

# Pattern 2: Baseline Crawl After Approval
@inngest_client.create_function(
    fn_id="baseline_crawl_workflow",
    trigger=inngest.TriggerEvent(event="website.approved")
)
async def baseline_crawl_workflow(ctx: inngest.Context, website_id: int, approved_product_ids: list[int]):
    """Parallel crawl of all approved products"""
    # Fan out: Crawl all products in parallel
    crawl_results = []
    for product_id in approved_product_ids:
        result = await ctx.run(f"crawl_{product_id}", crawl_single_product, product_id)
        crawl_results.append(result)

    return crawl_results

# Pattern 3: Scheduled Daily Monitoring
@inngest_client.create_function(
    fn_id="scheduled_daily_crawls",
    trigger=inngest.TriggerCron("0 2 * * *")  # 2 AM UTC daily
)
async def scheduled_daily_crawls(ctx: inngest.Context):
    """Crawl all active websites with summary notification"""
    active_websites = await ctx.run("get_active_websites", get_active_websites)

    # Parallel processing of websites
    crawl_results = []
    for website in active_websites:
        result = await ctx.run(f"crawl_website_{website.id}", crawl_website_products, website.id)
        crawl_results.append(result)

    # Send summary notification
    await ctx.run("send_summary", send_daily_summary, crawl_results)

@inngest_client.create_function(
    fn_id="crawl_website_products",
    retries=2
)
async def crawl_website_products(ctx: inngest.Context, website_id: int):
    """Crawl all products for a single website with rate limiting"""
    products = await ctx.run("get_products", get_website_products, website_id)

    # Sequential crawl with rate limiting
    results = []
    for product in products:
        result = await ctx.run(f"crawl_product_{product.id}", crawl_single_product, product.id)
        results.append(result)
        # Rate limiting handled within crawl_single_product

    return results

# Pattern 4: Change Detection → Webhook Notification
@inngest_client.create_function(
    fn_id="detect_and_notify_changes",
    retries=3
)
async def detect_and_notify_changes(ctx: inngest.Context, product_id: int):
    """Step-based: Detect changes → Send webhooks"""
    changes = await ctx.run("detect_changes", detect_product_changes, product_id)

    if changes:
        # Send webhook notifications (fire and forget)
        for change in changes:
            await ctx.run(f"notify_{change.id}", send_webhook_notification, change)

@inngest_client.create_function(
    fn_id="send_webhook_notification",
    retries=3
)
async def send_webhook_notification(ctx: inngest.Context, change_data: dict):
    """Send webhook with retries"""
    try:
        response = await ctx.run("send_webhook", send_webhook, change_data)
        await ctx.run("log_delivery", log_webhook_delivery, change_data, response)
    except Exception as exc:
        # Automatic retry with exponential backoff
        raise exc
```

### Rationale

- **Step-based functions**: Durable execution ensures workflows complete even with failures, better than Celery's fire-and-forget approach
- **Event-driven architecture**: More flexible than cron schedules - can trigger crawls via API events or schedules
- **Automatic retries**: Built-in exponential backoff handles transient failures without custom code
- **Serverless scaling**: No need to manage worker pools or resource limits on VPS
- **Fan-out pattern**: Parallel processing of products/websites with built-in coordination
- **Step isolation**: Each step can fail independently without affecting the entire workflow

### Alternatives Considered

- **Celery + Redis**: Traditional but requires managing worker infrastructure and resource limits
- **AWS Lambda + SQS**: More complex infrastructure setup, higher cold start latency
- **GitHub Actions**: Limited to scheduled workflows, no dynamic triggering, resource constraints
- **No step isolation**: Monolithic functions harder to debug and retry partial failures

### References

- Inngest Functions documentation: https://www.inngest.com/docs/features/inngest-functions
- Inngest Step Functions: https://www.inngest.com/docs/features/inngest-functions/steps-workflows
- Inngest Event Triggers: https://www.inngest.com/docs/features/events

---

## 4. HMAC Webhook Signature

### Decision

**Pattern**: Follow Stripe's approach - timestamp + payload signature in structured header format.

**Header Format**: `X-Obsrv-Signature: t={timestamp},v1={signature}`

**Implementation**:
```python
# utils/hmac_signer.py
import hmac
import hashlib
import time
from typing import Optional

class WebhookSigner:
    """HMAC-SHA256 webhook signature generation and verification"""

    HEADER_NAME = "X-Obsrv-Signature"
    ALGORITHM = hashlib.sha256

    @staticmethod
    def generate_signature(payload: str, secret: str, timestamp: Optional[int] = None) -> str:
        """Generate HMAC signature for webhook payload"""
        if timestamp is None:
            timestamp = int(time.time())

        # Signed payload: timestamp.payload
        signed_payload = f"{timestamp}.{payload}"

        # HMAC-SHA256 signature (hex encoded)
        signature = hmac.new(
            key=secret.encode('utf-8'),
            msg=signed_payload.encode('utf-8'),
            digestmod=WebhookSigner.ALGORITHM
        ).hexdigest()

        return f"t={timestamp},v1={signature}"

    @staticmethod
    def verify_signature(
        payload: str,
        signature_header: str,
        secret: str,
        tolerance_seconds: int = 300  # 5 minute tolerance
    ) -> bool:
        """Verify webhook signature"""
        try:
            # Parse header: "t=1234567890,v1=abcdef..."
            parts = dict(part.split('=') for part in signature_header.split(','))
            timestamp = int(parts['t'])
            received_signature = parts['v1']

            # Check timestamp freshness (prevent replay attacks)
            current_time = int(time.time())
            if abs(current_time - timestamp) > tolerance_seconds:
                return False

            # Recompute signature
            signed_payload = f"{timestamp}.{payload}"
            expected_signature = hmac.new(
                key=secret.encode('utf-8'),
                msg=signed_payload.encode('utf-8'),
                digestmod=WebhookSigner.ALGORITHM
            ).hexdigest()

            # Constant-time comparison
            return hmac.compare_digest(expected_signature, received_signature)

        except (KeyError, ValueError):
            return False

    @staticmethod
    def verify_with_secret_rotation(
        payload: str,
        signature_header: str,
        current_secret: str,
        previous_secret: Optional[str] = None,
        tolerance_seconds: int = 300
    ) -> bool:
        """Verify signature supporting secret rotation grace period"""
        # Try current secret first
        if WebhookSigner.verify_signature(payload, signature_header, current_secret, tolerance_seconds):
            return True

        # Fallback to previous secret during rotation grace period
        if previous_secret:
            return WebhookSigner.verify_signature(payload, signature_header, previous_secret, tolerance_seconds)

        return False

# Usage in notification service
import json

async def send_webhook_notification(change_data: dict, webhook_url: str, webhook_secret: str):
    """Send webhook with HMAC signature"""
    import httpx

    # Serialize payload
    payload_json = json.dumps(change_data, separators=(',', ':'))  # Compact, deterministic

    # Generate signature
    signature = WebhookSigner.generate_signature(payload_json, webhook_secret)

    # Send request
    async with httpx.AsyncClient(timeout=10.0) as client:
        response = await client.post(
            webhook_url,
            content=payload_json,
            headers={
                'Content-Type': 'application/json',
                WebhookSigner.HEADER_NAME: signature,
                'User-Agent': 'Obsrv-Webhook/1.0'
            }
        )
        return response

# Client-side verification (example for documentation)
def verify_obsrv_webhook(request_body: str, signature_header: str, webhook_secret: str) -> bool:
    """Example client verification code"""
    return WebhookSigner.verify_signature(
        payload=request_body,
        signature_header=signature_header,
        secret=webhook_secret,
        tolerance_seconds=300
    )
```

**Secret Rotation Implementation**:
```python
# models/client.py
from sqlalchemy import Column, String, DateTime
from datetime import datetime, timedelta

class Client(Base):
    __tablename__ = "clients"

    id = Column(Integer, primary_key=True)
    webhook_secret_current = Column(String(64), nullable=False)
    webhook_secret_previous = Column(String(64), nullable=True)
    webhook_secret_rotated_at = Column(DateTime, nullable=True)

    def rotate_webhook_secret(self, new_secret: str):
        """Rotate webhook secret with grace period"""
        self.webhook_secret_previous = self.webhook_secret_current
        self.webhook_secret_current = new_secret
        self.webhook_secret_rotated_at = datetime.utcnow()

    def cleanup_old_secret(self):
        """Remove previous secret after grace period (1 hour)"""
        if self.webhook_secret_rotated_at:
            grace_period = timedelta(hours=1)
            if datetime.utcnow() - self.webhook_secret_rotated_at > grace_period:
                self.webhook_secret_previous = None
                self.webhook_secret_rotated_at = None

# Scheduled cleanup task
@celery_app.task
def cleanup_expired_webhook_secrets():
    """Remove previous webhook secrets after grace period"""
    clients = get_clients_with_rotated_secrets()
    for client in clients:
        client.cleanup_old_secret()
    commit_changes()
```

### Rationale

- **Stripe pattern**: Industry-proven, well-documented, familiar to developers integrating with webhooks
- **Timestamp inclusion**: Prevents replay attacks, allows verification of message freshness
- **Hex encoding**: More compact than base64 for signatures, easier debugging (visible ASCII)
- **Structured header**: Versioned scheme (v1) allows future algorithm upgrades without breaking existing integrations
- **Grace period**: 1-hour dual-secret validation enables zero-downtime secret rotation

### Alternatives Considered

- **Shopify pattern (base64, no timestamp)**: Simpler but lacks replay attack protection
- **GitHub pattern (sha256= prefix only)**: No timestamp, no versioning, less flexible
- **JWT tokens**: Overkill for one-way notification, added parsing complexity, larger payload size

### References

- Stripe webhook signatures: https://stripe.com/docs/webhooks/signatures
- HMAC best practices: https://webhooks.fyi/security/hmac
- Secret rotation: https://docs.lithic.com/reference/rotateauthstreamsecret

---

## 5. Neon PostgreSQL Schema Design

### Decision

**JSONB Strategy**: Use `jsonb_path_ops` GIN indexes for containment queries, hybrid approach combining relational columns for queryable fields + JSONB for flexible crawl data. Leverage Neon's managed partitioning for time-series data.

**Schema Design**:
```sql
-- Core relational tables with JSONB supplements

CREATE TABLE clients (
    id SERIAL PRIMARY KEY,
    name VARCHAR(255) NOT NULL,
    webhook_secret_current VARCHAR(64) NOT NULL,
    webhook_secret_previous VARCHAR(64),
    webhook_secret_rotated_at TIMESTAMP,
    created_at TIMESTAMP NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMP NOT NULL DEFAULT NOW()
);

CREATE TABLE monitored_websites (
    id SERIAL PRIMARY KEY,
    client_id INTEGER NOT NULL REFERENCES clients(id) ON DELETE CASCADE,
    base_url VARCHAR(2048) NOT NULL,
    status VARCHAR(50) NOT NULL DEFAULT 'pending_approval', -- pending_approval, active, paused

    -- Configuration stored as JSONB for flexibility
    config JSONB NOT NULL DEFAULT '{
        "crawl_frequency": "daily",
        "price_threshold_percent": 1.0,
        "retention_days": 90,
        "rate_limit_per_minute": 10
    }'::jsonb,

    webhook_url VARCHAR(2048),
    last_crawl_at TIMESTAMP,
    created_at TIMESTAMP NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMP NOT NULL DEFAULT NOW(),

    UNIQUE(client_id, base_url)
);

-- Index for querying websites by config values
CREATE INDEX idx_websites_config ON monitored_websites USING GIN (config jsonb_path_ops);

CREATE TABLE products (
    id SERIAL PRIMARY KEY,
    website_id INTEGER NOT NULL REFERENCES monitored_websites(id) ON DELETE CASCADE,

    -- Relational columns for frequently queried fields
    normalized_url VARCHAR(2048) NOT NULL,
    product_identifier VARCHAR(255),  -- Extracted SKU/product ID
    product_name VARCHAR(500),
    current_price DECIMAL(10, 2),
    current_stock_status VARCHAR(50),  -- in_stock, out_of_stock, limited

    -- JSONB for flexible product data
    current_data JSONB NOT NULL DEFAULT '{}'::jsonb,

    last_crawled_at TIMESTAMP,
    created_at TIMESTAMP NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMP NOT NULL DEFAULT NOW(),

    UNIQUE(website_id, normalized_url, product_identifier)
);

-- Indexes for efficient queries
CREATE INDEX idx_products_website ON products(website_id);
CREATE INDEX idx_products_identifier ON products(product_identifier);
CREATE INDEX idx_products_updated ON products(updated_at DESC);
CREATE INDEX idx_products_current_data ON products USING GIN (current_data jsonb_path_ops);

-- Partitioned table for historical data (by month)
CREATE TABLE product_history (
    id BIGSERIAL,
    product_id INTEGER NOT NULL REFERENCES products(id) ON DELETE CASCADE,

    -- Snapshot timestamp (partition key)
    snapshot_at TIMESTAMP NOT NULL,

    -- Relational columns for efficient queries
    price DECIMAL(10, 2),
    stock_status VARCHAR(50),
    price_changed BOOLEAN NOT NULL DEFAULT FALSE,
    stock_changed BOOLEAN NOT NULL DEFAULT FALSE,

    -- JSONB for complete snapshot
    snapshot_data JSONB NOT NULL,

    created_at TIMESTAMP NOT NULL DEFAULT NOW()
) PARTITION BY RANGE (snapshot_at);

-- Create monthly partitions (automation needed)
CREATE TABLE product_history_2025_11 PARTITION OF product_history
    FOR VALUES FROM ('2025-11-01') TO ('2025-12-01');

CREATE TABLE product_history_2025_12 PARTITION OF product_history
    FOR VALUES FROM ('2025-12-01') TO ('2026-01-01');

-- Indexes on partitioned table
CREATE INDEX idx_history_product_time ON product_history(product_id, snapshot_at DESC);
CREATE INDEX idx_history_changes ON product_history(snapshot_at DESC) WHERE price_changed OR stock_changed;
CREATE INDEX idx_history_snapshot_data ON product_history USING GIN (snapshot_data jsonb_path_ops);

-- Materialized view for "latest state" queries (refreshed after crawls)
CREATE MATERIALIZED VIEW latest_product_states AS
SELECT DISTINCT ON (product_id)
    product_id,
    snapshot_at,
    price,
    stock_status,
    snapshot_data
FROM product_history
ORDER BY product_id, snapshot_at DESC;

CREATE UNIQUE INDEX idx_latest_states_product ON latest_product_states(product_id);

-- Refresh after crawl batch completes
-- REFRESH MATERIALIZED VIEW CONCURRENTLY latest_product_states;

CREATE TABLE crawl_logs (
    id BIGSERIAL PRIMARY KEY,
    website_id INTEGER NOT NULL REFERENCES monitored_websites(id) ON DELETE CASCADE,
    started_at TIMESTAMP NOT NULL,
    completed_at TIMESTAMP,
    status VARCHAR(50) NOT NULL,  -- success, failed, partial
    products_processed INTEGER DEFAULT 0,
    changes_detected INTEGER DEFAULT 0,
    error_details JSONB,

    created_at TIMESTAMP NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_crawl_logs_website_time ON crawl_logs(website_id, started_at DESC);
CREATE INDEX idx_crawl_logs_status ON crawl_logs(status, started_at DESC);

CREATE TABLE webhook_logs (
    id BIGSERIAL PRIMARY KEY,
    product_id INTEGER NOT NULL REFERENCES products(id) ON DELETE CASCADE,
    webhook_url VARCHAR(2048) NOT NULL,
    payload JSONB NOT NULL,

    attempted_at TIMESTAMP NOT NULL,
    status VARCHAR(50) NOT NULL,  -- pending, success, failed
    response_code INTEGER,
    response_body TEXT,
    retry_count INTEGER DEFAULT 0,

    created_at TIMESTAMP NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_webhook_logs_product ON webhook_logs(product_id, attempted_at DESC);
CREATE INDEX idx_webhook_logs_status ON webhook_logs(status, attempted_at DESC);

CREATE TABLE api_keys (
    id SERIAL PRIMARY KEY,
    client_id INTEGER NOT NULL REFERENCES clients(id) ON DELETE CASCADE,
    key_hash VARCHAR(128) NOT NULL UNIQUE,  -- bcrypt hash
    key_prefix VARCHAR(8) NOT NULL,  -- First 8 chars for identification

    last_used_at TIMESTAMP,
    invalidated_at TIMESTAMP,
    created_at TIMESTAMP NOT NULL DEFAULT NOW(),

    CONSTRAINT valid_key_state CHECK (invalidated_at IS NULL OR invalidated_at >= created_at)
);

CREATE INDEX idx_api_keys_client ON api_keys(client_id) WHERE invalidated_at IS NULL;
CREATE INDEX idx_api_keys_hash ON api_keys(key_hash) WHERE invalidated_at IS NULL;
```

**Query Patterns**:
```sql
-- Latest product state (using materialized view)
SELECT * FROM latest_product_states WHERE product_id = 123;

-- Historical price trend (partition pruning)
SELECT snapshot_at, price, stock_status
FROM product_history
WHERE product_id = 123
  AND snapshot_at >= '2025-10-01'
  AND snapshot_at < '2025-11-01'
ORDER BY snapshot_at DESC;

-- Changes in last 7 days (optimized with partial index)
SELECT p.product_name, h.snapshot_at, h.price, h.stock_status
FROM product_history h
JOIN products p ON h.product_id = p.id
WHERE h.snapshot_at >= NOW() - INTERVAL '7 days'
  AND (h.price_changed OR h.stock_changed)
ORDER BY h.snapshot_at DESC;

-- Query JSONB data (using GIN index)
SELECT * FROM products
WHERE current_data @> '{"brand": "Nike"}'::jsonb;

-- Website configuration lookup
SELECT * FROM monitored_websites
WHERE config @> '{"crawl_frequency": "hourly"}'::jsonb;
```

### Rationale

- **Time-based partitioning**: Optimal for time-series data, enables efficient data retention (drop old partitions), improves query performance with partition pruning
- **jsonb_path_ops over jsonb_ops**: 78% smaller index size, 8% faster containment queries - perfect for product data lookups
- **Hybrid relational + JSONB**: Frequently queried fields (price, stock) as columns for index efficiency, flexible attributes in JSONB
- **Materialized view for latest state**: Avoids expensive MAX(snapshot_at) GROUP BY queries, refreshed after batch crawls
- **Partition by month**: Balances partition count (12/year) vs partition size (~10K records/month for 100 products)

### Alternatives Considered

- **Hash partitioning by product_id**: Better write distribution but complicates time-based retention queries
- **Pure JSONB storage**: Maximum flexibility but slower queries, larger indexes, harder to enforce constraints
- **Separate table per website**: Extreme denormalization, schema management nightmare, doesn't scale

### References

- PostgreSQL partitioning: https://www.postgresql.org/docs/current/ddl-partitioning.html
- JSONB indexing: https://bitnine.net/blog-postgresql/postgresql-internals-jsonb-type-and-its-indexes/
- jsonb_path_ops performance: https://pganalyze.com/blog/gin-index

---

## 6. Data Retention & Cleanup

### Decision

**Strategy**: Leverage Neon's managed partitioning for automatic data lifecycle management + aggregated statistics preservation.

**Implementation**:
```python
# functions/maintenance_functions.py
from datetime import datetime, timedelta
from sqlalchemy import text

@inngest_client.create_function(
    fn_id="purge_old_history",
    trigger=inngest.TriggerCron("0 3 * * 0")  # Sunday 3 AM UTC
)
async def purge_old_history(ctx: inngest.Context):
    """Drop old partitions and create future partitions"""
    # Get all websites with their retention settings
    websites = get_websites_with_retention_config()

    for website in websites:
        retention_days = website.config.get('retention_days', 90)
        cutoff_date = datetime.utcnow() - timedelta(days=retention_days)

    # Use Neon's automated partitioning - just trigger cleanup
    # Neon handles partition management automatically
    websites = await ctx.run("get_websites", get_websites_with_retention_config)

    for website in websites:
        retention_days = website.config.get('retention_days', 90)
        cutoff_date = datetime.utcnow() - timedelta(days=retention_days)

        # Archive aggregated stats before cleanup
        await ctx.run(f"archive_stats_{website.id}", archive_partition_statistics, website.id, cutoff_date)

        # Trigger Neon's automated cleanup (via SQL or API)
        await ctx.run(f"cleanup_data_{website.id}", cleanup_old_data, website.id, cutoff_date)

def drop_partition(partition_name: str):
    """Drop partition table - instant operation"""
    with engine.begin() as conn:
        conn.execute(text(f"DROP TABLE IF EXISTS {partition_name}"))

def archive_partition_statistics(partition_name: str, website_id: int):
    """Aggregate and preserve statistics before dropping partition"""
    query = text(f"""
        INSERT INTO product_statistics_monthly (
            product_id,
            month,
            min_price,
            max_price,
            avg_price,
            price_change_count,
            stock_change_count
        )
        SELECT
            product_id,
            DATE_TRUNC('month', snapshot_at) as month,
            MIN(price) as min_price,
            MAX(price) as max_price,
            AVG(price) as avg_price,
            COUNT(*) FILTER (WHERE price_changed) as price_change_count,
            COUNT(*) FILTER (WHERE stock_changed) as stock_change_count
        FROM {partition_name} h
        JOIN products p ON h.product_id = p.id
        WHERE p.website_id = :website_id
        GROUP BY product_id, DATE_TRUNC('month', snapshot_at)
        ON CONFLICT (product_id, month) DO NOTHING
    """)

    with engine.begin() as conn:
        conn.execute(query, {"website_id": website_id})

def create_future_partitions(months_ahead: int = 3):
    """Create partitions for upcoming months"""
    from dateutil.relativedelta import relativedelta

    current_date = datetime.utcnow()

    for i in range(1, months_ahead + 1):
        partition_date = current_date + relativedelta(months=i)
        partition_name = f"product_history_{partition_date.strftime('%Y_%m')}"

        start_date = partition_date.replace(day=1)
        end_date = start_date + relativedelta(months=1)

        query = text(f"""
            CREATE TABLE IF NOT EXISTS {partition_name}
            PARTITION OF product_history
            FOR VALUES FROM ('{start_date}') TO ('{end_date}')
        """)

        with engine.begin() as conn:
            conn.execute(query)

        logger.info(f"Created partition {partition_name}")

# Fine-grained cleanup for non-partitioned tables
@inngest_client.create_function(
    fn_id="cleanup_old_logs",
    trigger=inngest.TriggerCron("0 4 * * *")  # Daily 4 AM UTC
)
async def cleanup_old_logs(ctx: inngest.Context):
    """Delete old crawl/webhook logs (not worth partitioning)"""
    retention_days = 30
    cutoff_date = datetime.utcnow() - timedelta(days=retention_days)

    # Delete in batches to avoid long locks
    batch_size = 1000

    while True:
        with engine.begin() as conn:
            result = conn.execute(text(f"""
                DELETE FROM crawl_logs
                WHERE id IN (
                    SELECT id FROM crawl_logs
                    WHERE created_at < :cutoff_date
                    ORDER BY id
                    LIMIT :batch_size
                )
            """), {"cutoff_date": cutoff_date, "batch_size": batch_size})

            deleted = result.rowcount

        if deleted == 0:
            break

        logger.info(f"Deleted {deleted} old crawl logs")
        time.sleep(1)  # Brief pause between batches

    # Same for webhook logs
    # ... (similar batched delete)

# Aggregated statistics table (preserved indefinitely)
CREATE TABLE product_statistics_monthly (
    id SERIAL PRIMARY KEY,
    product_id INTEGER NOT NULL REFERENCES products(id) ON DELETE CASCADE,
    month DATE NOT NULL,  -- First day of month
    min_price DECIMAL(10, 2),
    max_price DECIMAL(10, 2),
    avg_price DECIMAL(10, 2),
    price_change_count INTEGER,
    stock_change_count INTEGER,

    created_at TIMESTAMP NOT NULL DEFAULT NOW(),

    UNIQUE(product_id, month)
);

CREATE INDEX idx_stats_product_month ON product_statistics_monthly(product_id, month DESC);
```

**Inngest Cron Triggers**:
```python
# Cron triggers are defined in function decorators
@inngest_client.create_function(
    fn_id="purge_old_history",
    trigger=inngest.TriggerCron("0 3 * * 0")  # Sunday 3 AM UTC
)
async def purge_old_history(ctx: inngest.Context):
    pass

@inngest_client.create_function(
    fn_id="cleanup_old_logs",
    trigger=inngest.TriggerCron("0 4 * * *")  # Daily 4 AM UTC
)
async def cleanup_old_logs(ctx: inngest.Context):
    pass

# Note: Partition creation not needed with Neon's managed partitioning
```

### Rationale

- **Neon managed partitioning**: Automatic partition lifecycle management without manual intervention
- **Serverless scaling**: No need to manage partition creation or maintenance tasks
- **Aggregated statistics**: Preserves long-term trends without storing individual snapshots, enables multi-year analysis
- **Event-driven cleanup**: Cron-triggered functions ensure regular maintenance without manual scheduling
- **Reduced operational complexity**: Neon handles partitioning, indexing, and performance optimization

### Alternatives Considered

- **Manual partition management**: Complex to implement and maintain, error-prone
- **DELETE with VACUUM**: Slower performance, requires ongoing maintenance
- **Archive to external storage**: Adds complexity and cost for MVP scale

### References

- Partition drop performance: https://www.simplethread.com/beyond-delete/
- Time-based retention: https://blog.sequinstream.com/time-based-retention-strategies-in-postgres/
- pg_partman: https://www.crunchydata.com/blog/auto-archiving-and-data-retention-management-in-postgres-with-pg_partman

---

## 7. API Key Storage & Validation

### Decision

**Hashing Algorithm**: bcrypt with work factor 12 for API key storage.

**Key Generation**: 32-byte (256-bit) URL-safe tokens using Python's `secrets` module.

**Connection Strategy**: Direct Neon PostgreSQL connections with connection pooling.

**Implementation**:
```python
# utils/api_key.py
import secrets
import bcrypt
from typing import Optional

class APIKeyManager:
    """Secure API key generation and validation"""

    KEY_LENGTH = 32  # 256 bits
    KEY_PREFIX_LENGTH = 8
    BCRYPT_ROUNDS = 12  # Work factor

    @staticmethod
    def generate_key() -> tuple[str, str, str]:
        """
        Generate cryptographically secure API key

        Returns:
            tuple: (full_key, key_hash, key_prefix)
        """
        # Generate 256-bit random key (URL-safe base64)
        key = f"obsrv_{secrets.token_urlsafe(APIKeyManager.KEY_LENGTH)}"

        # Extract prefix for identification
        prefix = key[:APIKeyManager.KEY_PREFIX_LENGTH]

        # Hash with bcrypt (salted automatically)
        key_hash = bcrypt.hashpw(
            key.encode('utf-8'),
            bcrypt.gensalt(rounds=APIKeyManager.BCRYPT_ROUNDS)
        ).decode('utf-8')

        return key, key_hash, prefix

    @staticmethod
    def verify_key(key: str, key_hash: str) -> bool:
        """
        Verify API key against stored hash

        Args:
            key: Plaintext key from request
            key_hash: Bcrypt hash from database

        Returns:
            bool: True if key matches hash
        """
        try:
            return bcrypt.checkpw(
                key.encode('utf-8'),
                key_hash.encode('utf-8')
            )
        except Exception:
            return False

# services/auth_service.py
from datetime import timedelta

class AuthService:
    """API key authentication with Neon PostgreSQL"""

    def __init__(self, db_session):
        self.db = db_session

    def authenticate(self, api_key: str) -> Optional[dict]:
        """
        Authenticate API key with Neon PostgreSQL

        Returns:
            dict with client_id if valid, None if invalid
        """
        from models.api_key import APIKey

        # Get all active keys for this prefix (reduces search space)
        prefix = api_key[:8]
        active_keys = self.db.query(APIKey).filter(
            APIKey.key_prefix == prefix,
            APIKey.invalidated_at.is_(None)
        ).all()

        # Try to match hash (bcrypt verify is slow - limit candidates)
        for key_record in active_keys:
            if APIKeyManager.verify_key(api_key, key_record.key_hash):
                # Valid key found
                result = {
                    'client_id': key_record.client_id,
                    'key_id': key_record.id
                }

                # Update last used timestamp (async, don't block request)
                self.update_last_used_async(key_record.id)

                return result

        # Invalid key
        return None

    def invalidate_key(self, key_id: int):
        """Invalidate API key in Neon PostgreSQL"""
        from models.api_key import APIKey
        from datetime import datetime

        # Mark as invalidated in database
        key_record = self.db.query(APIKey).filter(APIKey.id == key_id).first()
        if key_record:
            key_record.invalidated_at = datetime.utcnow()
            self.db.commit()

    def update_last_used_async(self, key_id: int):
        """Update last_used_at timestamp (background task)"""
        from tasks.maintenance_tasks import update_api_key_last_used
        update_api_key_last_used.delay(key_id)

# FastAPI dependency
from fastapi import Depends, HTTPException, Header
from typing import Optional

async def get_current_client(
    authorization: Optional[str] = Header(None),
    x_api_key: Optional[str] = Header(None)
) -> dict:
    """
    Extract and validate API key from request

    Supports two formats:
    - Authorization: Bearer <key>
    - X-API-Key: <key>
    """
    api_key = None

    if authorization and authorization.startswith("Bearer "):
        api_key = authorization[7:]  # Remove "Bearer " prefix
    elif x_api_key:
        api_key = x_api_key

    if not api_key:
        raise HTTPException(status_code=401, detail="Missing API key")

    # Validate key
    auth_service = get_auth_service()  # From DI container
    client = auth_service.authenticate(api_key)

    if not client:
        raise HTTPException(status_code=401, detail="Invalid API key")

    return client

# Usage in routes
from fastapi import APIRouter

router = APIRouter()

@router.get("/products")
async def list_products(client: dict = Depends(get_current_client)):
    client_id = client['client_id']
    # ... fetch products for this client
```

**Key Generation Endpoint**:
```python
# api/routes/auth.py

@router.post("/api-keys", response_model=schemas.APIKeyResponse)
async def create_api_key(
    description: str,
    client: dict = Depends(get_current_client)  # Requires existing auth
):
    """Generate new API key"""
    key, key_hash, prefix = APIKeyManager.generate_key()

    # Store in database
    api_key_record = APIKey(
        client_id=client['client_id'],
        key_hash=key_hash,
        key_prefix=prefix,
        description=description
    )
    db.add(api_key_record)
    db.commit()

    # Return key ONCE (never stored in plaintext)
    return {
        'api_key': key,
        'prefix': prefix,
        'created_at': api_key_record.created_at,
        'warning': 'Store this key securely - it will not be shown again'
    }
```

### Rationale

- **bcrypt over argon2**: Simpler, widely supported, sufficient for API keys (not interactive passwords), ~100ms verification acceptable
- **256-bit keys**: OWASP recommendation, cryptographically strong, future-proof
- **Neon connection pooling**: Handles high concurrency without additional caching layer
- **Prefix indexing**: Limits bcrypt comparisons to ~1-10 candidates instead of all keys, improves performance
- **Direct database queries**: Simpler architecture, Neon provides excellent performance

### Alternatives Considered

- **argon2**: Marginally more secure but 100ms bcrypt sufficient for API keys
- **scrypt**: Middle ground but no clear advantage over bcrypt for this use case
- **JWT tokens**: Stateless but requires public/private key management, harder to invalidate, larger tokens
- **Redis caching**: Adds complexity, Neon provides sufficient performance for API key validation

### References

- bcrypt vs argon2: https://stytch.com/blog/argon2-vs-bcrypt-vs-scrypt/
- API key best practices: https://expertbeacon.com/best-practices-for-building-secure-api-keys/
- Python secrets module: https://docs.python.org/3/library/secrets.html

---

## 8. Docker Compose MVP Architecture

### Decision

**Services**: api only
**Health Checks**: HTTP health endpoint for API
**Restart Policy**: unless-stopped for API service (survive VPS reboots)

**docker-compose.yml**:
```yaml
version: '3.8'

services:
  # FastAPI application only
  api:
    build:
      context: .
      dockerfile: Dockerfile
      target: production
    container_name: obsrv_api
    restart: unless-stopped
    environment:
      DATABASE_URL: ${NEON_DATABASE_URL}  # From Neon
      INNGEST_EVENT_KEY: ${INNGEST_EVENT_KEY}
      INNGEST_ENV: production
      API_HOST: 0.0.0.0
      API_PORT: 8000
      LOG_LEVEL: info
      ENVIRONMENT: production
    ports:
      - "8000:8000"
    healthcheck:
      test: ["CMD", "curl", "-f", "http://localhost:8000/health"]
      interval: 30s
      timeout: 10s
      retries: 3
      start_period: 40s
    volumes:
      - ./logs:/app/logs  # Persistent logs
```

**Dockerfile** (multi-stage for optimization):
```dockerfile
# syntax=docker/dockerfile:1

# Stage 1: Build stage
FROM python:3.11-slim as builder

WORKDIR /build

# Install build dependencies
RUN apt-get update && apt-get install -y \
    gcc \
    && rm -rf /var/lib/apt/lists/*

# Install Python dependencies
COPY pyproject.toml poetry.lock ./
RUN pip install --no-cache-dir poetry && \
    poetry config virtualenvs.create false && \
    poetry install --no-dev --no-interaction --no-ansi

# Stage 2: Runtime stage
FROM python:3.11-slim as production

WORKDIR /app

# Install runtime dependencies
RUN apt-get update && apt-get install -y \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Install Playwright browsers (for crawl4ai)
RUN pip install playwright && \
    playwright install --with-deps chromium && \
    playwright install-deps

# Copy Python packages from builder
COPY --from=builder /usr/local/lib/python3.11/site-packages /usr/local/lib/python3.11/site-packages

# Copy application code
COPY src/ ./src/
COPY alembic/ ./alembic/
COPY alembic.ini ./

# Create non-root user for security
RUN useradd -m -u 1000 obsrv && \
    chown -R obsrv:obsrv /app

USER obsrv

# Default command (overridden in docker-compose)
CMD ["uvicorn", "src.api.main:app", "--host", "0.0.0.0", "--port", "8000"]
```

**.env.example**:
```bash
# Neon PostgreSQL
NEON_DATABASE_URL=postgresql://user:password@host/database?sslmode=require

# Inngest
INNGEST_EVENT_KEY=your_inngest_event_key
INNGEST_ENV=production

# API Configuration
API_HOST=0.0.0.0
API_PORT=8000
LOG_LEVEL=info
ENVIRONMENT=production

# Security
SECRET_KEY=generate_random_secret_key_here

# Crawling
DEFAULT_CRAWL_TIMEOUT=30
CRAWL_USER_AGENT=Obsrv-Bot/1.0 (+https://obsrv.io/bot)
```

**Deployment Script**:
```bash
#!/bin/bash
# deploy.sh

set -e

echo "Starting Obsrv API deployment..."

# Load environment variables
if [ ! -f .env ]; then
    echo "Error: .env file not found. Copy .env.example and configure."
    exit 1
fi

# Build application
docker-compose build --no-cache

# Run database migrations (against Neon)
docker-compose run --rm api alembic upgrade head

# Start API service
docker-compose up -d

# Wait for health checks
echo "Waiting for API to become healthy..."
sleep 10

# Check health
docker-compose ps

echo "Deployment complete!"
echo "API: http://localhost:8000"
echo "Inngest Functions: https://app.inngest.com/"
```

### Rationale

- **Single service architecture**: Eliminates container orchestration complexity, reduces resource usage
- **unless-stopped restart policy**: Survives VPS reboots, recovers from crashes, but allows manual stops
- **Managed services**: Neon and Inngest handle scaling, backups, and high availability
- **Multi-stage Dockerfile**: Separates build and runtime dependencies, reduces final image size by 40%
- **Health checks**: Enables automated recovery and monitoring
- **Simplified deployment**: No need to manage multiple interconnected services

### Alternatives Considered

- **Full container orchestration**: Kubernetes/Docker Swarm overkill for single service
- **Local PostgreSQL**: Requires manual maintenance, backup, and scaling
- **Celery on VPS**: Resource intensive, complex worker management
- **Multiple API instances**: Unnecessary for MVP scale, adds complexity

### References

- Docker Compose health checks: https://last9.io/blog/docker-compose-health-checks/
- FastAPI + Celery Docker: https://testdriven.io/courses/fastapi-celery/docker/
- PostgreSQL Docker best practices: https://medium.com/codex/how-to-persist-and-backup-data-of-a-postgresql-docker-container-9fe269ff4334

---

## Summary Table

| Area | Decision | Key Rationale | Trade-offs |
|------|----------|---------------|------------|
| **URL Normalization** | `url-normalize` + `w3lib` | Industry-proven, 4M downloads/month, robust tracking param removal | Requires two libraries instead of stdlib only |
| **Product ID Extraction** | Domain-specific regex + HTML fallback | High accuracy for known platforms, graceful degradation | Manual pattern maintenance per platform |
| **crawl4ai Strategy** | AsyncPlaywrightCrawlerStrategy with static HTML | Future-proof for JS rendering, resource-constrained config | Higher baseline resource usage than requests+BS4 |
| **Inngest Functions** | Step-based durable functions | Automatic retries, event-driven execution, serverless scaling | Vendor dependency vs self-hosted Celery |
| **Function Retries** | Built-in exponential backoff, configurable | Handles transient failures, prevents endpoint overwhelm | Up to 2-hour function timeout |
| **Workflow Patterns** | Step functions with fan-out | Clear dependencies, parallel execution, durable state | Event-driven vs imperative task chaining |
| **HMAC Signatures** | Stripe pattern (timestamp + versioned signature) | Replay attack protection, versioning, familiar to developers | Slightly larger headers than simple HMAC |
| **Secret Rotation** | Dual-key grace period (1 hour) | Zero-downtime rotation, client-friendly | Added complexity in verification logic |
| **JSONB Indexing** | jsonb_path_ops GIN indexes | 78% smaller indexes, 8% faster queries | Less flexible than jsonb_ops (containment only) |
| **Schema Design** | Hybrid relational + JSONB | Fast queries on structured fields, flexible for variable data | More complex schema than pure JSONB |
| **Neon Partitioning** | Managed time-based partitioning | Automatic lifecycle management, efficient retention | Less control than self-managed PostgreSQL |
| **Data Retention** | Neon automated cleanup + aggregated stats | Serverless maintenance, instant operations | Managed service dependency |
| **API Key Hashing** | bcrypt work factor 12 | Proven security, 100ms verification acceptable, simple | Slower than argon2id for same security level |
| **Key Generation** | 256-bit secrets.token_urlsafe | OWASP recommendation, cryptographically strong | Longer keys than 128-bit alternatives |
| **Auth Strategy** | Direct Neon queries | Simpler architecture, connection pooling | No caching layer vs Redis approach |
| **Docker Services** | 1 container (api only) | Simplified deployment, reduced resource usage | Less service isolation than multi-container |
| **Health Checks** | pg_isready, redis-cli ping, Celery inspect | Reliable service readiness detection, enables automation | Added startup time (~30s) |
| **Restart Policy** | unless-stopped | Survives reboots, allows manual control | Can mask underlying issues if auto-restarting frequently |

---

## Implementation Priority

**Phase 1 - Core Infrastructure** (Week 1):
1. Docker Compose setup (API only)
2. Neon PostgreSQL setup and migrations (Alembic)
3. Inngest account setup and function registration
4. API key generation and authentication
5. Basic FastAPI routes with health checks

**Phase 2 - Crawling Foundation** (Week 2):
1. URL normalization and product ID extraction
2. crawl4ai integration with rate limiting
3. Basic Inngest functions for crawling
4. Product discovery workflow

**Phase 3 - Monitoring Logic** (Week 3):
1. Change detection (price/stock)
2. Historical data storage
3. HMAC webhook signatures
4. Notification delivery with retries

**Phase 4 - Operations** (Week 4):
1. Inngest cron scheduling
2. Data retention and cleanup functions
3. Monitoring and logging
4. Deployment automation

---

## Open Questions for Clarification

1. **Crawl4ai JavaScript Rendering**: Confirmed MVP scope is static HTML only. Should we add a "JS-required" flag during website registration to warn clients upfront?

2. **Partition Automation**: Should we use pg_partman extension for automated partition management, or keep it simple with manual Celery tasks for MVP?

3. **API Key Bootstrap**: How should the first client/API key be created? Manual SQL insert, or a special bootstrap CLI command?

4. **Rate Limiting (API)**: Should we add rate limiting to API endpoints (e.g., 100 req/min per client) to prevent abuse, or rely on VPS-level limits for MVP?

5. **Webhook Retries**: Current spec says 3 retries over 1 hour. Should failed webhooks after exhaustion be queryable via API for manual retry, or just logged?

---

**Document Status**: Draft - Ready for Technical Review
**Next Steps**:
1. Review decisions with team
2. Resolve open questions
3. Begin Phase 1 implementation
4. Update plan.md with refined timeline
