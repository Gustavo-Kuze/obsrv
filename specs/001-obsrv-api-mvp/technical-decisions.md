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

## 3. Celery Task Patterns

### Decision

**Celery Beat Setup**: Use database-backed scheduler with `django-celery-beat` (or standalone equivalent) for dynamic schedule management.

**Configuration**:
```python
# celeryconfig.py
from celery.schedules import crontab
from kombu import Queue

# Broker and backend
broker_url = 'redis://redis:6379/0'
result_backend = 'redis://redis:6379/0'

# Task routing
task_routes = {
    'tasks.crawl_tasks.*': {'queue': 'crawl_queue'},
    'tasks.discovery_tasks.*': {'queue': 'discovery_queue'},
    'tasks.notification_tasks.*': {'queue': 'notification_queue'},
    'tasks.maintenance_tasks.*': {'queue': 'maintenance_queue'},
}

# Concurrency and performance
worker_prefetch_multiplier = 1  # One task at a time for resource control
worker_max_tasks_per_child = 50  # Prevent memory leaks
task_acks_late = True  # Acknowledge after completion
task_reject_on_worker_lost = True  # Requeue if worker dies

# Task time limits
task_soft_time_limit = 300  # 5 minutes soft limit
task_time_limit = 600  # 10 minutes hard limit

# Result expiration
result_expires = 3600  # 1 hour

# Beat schedule (default schedules, can be overridden in DB)
beat_schedule = {
    'daily-crawls-2am': {
        'task': 'tasks.crawl_tasks.execute_scheduled_crawls',
        'schedule': crontab(hour=2, minute=0),  # 2 AM UTC daily
        'options': {'queue': 'crawl_queue'}
    },
    'cleanup-old-data-weekly': {
        'task': 'tasks.maintenance_tasks.purge_old_history',
        'schedule': crontab(hour=3, minute=0, day_of_week=0),  # Sunday 3 AM UTC
        'options': {'queue': 'maintenance_queue'}
    },
    'health-check-hourly': {
        'task': 'tasks.maintenance_tasks.check_crawl_health',
        'schedule': crontab(minute=0),  # Every hour
        'options': {'queue': 'maintenance_queue'}
    }
}
```

**Task Retry Strategy**:
```python
# tasks/crawl_tasks.py
from celery import Task
from celery.exceptions import MaxRetriesExceededError

class CrawlTask(Task):
    """Base task with retry configuration"""
    autoretry_for = (
        ConnectionError,  # Network issues
        TimeoutError,     # Page load timeout
        Exception,        # Catch-all for transient errors
    )
    retry_kwargs = {
        'max_retries': 3,
        'countdown': 60,  # Initial delay: 60 seconds
    }
    retry_backoff = True  # Exponential: 60s, 120s, 240s
    retry_backoff_max = 600  # Cap at 10 minutes
    retry_jitter = True  # Add randomness to prevent thundering herd

@celery_app.task(base=CrawlTask, bind=True)
def crawl_single_product(self, product_id: int):
    """Crawl single product with automatic retries"""
    try:
        product = get_product(product_id)
        result = crawl_product_page(product.url)

        if not result['success']:
            # Raise to trigger retry
            raise Exception(f"Crawl failed: {result['error']}")

        save_product_snapshot(product_id, result)
        detect_and_notify_changes(product_id)

    except MaxRetriesExceededError:
        # All retries exhausted - log failure
        log_crawl_failure(product_id, "Max retries exceeded")
        raise
```

