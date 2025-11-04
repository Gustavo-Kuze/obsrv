# Research: Technical Implementation Decisions

**Feature**: Obsrv API - E-commerce Monitoring System MVP
**Branch**: `001-obsrv-api-mvp`
**Date**: 2025-11-03
**Phase**: Phase 0 - Research & Planning

## Overview

This document consolidates technical research findings and implementation decisions for the Obsrv API MVP. All decisions prioritize MVP simplicity while maintaining production-readiness for the minimal single-VPS environment (1 CPU, 4GB RAM, 50GB storage) with managed Neon PostgreSQL and Inngest serverless functions.

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

### 3. Inngest Function Patterns & Scheduling

**Decision**: Inngest step-based functions with event-driven and cron triggers

**Rationale**:
- Durable execution ensures workflows complete even with failures
- Event-driven architecture more flexible than cron schedules
- Built-in retry logic and step isolation
- Serverless scaling eliminates resource management on VPS

**Alternatives Considered**:
- Inngest for all tasks: More complex function chaining
- AWS Lambda + SQS: More complex infrastructure setup
- GitHub Actions: Limited to scheduled workflows, no dynamic triggering

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

### 5. Neon PostgreSQL Schema Design

**Decision**: Hybrid relational + JSONB with Neon-managed partitioning for history table

**Rationale**:
- JSONB for flexible crawl data (varies by e-commerce platform)
- Neon-managed partitioning enables efficient old data purging
- Serverless scaling and automatic maintenance

**Alternatives Considered**:
- Pure relational schema: Requires migrations for new product attributes
- NoSQL (MongoDB): More complex stack, loses ACID guarantees
- Self-managed partitioning: Manual maintenance overhead

**Implementation Notes**:
- Use `jsonb_path_ops` GIN indexes (78% smaller than default, faster queries)
- Neon handles partitioning automatically based on retention policies
- Index strategy: `(website_id, product_id, crawl_timestamp DESC)` for time-series queries

---

### 6. Data Retention & Cleanup Strategy

**Decision**: Leverage Neon's managed services for automatic data lifecycle management

**Rationale**:
- Automatic data lifecycle management without manual intervention
- Serverless maintenance eliminates operational complexity
- Built-in backup and recovery capabilities

**Alternatives Considered**:
- Scheduled DELETE: Slow, causes table bloat, requires VACUUM
- Archive to S3: Adds complexity, cost, rarely needed for MVP
- Self-managed retention: Manual maintenance overhead

**Implementation Notes**:
- Inngest function: `maintain_data_retention` runs weekly (Sunday 3 AM UTC)
- Neon handles automatic cleanup based on retention policies
- Aggregated statistics preserved for long-term analysis
- Built-in backup ensures data durability

---

### 7. API Key Storage & Validation

**Decision**: bcrypt (work factor 12) for hashing, direct Neon PostgreSQL queries

**Rationale**:
- bcrypt industry standard, 100ms verification acceptable for API keys
- Neon connection pooling provides sufficient performance
- Simpler architecture without additional caching layer

**Alternatives Considered**:
- argon2: Marginally more secure but 100ms bcrypt sufficient for API keys
- JWT: Stateless but no revocation support (requirement for invalidation)
- External cache (Redis): Adds complexity for minimal performance gain

**Implementation Notes**:
- Key format: `obsrv_live_` + 43 characters (URL-safe base64 of 256 bits)
- Direct database queries with Neon connection pooling
- Rate limiting: 1000 requests/hour per API key
- Neon provides automatic query optimization

---

### 8. Docker Compose Architecture

**Decision**: Single service: API only with managed Neon PostgreSQL and Inngest

**Rationale**:
- Eliminates container orchestration complexity
- Managed services handle scaling, backups, and high availability
- Simplified deployment reduces operational overhead

**Alternatives Considered**:
- Single container: Simpler but harder to debug, no process isolation
- Kubernetes: Overkill for single VPS, complex for MVP
- Separate VMs: More expensive, manual orchestration

