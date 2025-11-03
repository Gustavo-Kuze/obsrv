# Data Model: Obsrv API MVP

**Feature**: Obsrv API - E-commerce Monitoring System MVP
**Branch**: `001-obsrv-api-mvp`
**Date**: 2025-11-03
**Phase**: Phase 1 - Design & Contracts

## Overview

This document defines the complete data model for the Obsrv API MVP, including entity relationships, field specifications, validation rules, state transitions, and database schema design.

## Entity Relationship Diagram

```
┌─────────────────┐
│  Client         │
│  Account        │
└────────┬────────┘
         │ 1
         │ owns
         │
         ├──────────────────┐
         │                  │
         │ *                │ *
    ┌────▼──────┐      ┌────▼─────┐
    │ API Key   │      │ Monitored │
    │           │      │ Website   │
    └───────────┘      └────┬──────┘
                            │ 1
                            │ tracks
                            │ *
                       ┌────▼─────────┐
                       │  Product     │
                       └────┬─────────┘
                            │ 1
                            │ has
                            │ *
                       ┌────▼──────────────┐
                       │ Product History   │
                       │ Record            │
                       └───────────────────┘

┌────────────────┐
│ Monitored      │
│ Website        │
└────────┬───────┘
         │ 1
         │ generates
         │ *
    ┌────▼──────────┐
    │ Crawl         │
    │ Execution Log │
    └───────────────┘

┌────────────────┐
│ Product        │
│ History Record │
└────────┬───────┘
         │ 1
         │ triggers
         │ *
    ┌────▼──────────┐
    │ Webhook       │
    │ Delivery Log  │
    └───────────────┘
```

---

## Entity Definitions

### 1. Client Account

**Purpose**: Represents a customer of the Obsrv monitoring service

**Fields**:

| Field Name | Type | Constraints | Description |
|-----------|------|-------------|-------------|
| `id` | UUID | PK, NOT NULL | Unique client identifier |
| `name` | VARCHAR(255) | NOT NULL | Client organization name |
| `email` | VARCHAR(255) | NOT NULL, UNIQUE | Primary contact email |
| `created_at` | TIMESTAMP | NOT NULL, DEFAULT NOW() | Account creation timestamp |
| `updated_at` | TIMESTAMP | NOT NULL, DEFAULT NOW() | Last modification timestamp |
| `subscription_tier` | ENUM | NOT NULL, DEFAULT 'basic' | Subscription level (basic, professional, enterprise) |
| `is_active` | BOOLEAN | NOT NULL, DEFAULT TRUE | Account active status |
| `webhook_secret_current` | VARCHAR(64) | NOT NULL | Current webhook signing secret (hashed) |
| `webhook_secret_previous` | VARCHAR(64) | NULLABLE | Previous secret during rotation grace period |
| `secret_rotation_expires_at` | TIMESTAMP | NULLABLE | Expiry time for previous secret (1 hour) |
| `max_websites` | INTEGER | NOT NULL, DEFAULT 20 | Maximum websites allowed |
| `max_products_per_website` | INTEGER | NOT NULL, DEFAULT 100 | Maximum products per website |

**Validation Rules**:
- Email must be valid format
- `subscription_tier` in ['basic', 'professional', 'enterprise']
- `max_websites` > 0 and <= 100
- `max_products_per_website` > 0 and <= 1000
- `webhook_secret_current` generated using `secrets.token_urlsafe(48)`

**Indexes**:
```sql
CREATE UNIQUE INDEX idx_clients_email ON clients(email);
CREATE INDEX idx_clients_active ON clients(is_active) WHERE is_active = TRUE;
```

---

### 2. API Key

**Purpose**: Represents authentication credential for client API access

**Fields**:

| Field Name | Type | Constraints | Description |
|-----------|------|-------------|-------------|
| `id` | UUID | PK, NOT NULL | Unique key identifier |
| `client_id` | UUID | FK → clients.id, NOT NULL | Owner client |
| `key_hash` | VARCHAR(60) | NOT NULL, UNIQUE | bcrypt hash of API key |
| `key_prefix` | VARCHAR(16) | NOT NULL | First 8 characters for identification |
| `created_at` | TIMESTAMP | NOT NULL, DEFAULT NOW() | Key creation timestamp |
| `last_used_at` | TIMESTAMP | NULLABLE | Last successful authentication |
| `invalidated_at` | TIMESTAMP | NULLABLE | Invalidation timestamp (NULL = active) |
| `description` | TEXT | NULLABLE | Optional key description |
| `permissions_scope` | JSONB | NOT NULL, DEFAULT '["read", "write"]' | Permission scopes |