**Workflow Patterns (Discovery → Approval → Baseline → Monitoring)**:
```python
# tasks/workflow_patterns.py
from celery import chain, group, chord

# Pattern 1: Website Registration Workflow
def register_website_workflow(website_id: int, seed_urls: list[str]):
    """Chain: Discovery → Wait for Approval → Baseline Crawl"""
    workflow = chain(
        # Step 1: Discover products from seed URLs
        discover_products_from_seeds.s(website_id, seed_urls),

        # Step 2: Manual approval gate (not automated)
        # Client approves via API, triggering next step
    )
    return workflow.apply_async()

# Pattern 2: Baseline Crawl After Approval
def baseline_crawl_workflow(website_id: int, approved_product_ids: list[int]):
    """Group: Parallel crawl of all approved products"""
    crawl_tasks = group(
        crawl_single_product.s(product_id)
        for product_id in approved_product_ids
    )
    return crawl_tasks.apply_async()

# Pattern 3: Scheduled Daily Monitoring
@celery_app.task
def execute_scheduled_crawls():
    """Chord: Crawl all active websites → Send summary notification"""
    active_websites = get_active_websites()

    # Create parallel crawl tasks for each website
    crawl_groups = group(
        crawl_website_products.s(website.id)
        for website in active_websites
    )

    # After all crawls complete, send summary
    workflow = chord(crawl_groups)(
        send_daily_summary.s()
    )
    return workflow

@celery_app.task
def crawl_website_products(website_id: int):
    """Crawl all products for a single website"""
    products = get_website_products(website_id)

    # Sequential crawl with rate limiting
    results = []
    for product in products:
        result = crawl_single_product.delay(product.id)
        results.append(result)
        # Rate limiting handled within crawl_single_product

    return results

# Pattern 4: Change Detection → Webhook Notification
@celery_app.task
def detect_and_notify_changes(product_id: int):
    """Chain: Detect changes → Send webhooks"""
    changes = detect_product_changes(product_id)

    if changes:
        # Fire and forget webhook notifications
        for change in changes:
            send_webhook_notification.delay(change)

@celery_app.task(base=CrawlTask, bind=True)
def send_webhook_notification(self, change_data: dict):
    """Send webhook with retries"""
    try:
        response = send_webhook(change_data)
        log_webhook_delivery(change_data, response)
    except Exception as exc:
        # Retry up to 3 times with exponential backoff
        raise self.retry(exc=exc)
```

### Rationale

- **Database-backed Beat**: Allows runtime schedule updates without restarting workers (clients can adjust crawl times via API)
- **Crontab for daily crawls**: More intuitive than interval schedules for time-based operations (2 AM UTC daily)
- **Exponential backoff**: Handles transient failures gracefully, prevents overwhelming failed endpoints
- **Task routing to separate queues**: Isolates crawl tasks (resource-intensive) from notifications (latency-sensitive)
- **Chord pattern for daily crawls**: Ensures all websites crawled before sending summary, handles partial failures gracefully
- **Chain for workflows**: Clear sequential dependencies (discovery must complete before approval can happen)

### Alternatives Considered

- **Hardcoded beat_schedule**: Simpler but requires code changes and restarts to adjust crawl times
- **Interval schedules instead of crontab**: Less intuitive for calendar-based scheduling ("daily at 2 AM")
- **Synchronous crawl workflows**: Would block workers, poor resource utilization, no parallel processing
- **No retry logic**: Higher failure rates, more manual intervention required

### References

- Celery Beat documentation: https://docs.celeryq.dev/en/stable/userguide/periodic-tasks.html
- Celery Canvas patterns: https://docs.celeryq.dev/en/stable/userguide/canvas.html
- Retry strategies: https://testdriven.io/blog/retrying-failed-celery-tasks/

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

## 5. PostgreSQL Schema Design

### Decision

**JSONB Strategy**: Use `jsonb_path_ops` GIN indexes for containment queries, hybrid approach combining relational columns for queryable fields + JSONB for flexible crawl data.

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

**Strategy**: DROP PARTITION for bulk historical data removal + DELETE for fine-grained cleanup + aggregated statistics preservation.

