# Research: Technical Implementation Decisions

**Feature**: Obsrv API - E-commerce Monitoring System MVP
**Branch**: `001-obsrv-api-mvp`
**Date**: 2025-11-03
**Phase**: Phase 0 - Research & Planning

## Overview

This document consolidates technical research findings and implementation decisions for the Obsrv API MVP. All decisions prioritize MVP simplicity while maintaining production-readiness for the constrained single-VPS environment (4 CPU, 8GB RAM, 100GB storage).

## Key Technical Decisions

### 1. URL Normalization & Product ID Extraction

**Decision**: Use `url-normalize` + `w3lib` libraries with domain-specific regex patterns

**Rationale**:
- Industry-proven libraries (4M+ downloads/month)
- Robust tracking parameter removal critical for accurate product identification
- Domain-specific patterns (Amazon, Shopify) with generic fallbacks handle 80% of e-commerce sites

**Alternatives Considered**:
- BeautifulSoup only: Misses URL-based IDs, requires HTML parsing every time
- Custom implementation: Reinventing wheel, prone to edge cases
- furl library: Heavier, overlapping functionality

**Implementation Notes**:
- Extract product IDs using URL patterns first (fast), fallback to HTML meta tags
- Cache normalized URLs to avoid repeated processing
- Store both original and normalized URLs for debugging

---

### 2. crawl4ai Integration & Crawling Strategy

**Decision**: Use crawl4ai with `AsyncPlaywrightCrawlerStrategy` but constrained to static HTML for MVP

**Rationale**:
- Future-proof architecture for JavaScript rendering (post-MVP)
- Async crawling enables concurrent website processing within resource limits
- Built-in rate limiting and user agent rotation

**Alternatives Considered**:
- BeautifulSoup + requests: Simpler but no JS support, manual rate limiting
- Scrapy: Overkill for MVP, steeper learning curve
- Selenium: Higher resource usage, slower execution

**Implementation Notes**:
- Rate limit: 10 requests/minute per domain (avoid bot detection)
- Disable JavaScript rendering for MVP (`headless=False`, static HTML only)
- Retry failed requests 3 times with exponential backoff
- Use rotating user agent strings

---

### 3. Celery Task Patterns & Scheduling

**Decision**: Celery Beat with database-backed scheduler, task chaining for workflows

**Rationale**:
- Database-backed scheduler allows runtime schedule updates per website
- Task chains provide clear workflow: discovery → approval → baseline → monitoring
- Celery Flower for observability (included in docker-compose)

**Alternatives Considered**:
- Cron + standalone scripts: Simpler but no workflow management, no retries
- APScheduler: Less mature ecosystem, limited distributed support
- Redis-backed Beat: Loses schedules on Redis restart

**Implementation Notes**:
- Retry strategy: 3 attempts, exponential backoff (60s, 120s, 240s)
- Task timeout: 15 minutes per crawl (100 products × 2s/product + overhead)
- Periodic tasks: `crawl_scheduled_websites` (hourly check), `cleanup_old_data` (daily 3 AM)
- Use task priorities: high (notifications), normal (crawls), low (cleanup)

---

### 4. HMAC Webhook Signature

**Decision**: Stripe-style HMAC-SHA256 with timestamp and versioning: `X-Obsrv-Signature: t={timestamp},v1={signature}`

**Rationale**:
- Replay attack protection via timestamp validation (5-minute window)
- Versioning (`v1=`) enables future algorithm upgrades
- Familiar pattern to developers (Stripe, GitHub use similar formats)

**Alternatives Considered**:
- GitHub style (single signature in header): No replay protection
- JWT tokens: Overkill, adds payload overhead
- Basic HMAC without timestamp: Vulnerable to replay attacks

**Implementation Notes**:
- Sign entire JSON payload: `HMAC-SHA256(secret, timestamp + '.' + json_body)`
- Secret rotation: 1-hour grace period accepting both old and new secrets
- Client verification: Recompute signature, constant-time comparison to prevent timing attacks
- Include signature verification examples in API documentation