**Validation Rules**:
- `key_hash` generated using `bcrypt.hashpw(key, bcrypt.gensalt(rounds=12))`
- Key format (unhashed): `obsrv_live_{secrets.token_urlsafe(32)}` (43 total chars)
- `key_prefix` = first 8 chars of unhashed key for display
- `permissions_scope` contains valid scopes: ["read", "write", "admin"]

**Indexes**:
```sql
CREATE UNIQUE INDEX idx_api_keys_hash ON api_keys(key_hash);
CREATE INDEX idx_api_keys_client_active ON api_keys(client_id) WHERE invalidated_at IS NULL;
CREATE INDEX idx_api_keys_prefix ON api_keys(key_prefix);
```

**State Transitions**:
```
[Created] → [Active] → [Invalidated]
            ↓
        [Last Used Updated]
```

---

### 3. Monitored Website

**Purpose**: Represents an e-commerce website registered for continuous monitoring

**Fields**:

| Field Name | Type | Constraints | Description |
|-----------|------|-------------|-------------|
| `id` | UUID | PK, NOT NULL | Unique website identifier |
| `client_id` | UUID | FK → clients.id, NOT NULL | Owner client |
| `base_url` | VARCHAR(2048) | NOT NULL | Website base URL (normalized) |
| `seed_urls` | JSONB | NOT NULL | Seed URLs for product discovery |
| `created_at` | TIMESTAMP | NOT NULL, DEFAULT NOW() | Registration timestamp |
| `updated_at` | TIMESTAMP | NOT NULL, DEFAULT NOW() | Last modification timestamp |
| `status` | ENUM | NOT NULL, DEFAULT 'pending_approval' | Monitoring status |
| `crawl_frequency_minutes` | INTEGER | NOT NULL, DEFAULT 1440 | Crawl interval (1440 = daily) |
| `price_change_threshold_pct` | DECIMAL(5,2) | NOT NULL, DEFAULT 1.00 | Price change threshold % |
| `retention_days` | INTEGER | NOT NULL, DEFAULT 90 | Historical data retention period |
| `discovered_products_pending` | JSONB | NULLABLE | Products awaiting approval |
| `approved_product_count` | INTEGER | NOT NULL, DEFAULT 0 | Count of approved products |
| `last_successful_crawl_at` | TIMESTAMP | NULLABLE | Last successful crawl timestamp |
| `last_crawl_status` | VARCHAR(50) | NULLABLE | Status of most recent crawl |
| `webhook_endpoint_url` | VARCHAR(2048) | NULLABLE | Client webhook receiver URL |
| `webhook_enabled` | BOOLEAN | NOT NULL, DEFAULT TRUE | Webhook delivery enabled |
| `consecutive_failures` | INTEGER | NOT NULL, DEFAULT 0 | Failed crawl count (for pausing) |

**Validation Rules**:
- `base_url` must be valid HTTP/HTTPS URL
- `status` in ['pending_approval', 'active', 'paused', 'failed']
- `crawl_frequency_minutes` in [360, 480, 720, 1440] (6h, 8h, 12h, 24h)
- `price_change_threshold_pct` >= 0.01 and <= 100.00
- `retention_days` >= 30 and <= 365
- `approved_product_count` <= client.max_products_per_website
- `webhook_endpoint_url` must be valid HTTPS URL if provided

**Indexes**:
```sql
CREATE INDEX idx_websites_client ON monitored_websites(client_id);
CREATE INDEX idx_websites_status ON monitored_websites(status) WHERE status = 'active';
CREATE INDEX idx_websites_next_crawl ON monitored_websites(last_successful_crawl_at, crawl_frequency_minutes);
```

**State Transitions**:
```
[pending_approval] → [active] → [paused] → [active]
                             ↓
                        [failed] (after 3 consecutive failures)
```

---

### 4. Product