**Implementation**:
```python
# tasks/maintenance_tasks.py
from datetime import datetime, timedelta
from sqlalchemy import text

@celery_app.task
def purge_old_history():
    """Drop old partitions and create future partitions"""
    # Get all websites with their retention settings
    websites = get_websites_with_retention_config()

    for website in websites:
        retention_days = website.config.get('retention_days', 90)
        cutoff_date = datetime.utcnow() - timedelta(days=retention_days)

        # Find partitions older than retention period
        old_partitions = find_partitions_before(cutoff_date)

        for partition_name in old_partitions:
            # Archive aggregated stats BEFORE dropping partition
            archive_partition_statistics(partition_name, website.id)

            # Drop partition (instant, releases disk space immediately)
            drop_partition(partition_name)

            logger.info(f"Dropped partition {partition_name} for website {website.id}")

    # Create future partitions (3 months ahead)
    create_future_partitions(months_ahead=3)

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
@celery_app.task
def cleanup_old_logs():
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

**Celery Beat Schedule**:
```python
beat_schedule = {
    'purge-old-history-weekly': {
        'task': 'tasks.maintenance_tasks.purge_old_history',
        'schedule': crontab(hour=3, minute=0, day_of_week=0),  # Sunday 3 AM UTC
        'options': {'queue': 'maintenance_queue'}
    },
    'cleanup-logs-daily': {
        'task': 'tasks.maintenance_tasks.cleanup_old_logs',
        'schedule': crontab(hour=4, minute=0),  # Daily 4 AM UTC
        'options': {'queue': 'maintenance_queue'}
    },
    'create-future-partitions-monthly': {
        'task': 'tasks.maintenance_tasks.create_future_partitions',
        'schedule': crontab(hour=2, minute=0, day_of_month=1),  # 1st of month, 2 AM UTC
        'options': {'queue': 'maintenance_queue'}
    }
}
```

### Rationale

- **PARTITION DROP over DELETE**: 1000x faster (metadata operation vs row-by-row deletion), instantly releases disk space, no VACUUM overhead
- **Monthly partitions**: Balance between partition count (12/year) and partition size (~10K rows/month for 100 products)
- **Aggregated statistics**: Preserves long-term trends without storing individual snapshots, enables multi-year analysis
- **Batched DELETE for logs**: Prevents table bloat for non-critical data, avoids long exclusive locks
- **Automated partition creation**: Ensures new partitions exist before data arrives, prevents INSERT failures

### Alternatives Considered

- **DELETE with VACUUM**: 1000x slower, causes table bloat, requires aggressive VACUUM schedules
- **TRUNCATE**: Faster than DELETE but removes ALL data from table (not selective)
- **Archive to cold storage**: Adds complexity, not needed for MVP scale (90 days × 2000 products = ~180K rows)

### References

- Partition drop performance: https://www.simplethread.com/beyond-delete/
- Time-based retention: https://blog.sequinstream.com/time-based-retention-strategies-in-postgres/
- pg_partman: https://www.crunchydata.com/blog/auto-archiving-and-data-retention-management-in-postgres-with-pg_partman

---

## 7. API Key Storage & Validation

### Decision

**Hashing Algorithm**: bcrypt with work factor 12 for API key storage.

**Key Generation**: 32-byte (256-bit) URL-safe tokens using Python's `secrets` module.

**Caching Strategy**: Redis cache with 5-minute TTL for validated API keys.

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
import redis
import json
from datetime import timedelta

class AuthService:
    """API key authentication with Redis caching"""

    CACHE_TTL_SECONDS = 300  # 5 minutes
    CACHE_KEY_PREFIX = "api_key:"

    def __init__(self, db_session, redis_client: redis.Redis):
        self.db = db_session
        self.redis = redis_client

    def authenticate(self, api_key: str) -> Optional[dict]:
        """
        Authenticate API key with caching

        Returns:
            dict with client_id if valid, None if invalid
        """
        # Check cache first
        cache_key = f"{self.CACHE_KEY_PREFIX}{api_key}"
        cached = self.redis.get(cache_key)

        if cached:
            # Cache hit - return immediately
            return json.loads(cached)

        # Cache miss - query database
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

                # Cache the result
                self.redis.setex(
                    cache_key,
                    self.CACHE_TTL_SECONDS,
                    json.dumps(result)
                )

                return result

        # Invalid key - cache negative result briefly (prevent brute force)
        self.redis.setex(cache_key, 60, json.dumps(None))
        return None

    def invalidate_key(self, key_id: int):
        """Invalidate API key and clear cache"""
        from models.api_key import APIKey
        from datetime import datetime

        # Mark as invalidated in database
        key_record = self.db.query(APIKey).filter(APIKey.id == key_id).first()
        if key_record:
            key_record.invalidated_at = datetime.utcnow()
            self.db.commit()

            # Clear from cache (invalidate all possible cache entries)
            # Note: We can't reconstruct the full key, so we rely on TTL expiration
            # Alternative: Store key_id in cache value and scan/delete

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

- **bcrypt over argon2**: Simpler, widely supported, sufficient for API keys (not interactive passwords), ~100ms verification acceptable for API auth
- **256-bit keys**: OWASP recommendation, cryptographically strong, future-proof
- **Redis caching**: 99% cache hit rate expected, reduces database load, sub-millisecond validation
- **Prefix indexing**: Limits bcrypt comparisons to ~1-10 candidates instead of all keys, improves performance
- **5-minute TTL**: Balances performance (fewer DB queries) with security (timely invalidation)

### Alternatives Considered

- **Argon2**: More secure but overkill for API keys, higher memory usage (concern on 8GB VPS), less mature Python support
- **scrypt**: Middle ground but no clear advantage over bcrypt for this use case
- **JWT tokens**: Stateless but requires public/private key management, harder to invalidate, larger tokens
- **Database-only validation**: Simpler but 10-50ms latency per request vs <1ms with cache

### References

- bcrypt vs argon2: https://stytch.com/blog/argon2-vs-bcrypt-vs-scrypt/
- API key best practices: https://expertbeacon.com/best-practices-for-building-secure-api-keys/
- Python secrets module: https://docs.python.org/3/library/secrets.html

---

## 8. Docker Compose MVP Architecture

### Decision

**Services**: api, celery-worker, celery-beat, postgres, redis
**Health Checks**: pg_isready (PostgreSQL), redis-cli ping (Redis), Celery inspect ping (workers)
**Restart Policy**: unless-stopped for all services (survive VPS reboots)

**docker-compose.yml**:
```yaml
version: '3.8'