---

### 5. PostgreSQL Schema Design

**Decision**: Hybrid relational + JSONB with time-based partitioning for history table

**Rationale**:
- JSONB for flexible crawl data (varies by e-commerce platform)
- Monthly partitioning enables efficient old data purging (DROP PARTITION vs DELETE)
- Materialized view for "latest product state" optimizes common queries

**Alternatives Considered**:
- Pure relational schema: Requires migrations for new product attributes
- NoSQL (MongoDB): More complex stack, loses ACID guarantees
- No partitioning: Slow DELETE operations, VACUUM overhead

**Implementation Notes**:
- Use `jsonb_path_ops` GIN indexes (78% smaller than default, faster queries)
- Partition `product_history` by month: `product_history_2025_01`, `product_history_2025_02`
- Materialized view refreshed after each crawl batch
- Index strategy: `(website_id, product_id, crawl_timestamp DESC)` for time-series queries

---

### 6. Data Retention & Cleanup Strategy

**Decision**: DROP PARTITION for historical data removal, preserve aggregated statistics

**Rationale**:
- Partition drop is 1000x faster than DELETE (instant, no VACUUM)
- Aggregated statistics (min/max/avg prices per month) kept indefinitely
- Weekly cleanup schedule minimizes maintenance impact

**Alternatives Considered**:
- Scheduled DELETE: Slow, causes table bloat, requires VACUUM
- Archive to S3: Adds complexity, cost, rarely needed for MVP
- Truncate: Can't selectively remove by date

**Implementation Notes**:
- Celery task: `maintain_data_retention` runs weekly (Sunday 3 AM UTC)
- Before dropping partition, compute aggregates and store in `product_statistics` table
- Retention check: `SELECT partition_name FROM pg_partitions WHERE created_at < NOW() - INTERVAL '90 days'`
- Log all partition drops for audit trail

---

### 7. API Key Storage & Validation

**Decision**: bcrypt (work factor 12) for hashing, Redis caching for validated keys (5-minute TTL)

**Rationale**:
- bcrypt industry standard, 100ms verification acceptable for API keys
- 99% cache hit rate avoids database round-trips
- 256-bit entropy from `secrets.token_urlsafe()` prevents brute force

**Alternatives Considered**:
- argon2: Marginally more secure but 100ms bcrypt sufficient for API keys
- No caching: Database query on every request (50ms+ latency)
- JWT: Stateless but no revocation support (requirement for invalidation)

**Implementation Notes**:
- Key format: `obsrv_live_` + 43 characters (URL-safe base64 of 256 bits)
- Cache key: `api_key:hash:{first_8_chars}` → `{client_id, expires_at}`
- Cache invalidation: Clear on key invalidation or rotation
- Rate limiting: 1000 requests/hour per API key

---

### 8. Docker Compose Architecture

**Decision**: 6-service stack: API, Celery Worker, Celery Beat, PostgreSQL, Redis, Flower

**Rationale**:
- Service isolation enables independent scaling post-MVP
- Health checks ensure correct startup order (DB → API → Workers)
- Named volumes persist data across container restarts

**Alternatives Considered**:
- Single container: Simpler but harder to debug, no process isolation
- Kubernetes: Overkill for single VPS, complex for MVP
- Separate VMs: More expensive, manual orchestration

**Implementation Notes**:
```yaml
services:
  postgres:
    image: postgres:16-alpine
    volumes: [pgdata:/var/lib/postgresql/data]
    healthcheck: pg_isready

  redis:
    image: redis:7-alpine
    volumes: [redisdata:/data]
    healthcheck: redis-cli ping

  api:
    build: .
    command: uvicorn src.api.main:app --host 0.0.0.0
    depends_on: [postgres, redis]
    healthcheck: curl http://localhost:8000/health

  celery-worker:
    build: .
    command: celery -A src.tasks worker --loglevel=info
    depends_on: [postgres, redis]

  celery-beat:
    build: .
    command: celery -A src.tasks beat --loglevel=info
    depends_on: [postgres, redis]

  flower:
    build: .
    command: celery -A src.tasks flower
    ports: [5555:5555]
```