**Purpose**: Represents an individual product being tracked on a monitored website

**Fields**:

| Field Name | Type | Constraints | Description |
|-----------|------|-------------|-------------|
| `id` | UUID | PK, NOT NULL | Unique product identifier |
| `website_id` | UUID | FK → monitored_websites.id, NOT NULL | Parent website |
| `original_url` | VARCHAR(2048) | NOT NULL | Original product URL as discovered |
| `normalized_url` | VARCHAR(2048) | NOT NULL | Normalized URL (cleaned) |
| `extracted_product_id` | VARCHAR(255) | NULLABLE | Extracted SKU/product code |
| `extraction_method` | VARCHAR(50) | NOT NULL | Method used for ID extraction |
| `product_name` | TEXT | NOT NULL | Product display name |
| `current_price` | DECIMAL(12,2) | NULLABLE | Current price (nullable if out of stock) |
| `current_currency` | VARCHAR(3) | NOT NULL, DEFAULT 'USD' | Price currency code |
| `current_stock_status` | ENUM | NOT NULL | Current stock availability |
| `last_crawled_at` | TIMESTAMP | NOT NULL | Last successful crawl timestamp |
| `created_at` | TIMESTAMP | NOT NULL, DEFAULT NOW() | Product first discovered timestamp |
| `updated_at` | TIMESTAMP | NOT NULL, DEFAULT NOW() | Last update timestamp |
| `is_active` | BOOLEAN | NOT NULL, DEFAULT TRUE | Monitoring active (false if delisted) |
| `delisted_at` | TIMESTAMP | NULLABLE | Timestamp when product 404'd |

**Validation Rules**:
- `normalized_url` uniqueness enforced per website_id
- `current_stock_status` in ['in_stock', 'out_of_stock', 'limited_availability', 'unknown']
- `extraction_method` in ['url_pattern_amazon', 'url_pattern_shopify', 'url_pattern_generic', 'html_opengraph', 'html_schema', 'none']
- `current_price` >= 0 if not NULL
- `current_currency` valid ISO 4217 code

**Indexes**:
```sql
CREATE UNIQUE INDEX idx_products_website_normalized_url ON products(website_id, normalized_url);
CREATE INDEX idx_products_website_active ON products(website_id) WHERE is_active = TRUE;
CREATE INDEX idx_products_extracted_id ON products(website_id, extracted_product_id) WHERE extracted_product_id IS NOT NULL;
CREATE INDEX idx_products_last_crawled ON products(last_crawled_at);
```

**Composite Unique Key**: `(website_id, normalized_url)` ensures no duplicate products per website

---

### 5. Product History Record

**Purpose**: Represents a point-in-time snapshot of product data

**Table Design**: Time-series partitioned by month

**Fields**:

| Field Name | Type | Constraints | Description |
|-----------|------|-------------|-------------|
| `id` | UUID | PK, NOT NULL | Unique history record identifier |
| `product_id` | UUID | FK → products.id, NOT NULL | Referenced product |
| `website_id` | UUID | FK → monitored_websites.id, NOT NULL | Denormalized for partition key |
| `crawl_timestamp` | TIMESTAMP | NOT NULL, PARTITION KEY | Snapshot timestamp |
| `price` | DECIMAL(12,2) | NULLABLE | Price at this snapshot |
| `currency` | VARCHAR(3) | NOT NULL | Currency code |
| `stock_status` | ENUM | NOT NULL | Stock status at this snapshot |
| `price_changed` | BOOLEAN | NOT NULL, DEFAULT FALSE | Flag indicating price change from previous |
| `stock_changed` | BOOLEAN | NOT NULL, DEFAULT FALSE | Flag indicating stock change from previous |
| `price_change_pct` | DECIMAL(6,2) | NULLABLE | Percentage change from previous price |
| `raw_crawl_data` | JSONB | NOT NULL | Full crawled data (flexible schema) |
| `crawl_log_id` | UUID | FK → crawl_execution_logs.id, NOT NULL | Associated crawl execution |

**Validation Rules**:
- `stock_status` in ['in_stock', 'out_of_stock', 'limited_availability', 'unknown']
- `price` >= 0 if not NULL
- `price_change_pct` computed as `((new_price - old_price) / old_price) * 100`
- `raw_crawl_data` contains: `{product_name, image_url, description, availability, seller, ...}`