services:
  # PostgreSQL database
  postgres:
    image: postgres:15-alpine
    container_name: obsrv_postgres
    restart: unless-stopped
    environment:
      POSTGRES_DB: obsrv
      POSTGRES_USER: obsrv_user
      POSTGRES_PASSWORD: ${POSTGRES_PASSWORD}
      POSTGRES_INITDB_ARGS: "-E UTF8 --locale=en_US.UTF-8"
    volumes:
      - postgres_data:/var/lib/postgresql/data
      - ./init-scripts:/docker-entrypoint-initdb.d  # Schema initialization
    ports:
      - "127.0.0.1:5432:5432"  # Localhost only for security
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U obsrv_user -d obsrv"]
      interval: 10s
      timeout: 5s
      retries: 5
      start_period: 10s
    networks:
      - obsrv_network

  # Redis - task queue and cache
  redis:
    image: redis:7-alpine
    container_name: obsrv_redis
    restart: unless-stopped
    command: redis-server --appendonly yes --maxmemory 512mb --maxmemory-policy allkeys-lru
    volumes:
      - redis_data:/data
    ports:
      - "127.0.0.1:6379:6379"  # Localhost only
    healthcheck:
      test: ["CMD", "redis-cli", "ping"]
      interval: 5s
      timeout: 3s
      retries: 3
      start_period: 5s
    networks:
      - obsrv_network

  # FastAPI application
  api:
    build:
      context: .
      dockerfile: Dockerfile
      target: production
    container_name: obsrv_api
    restart: unless-stopped
    environment:
      DATABASE_URL: postgresql://obsrv_user:${POSTGRES_PASSWORD}@postgres:5432/obsrv
      REDIS_URL: redis://redis:6379/0
      API_HOST: 0.0.0.0
      API_PORT: 8000
      LOG_LEVEL: info
      ENVIRONMENT: production
    ports:
      - "8000:8000"
    depends_on:
      postgres:
        condition: service_healthy
      redis:
        condition: service_healthy
    healthcheck:
      test: ["CMD", "curl", "-f", "http://localhost:8000/health"]
      interval: 30s
      timeout: 10s
      retries: 3
      start_period: 40s
    networks:
      - obsrv_network
    volumes:
      - ./logs:/app/logs  # Persistent logs

  # Celery worker - crawl tasks
  celery-worker:
    build:
      context: .
      dockerfile: Dockerfile
      target: production
    container_name: obsrv_celery_worker
    restart: unless-stopped
    command: celery -A src.tasks.celery_app worker --loglevel=info --concurrency=2 --max-tasks-per-child=50
    environment:
      DATABASE_URL: postgresql://obsrv_user:${POSTGRES_PASSWORD}@postgres:5432/obsrv
      REDIS_URL: redis://redis:6379/0
      LOG_LEVEL: info
      ENVIRONMENT: production
    depends_on:
      postgres:
        condition: service_healthy
      redis:
        condition: service_healthy
    healthcheck:
      test: ["CMD-SHELL", "celery -A src.tasks.celery_app inspect ping -d celery@$$HOSTNAME"]
      interval: 30s
      timeout: 10s
      retries: 3
      start_period: 30s
    networks:
      - obsrv_network
    volumes:
      - ./logs:/app/logs

  # Celery beat - scheduled tasks
  celery-beat:
    build:
      context: .
      dockerfile: Dockerfile
      target: production
    container_name: obsrv_celery_beat
    restart: unless-stopped
    command: celery -A src.tasks.celery_app beat --loglevel=info
    environment:
      DATABASE_URL: postgresql://obsrv_user:${POSTGRES_PASSWORD}@postgres:5432/obsrv
      REDIS_URL: redis://redis:6379/0
      LOG_LEVEL: info
      ENVIRONMENT: production
    depends_on:
      postgres:
        condition: service_healthy
      redis:
        condition: service_healthy
    networks:
      - obsrv_network
    volumes:
      - ./logs:/app/logs

  # Flower - Celery monitoring (optional for production)
  flower:
    build:
      context: .
      dockerfile: Dockerfile
      target: production
    container_name: obsrv_flower
    restart: unless-stopped
    command: celery -A src.tasks.celery_app flower --port=5555
    environment:
      DATABASE_URL: postgresql://obsrv_user:${POSTGRES_PASSWORD}@postgres:5432/obsrv
      REDIS_URL: redis://redis:6379/0
    ports:
      - "127.0.0.1:5555:5555"  # Localhost only
    depends_on:
      redis:
        condition: service_healthy
    networks:
      - obsrv_network