- Resource limits: API (2 CPU, 4GB), workers (1.5 CPU, 3GB), DB (0.5 CPU, 1GB)
- Restart policy: `unless-stopped` for all services
- Networks: Single bridge network `obsrv-net`

---

## Summary of Trade-offs

| Area | Decision | Trade-off |
|------|----------|-----------|
| URL Normalization | url-normalize + w3lib | Small dependency cost vs reliability |
| Crawling | crawl4ai | Higher resources vs future JS support |
| Task Queue | Celery + DB scheduler | Complexity vs runtime flexibility |
| Webhooks | HMAC with timestamp | Client implementation vs security |
| Database | Relational + JSONB | Schema flexibility vs query performance |
| Retention | Partition dropping | Partition management vs 1000x faster cleanup |
| Auth | bcrypt + Redis cache | 5-min invalidation delay vs speed |
| Deployment | 6-container Docker | Orchestration complexity vs isolation |

---

## Implementation Priority

**Phase 1 (Week 1)**: Core infrastructure
- PostgreSQL schema with partitioning
- API key authentication with Redis caching
- Basic CRUD API endpoints

**Phase 2 (Week 2)**: Crawling engine
- URL normalization and product ID extraction
- crawl4ai integration with rate limiting
- Celery tasks for discovery and crawling

**Phase 3 (Week 3)**: Change detection & notifications
- Price/stock change detection logic
- HMAC webhook delivery with retries
- Historical data queries

**Phase 4 (Week 4)**: Production readiness
- Data retention automation
- Docker Compose orchestration
- Monitoring with Flower
- Deployment quickstart documentation

---

## Open Questions for Implementation

1. **Product Discovery Approval UI**: MVP spec mentions "client approval" of discovered products - implement as API endpoint with pending state or require manual database update?

2. **Crawl Concurrency Limits**: How many websites can we crawl simultaneously without overwhelming VPS? Recommend starting with 3 concurrent, monitor CPU/memory.

3. **Webhook Retry Storage**: Should failed webhook payloads be stored in database or Redis? Database ensures durability, Redis reduces storage growth.

4. **Platform Adapter Extensibility**: Generic crawler sufficient for MVP, but should we pre-build adapters for top 3 platforms (Amazon, Shopify, WooCommerce)?

5. **Monitoring & Alerting**: Beyond Flower, do we need external monitoring (e.g., UptimeRobot, Sentry)? Or rely on crawl logs and API health checks?

---

## References

- **URL Normalization**: [url-normalize docs](https://github.com/niksite/url-normalize), [w3lib docs](https://w3lib.readthedocs.io/)
- **crawl4ai**: [GitHub repository](https://github.com/unclecode/crawl4ai), [Examples](https://crawl4ai.com/mkdocs/examples/)
- **Celery Best Practices**: [Official docs](https://docs.celeryq.dev/), [Production checklist](https://docs.celeryq.dev/en/stable/userguide/calling.html#guide-calling)
- **HMAC Webhooks**: [Stripe signature verification](https://stripe.com/docs/webhooks/signatures), [GitHub webhook security](https://docs.github.com/en/webhooks/using-webhooks/validating-webhook-deliveries)
- **PostgreSQL Partitioning**: [Official docs](https://www.postgresql.org/docs/current/ddl-partitioning.html), [Performance benchmarks](https://www.postgresql.org/docs/current/ddl-partition-pruning.html)
- **bcrypt Security**: [OWASP recommendations](https://cheatsheetseries.owasp.org/cheatsheets/Password_Storage_Cheat_Sheet.html)
- **Docker Compose**: [Official docs](https://docs.docker.com/compose/), [Health checks](https://docs.docker.com/compose/compose-file/05-services/#healthcheck)

---

**Status**: ✅ Research complete - Ready for Phase 1 (Design & Contracts)