**Partitioning Strategy**:
```sql
-- Create parent table
CREATE TABLE product_history (
    -- fields as above
) PARTITION BY RANGE (crawl_timestamp);

-- Create monthly partitions
CREATE TABLE product_history_2025_01 PARTITION OF product_history
FOR VALUES FROM ('2025-01-01') TO ('2025-02-01');

CREATE TABLE product_history_2025_02 PARTITION OF product_history
FOR VALUES FROM ('2025-02-01') TO ('2025-03-01');

-- Automated partition creation via cron or trigger
```

**Indexes**:
```sql
CREATE INDEX idx_product_history_product_time ON product_history(product_id, crawl_timestamp DESC);
CREATE INDEX idx_product_history_website_time ON product_history(website_id, crawl_timestamp DESC);
CREATE INDEX idx_product_history_changes ON product_history(product_id) WHERE price_changed = TRUE OR stock_changed = TRUE;
CREATE INDEX idx_product_history_raw_data ON product_history USING GIN(raw_crawl_data jsonb_path_ops);
```

**Materialized View for Latest State**:
```sql
CREATE MATERIALIZED VIEW product_latest_state AS
SELECT DISTINCT ON (product_id)
    product_id,
    price,
    stock_status,
    crawl_timestamp
FROM product_history
ORDER BY product_id, crawl_timestamp DESC;

CREATE UNIQUE INDEX ON product_latest_state(product_id);
```

---

### 6. Crawl Execution Log

**Purpose**: Represents a single crawl operation execution

**Fields**:

| Field Name | Type | Constraints | Description |
|-----------|------|-------------|-------------|
| `id` | UUID | PK, NOT NULL | Unique crawl execution identifier |
| `website_id` | UUID | FK → monitored_websites.id, NOT NULL | Target website |
| `started_at` | TIMESTAMP | NOT NULL, DEFAULT NOW() | Crawl start timestamp |
| `completed_at` | TIMESTAMP | NULLABLE | Crawl completion timestamp (NULL = in progress) |
| `status` | ENUM | NOT NULL | Execution status |
| `products_processed` | INTEGER | NOT NULL, DEFAULT 0 | Count of products successfully crawled |
| `changes_detected` | INTEGER | NOT NULL, DEFAULT 0 | Count of price/stock changes detected |
| `errors_count` | INTEGER | NOT NULL, DEFAULT 0 | Count of product-level errors |
| `error_details` | JSONB | NULLABLE | Error messages and stack traces |
| `retry_count` | INTEGER | NOT NULL, DEFAULT 0 | Number of retry attempts |
| `triggered_by` | VARCHAR(50) | NOT NULL | Trigger source (scheduled, manual, discovery) |
| `duration_seconds` | INTEGER | NULLABLE | Total execution time |

**Validation Rules**:
- `status` in ['pending', 'running', 'success', 'partial_success', 'failed']
- `duration_seconds` computed as `EXTRACT(EPOCH FROM (completed_at - started_at))`
- `triggered_by` in ['scheduled', 'manual', 'discovery', 'retry']

**Indexes**:
```sql
CREATE INDEX idx_crawl_logs_website ON crawl_execution_logs(website_id, started_at DESC);
CREATE INDEX idx_crawl_logs_status ON crawl_execution_logs(status, started_at DESC);
CREATE INDEX idx_crawl_logs_errors ON crawl_execution_logs(website_id) WHERE status = 'failed';
```

**State Transitions**:
```
[pending] → [running] → [success]
                     → [partial_success] (some products failed)
                     → [failed] → [retry]
```

---

### 7. Webhook Delivery Log

**Purpose**: Represents an attempt to deliver change notification

**Fields**:

| Field Name | Type | Constraints | Description |
|-----------|------|-------------|-------------|
| `id` | UUID | PK, NOT NULL | Unique delivery attempt identifier |
| `product_history_id` | UUID | FK → product_history.id, NOT NULL | Change that triggered webhook |
| `website_id` | UUID | FK → monitored_websites.id, NOT NULL | Target website (for filtering) |
| `target_url` | VARCHAR(2048) | NOT NULL | Webhook endpoint URL |
| `payload` | JSONB | NOT NULL | Complete webhook payload sent |
| `signature` | VARCHAR(128) | NOT NULL | HMAC-SHA256 signature value |
| `timestamp_header` | TIMESTAMP | NOT NULL | Timestamp included in signature |
| `attempt_number` | INTEGER | NOT NULL, DEFAULT 1 | Retry attempt number (1-3) |
| `delivery_timestamp` | TIMESTAMP | NOT NULL, DEFAULT NOW() | Delivery attempt timestamp |
| `http_status_code` | INTEGER | NULLABLE | HTTP response code (NULL = network error) |
| `status` | ENUM | NOT NULL | Delivery status |
| `response_body` | TEXT | NULLABLE | HTTP response body (for debugging) |
| `error_message` | TEXT | NULLABLE | Error details if delivery failed |
| `next_retry_at` | TIMESTAMP | NULLABLE | Scheduled retry timestamp |

**Validation Rules**:
- `status` in ['pending', 'success', 'failed', 'retrying', 'exhausted']
- `attempt_number` <= 3 (max retries)
- `http_status_code` >= 100 and <= 599 if not NULL
- `payload` structure: `{product_id, product_name, change_type, old_value, new_value, timestamp, signature_verification}`

**Indexes**:
```sql
CREATE INDEX idx_webhook_logs_website_status ON webhook_delivery_logs(website_id, status, delivery_timestamp DESC);
CREATE INDEX idx_webhook_logs_retry ON webhook_delivery_logs(next_retry_at) WHERE status = 'retrying';
CREATE INDEX idx_webhook_logs_product_history ON webhook_delivery_logs(product_history_id);
```

**State Transitions**:
```
[pending] → [success]
         → [failed] → [retrying] → [success]
                               → [retrying] (retry 2)
                               → [exhausted] (after 3 attempts)
```

---

## Aggregate Tables

### 8. Product Statistics (Aggregated)

**Purpose**: Preserve long-term trend data after partition drops

**Fields**:

| Field Name | Type | Constraints | Description |
|-----------|------|-------------|-------------|
| `id` | UUID | PK, NOT NULL | Unique statistics record |
| `product_id` | UUID | FK → products.id, NOT NULL | Product reference |
| `period_start` | DATE | NOT NULL | Aggregation period start (monthly) |
| `period_end` | DATE | NOT NULL | Aggregation period end |
| `min_price` | DECIMAL(12,2) | NULLABLE | Minimum price in period |
| `max_price` | DECIMAL(12,2) | NULLABLE | Maximum price in period |
| `avg_price` | DECIMAL(12,2) | NULLABLE | Average price in period |
| `price_changes_count` | INTEGER | NOT NULL | Number of price changes |
| `stock_out_days` | INTEGER | NOT NULL | Days product was out of stock |
| `total_snapshots` | INTEGER | NOT NULL | Total crawls in period |
| `created_at` | TIMESTAMP | NOT NULL, DEFAULT NOW() | Statistics generation timestamp |

**Indexes**:
```sql
CREATE UNIQUE INDEX idx_product_stats_product_period ON product_statistics(product_id, period_start);
CREATE INDEX idx_product_stats_period ON product_statistics(period_start DESC);
```

---

## Database Schema Summary

**Total Tables**: 9 (7 core + 1 partitioned + 1 aggregate)
**Estimated Storage** (20 websites, 100 products each, 90-day retention):
- Products: ~2,000 rows × 1 KB = 2 MB
- Product History: ~2,000 products × 90 days × 2 KB = 360 MB
- Crawl Logs: ~20 websites × 90 days × 1 KB = 2 MB
- Webhook Logs: ~varies by changes, estimate 50 MB
- **Total: ~414 MB** (well within 100 GB VPS storage)

**Maintenance Jobs**:
1. **Weekly Partition Drop**: Remove partitions older than retention_days
2. **Daily Aggregation**: Compute product_statistics for completed months before partition drop
3. **Hourly Cleanup**: Delete old crawl_logs (> 30 days) and webhook_logs (> 7 days)
4. **Daily VACUUM**: Run VACUUM ANALYZE on active partitions

---

**Status**: ✅ Data model complete - Ready for API contract generation