**Implementation Notes**:
```yaml
services:
  api:
    build: .
    ports:
      - "8000:8000"
    environment:
      - DATABASE_URL=${DATABASE_URL}
      - INNGEST_EVENT_KEY=${INNGEST_EVENT_KEY}
      - INNGEST_SIGNING_KEY=${INNGEST_SIGNING_KEY}
    restart: unless-stopped
    healthcheck:
      test: ["CMD", "curl", "-f", "http://localhost:8000/health"]
      interval: 30s
      timeout: 10s
      retries: 3
```

- Single container deployment simplifies operations
- Managed services eliminate local infrastructure management
- Health checks ensure service reliability

---

## Summary of Trade-offs

| Area | Decision | Trade-off |
|------|----------|-----------|
| URL Normalization | url-normalize + w3lib | Small dependency cost vs reliability |
| Crawling | crawl4ai | Higher resources vs future JS support |
| Task Queue | Inngest functions | Vendor dependency vs self-hosted complexity |
| Webhooks | HMAC with timestamp | Client implementation vs security |
| Database | Neon + JSONB | Managed service cost vs operational simplicity |
| Retention | Neon automated | Less control vs simplified maintenance |
| Auth | bcrypt + Neon | Direct queries vs minimal complexity |
| Deployment | Single container | Less isolation vs simplified operations |

---

## Implementation Priority

**Phase 1 (Week 1)**: Core infrastructure
- Neon PostgreSQL setup and schema
- Inngest account and function registration
- API key authentication
- Basic CRUD API endpoints

**Phase 2 (Week 2)**: Crawling engine
- URL normalization and product ID extraction
- crawl4ai integration with rate limiting
- Inngest functions for discovery and crawling

**Phase 3 (Week 3)**: Change detection & notifications
- Price/stock change detection logic
- HMAC webhook delivery with retries
- Historical data queries

**Phase 4 (Week 4)**: Production readiness
- Data retention automation with Inngest
- Single-container Docker deployment
- Inngest monitoring and logging
- Deployment quickstart documentation

---

## Open Questions for Implementation

1. **Product Discovery Approval UI**: MVP spec mentions "client approval" of discovered products - implement as API endpoint with pending state or require manual database update?

2. **Crawl Concurrency Limits**: How many websites can we crawl simultaneously with Inngest's serverless scaling? Start with conservative limits, monitor function performance.

3. **Webhook Retry Storage**: Should failed webhook payloads be stored in Neon database? Database ensures durability for Inngest's retry mechanism.

4. **Platform Adapter Extensibility**: Generic crawler sufficient for MVP, but should we pre-build adapters for top 3 platforms (Amazon, Shopify, WooCommerce)?

5. **Monitoring & Alerting**: Inngest dashboard provides function monitoring. Do we need external monitoring (e.g., UptimeRobot, Sentry)? Or rely on Inngest logs and API health checks?

---

## References

- **URL Normalization**: [url-normalize docs](https://github.com/niksite/url-normalize), [w3lib docs](https://w3lib.readthedocs.io/)
- **crawl4ai**: [GitHub repository](https://github.com/unclecode/crawl4ai), [Examples](https://crawl4ai.com/mkdocs/examples/)
- **Inngest Documentation**: [Official docs](https://www.inngest.com/docs), [Function patterns](https://www.inngest.com/docs/functions)
- **HMAC Webhooks**: [Stripe signature verification](https://stripe.com/docs/webhooks/signatures), [GitHub webhook security](https://docs.github.com/en/webhooks/using-webhooks/validating-webhook-deliveries)
- **PostgreSQL Partitioning**: [Official docs](https://www.postgresql.org/docs/current/ddl-partitioning.html), [Performance benchmarks](https://www.postgresql.org/docs/current/ddl-partition-pruning.html)
- **bcrypt Security**: [OWASP recommendations](https://cheatsheetseries.owasp.org/cheatsheets/Password_Storage_Cheat_Sheet.html)
- **Docker Compose**: [Official docs](https://docs.docker.com/compose/), [Health checks](https://docs.docker.com/compose/compose-file/05-services/#healthcheck)

---

**Status**: ✅ Research complete - Ready for Phase 1 (Design & Contracts)