networks:
  obsrv_network:
    driver: bridge

volumes:
  postgres_data:
    driver: local
  redis_data:
    driver: local
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
    postgresql-client \
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
    postgresql-client \
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
# PostgreSQL
POSTGRES_PASSWORD=change_me_in_production

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

# Pull latest images
docker-compose pull

# Build application
docker-compose build --no-cache

# Run database migrations
docker-compose run --rm api alembic upgrade head

# Start services
docker-compose up -d

# Wait for health checks
echo "Waiting for services to become healthy..."
sleep 10

# Check health
docker-compose ps

echo "Deployment complete!"
echo "API: http://localhost:8000"
echo "Flower: http://localhost:5555"
```

### Rationale

- **service_healthy conditions**: Ensures database and Redis are ready before starting dependent services, prevents startup race conditions
- **unless-stopped restart policy**: Survives VPS reboots, recovers from crashes, but allows manual stops
- **Localhost-only ports**: PostgreSQL and Redis not exposed externally, reduces attack surface
- **Alpine images**: Smaller image size (~50MB vs 200MB), faster pulls, lower disk usage
- **Multi-stage Dockerfile**: Separates build and runtime dependencies, reduces final image size by 40%
- **Named volumes**: Data persists across container recreations, enables easy backups
- **Health checks**: Enables rolling updates, load balancer integration, automated recovery

### Alternatives Considered

- **Docker Swarm/Kubernetes**: Overkill for single-VPS MVP, adds operational complexity
- **Separate containers for each Celery queue**: Over-optimization for MVP scale, complicates deployment
- **Host networking**: Simpler but less isolated, harder to manage port conflicts
- **Docker secrets**: More secure but requires Swarm mode, plain env vars acceptable for MVP

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
| **Celery Scheduling** | Database-backed Beat + crontab schedules | Runtime schedule updates, intuitive time-based configs | Added complexity vs hardcoded schedules |
| **Task Retries** | Exponential backoff, 3 retries, 60s initial delay | Handles transient failures, prevents endpoint overwhelm | Delayed final failure detection (up to 7 minutes) |
| **Workflow Patterns** | Chain + Group + Chord | Clear dependencies, parallel execution, robust failure handling | More complex than simple task chaining |
| **HMAC Signatures** | Stripe pattern (timestamp + versioned signature) | Replay attack protection, versioning, familiar to developers | Slightly larger headers than simple HMAC |
| **Secret Rotation** | Dual-key grace period (1 hour) | Zero-downtime rotation, client-friendly | Added complexity in verification logic |
| **JSONB Indexing** | jsonb_path_ops GIN indexes | 78% smaller indexes, 8% faster queries | Less flexible than jsonb_ops (containment only) |
| **Schema Design** | Hybrid relational + JSONB | Fast queries on structured fields, flexible for variable data | More complex schema than pure JSONB |
| **Partitioning** | Monthly time-based partitioning | Optimal for time-series, efficient retention, partition pruning | Requires partition management automation |
| **Data Retention** | DROP PARTITION + aggregated stats | 1000x faster than DELETE, instant disk space release | Less granular than row-level retention |
| **API Key Hashing** | bcrypt work factor 12 | Proven security, 100ms verification acceptable, simple | Slower than argon2id for same security level |
| **Key Generation** | 256-bit secrets.token_urlsafe | OWASP recommendation, cryptographically strong | Longer keys than 128-bit alternatives |
| **Auth Caching** | Redis 5-minute TTL | 99% cache hit rate, sub-ms validation | 5-minute delay for key invalidation |
| **Docker Services** | 5 containers (api, worker, beat, postgres, redis) | Clear separation, independent scaling, health checks | More complex than monolithic container |
| **Health Checks** | pg_isready, redis-cli ping, Celery inspect | Reliable service readiness detection, enables automation | Added startup time (~30s) |
| **Restart Policy** | unless-stopped | Survives reboots, allows manual control | Can mask underlying issues if auto-restarting frequently |

---

## Implementation Priority

**Phase 1 - Core Infrastructure** (Week 1):
1. Docker Compose setup with PostgreSQL, Redis
2. Database schema and migrations (Alembic)
3. API key generation and authentication
4. Basic FastAPI routes with health checks

**Phase 2 - Crawling Foundation** (Week 2):
1. URL normalization and product ID extraction
2. crawl4ai integration with rate limiting
3. Basic Celery tasks for crawling
4. Product discovery workflow

**Phase 3 - Monitoring Logic** (Week 3):
1. Change detection (price/stock)
2. Historical data storage
3. HMAC webhook signatures
4. Notification delivery with retries

**Phase 4 - Operations** (Week 4):
1. Celery Beat scheduling
2. Data retention and cleanup tasks
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
