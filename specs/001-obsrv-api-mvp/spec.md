# Feature Specification: Obsrv API - E-commerce Monitoring System MVP

**Feature Branch**: `001-obsrv-api-mvp`
**Created**: 2025-11-02
**Status**: Draft
**Input**: User description: "Generate comprehensive specifications for the Obsrv API - a low-cost e-commerce monitoring system hosted on a single VPS. Project Overview: Company: Obsrv - software agency for market research via competitor data monitoring; Core functionality: Monitor any e-commerce websites, save daily data, send webhook notifications to our clients ERPs; Deployment constraints: Monolith architecture, single VPS hosting, for minimal costs; Target: MVP with simple infrastructure. Architecture Requirements: Single VPS with Docker Compose stack; FastAPI (Python) for REST APIs; Worker: Celery + crawl4ai for daily product data collection; Database: PostgreSQL for products, history, and crawl logs; Cache/Queue: Redis for Celery tasks and caching; Website registration and monitoring setup; Daily automated crawling with crawl4ai; Price/stock change detection; Historical data tracking; Authentication is managed via API Key, that can be invalidated on demand. Technical Constraints: JSONB storage for flexible crawl results; Celery Bea"

## Clarifications

### Session 2025-11-02

- Q: How should the system uniquely identify products across crawls to accurately track changes? → A: URL normalization with product identifier extraction - remove tracking params, extract SKU/product ID from URL or page content
- Q: Should the system notify clients of every price change regardless of magnitude, or apply a threshold filter? → A: Configurable threshold with sensible defaults (1% default) - clients can adjust per-website
- Q: How should the system identify which products to monitor when a website is registered? → A: Hybrid approach - client provides seed URLs (categories or products), system discovers related products with client approval
- Q: How long should the system retain historical crawl data before archival or deletion? → A: 90 days default with configurable retention per website - balance of cost and flexibility
- Q: How should webhook receivers verify the authenticity of incoming webhook notifications? → A: HMAC signature with shared secret - system signs webhook payload, client verifies signature using shared secret

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Register Target Website for Monitoring (Priority: P1)

A client needs to register an e-commerce website URL for continuous monitoring. The system captures the initial product data and sets up daily tracking.

**Why this priority**: This is the foundation of the entire system - without registered websites, no monitoring can occur. This represents the absolute minimum for a viable product.

**Independent Test**: Can be fully tested by providing a website URL through the API, verifying that the system accepts the registration, performs initial data collection, and stores the baseline product information. Delivers immediate value by capturing the first snapshot of competitor data.

**Acceptance Scenarios**:

1. **Given** a valid e-commerce website with seed URLs (product or category pages), **When** client submits registration via API with valid API key, **Then** system accepts the registration, assigns a unique tracking ID, performs product discovery from seed URLs, returns discovered products for approval, and begins monitoring approved products
2. **Given** an invalid or malformed seed URL, **When** client attempts registration, **Then** system rejects the request with clear error message explaining the validation failure
3. **Given** a duplicate website URL for the same client, **When** client attempts to register again, **Then** system identifies the duplicate and returns existing tracking ID with option to add new seed URLs for additional product discovery
4. **Given** seed URLs that discover more than 100 products, **When** discovery completes, **Then** system returns all discovered products ranked by relevance and prompts client to select up to 100 products to monitor
5. **Given** approved discovered products, **When** client confirms selection, **Then** system performs initial baseline crawl and begins scheduled monitoring

---

### User Story 2 - Receive Automated Change Notifications (Priority: P2)

Clients need to receive immediate webhook notifications when monitored products change price or stock status, enabling them to react to competitor movements in real-time.

**Why this priority**: This is the core value proposition - automated change detection and notification. Without this, clients would need to manually check data, defeating the purpose of monitoring.

**Independent Test**: Can be tested by registering a webhook endpoint, simulating or waiting for a product change, and verifying that the webhook receives accurate change data with before/after values. Delivers clear value by automating the competitive intelligence workflow.

**Acceptance Scenarios**:

1. **Given** a monitored product with established baseline price, **When** daily crawl detects price change exceeding threshold, **Then** system sends webhook notification to client's ERP endpoint with product details, old price, new price, timestamp, change percentage, and HMAC signature for verification
2. **Given** a monitored product with established stock status, **When** daily crawl detects stock status change (in-stock to out-of-stock or vice versa), **Then** system sends webhook notification with stock status transition details and HMAC signature
3. **Given** client's webhook endpoint is temporarily unavailable, **When** system attempts to send notification, **Then** system retries webhook delivery with exponential backoff (3 attempts over 1 hour) and logs delivery status
4. **Given** multiple products change simultaneously, **When** daily crawl completes, **Then** system batches notifications appropriately (configurable: immediate per-product or daily summary) to avoid overwhelming client endpoints
5. **Given** a webhook secret, **When** client rotates the secret via API, **Then** system immediately uses new secret for all subsequent webhook signatures and provides brief grace period for old secret validation

---

### User Story 3 - Query Historical Product Data (Priority: P3)

Clients need to retrieve historical price and stock data for monitored products to perform trend analysis and generate competitive intelligence reports.

**Why this priority**: While valuable for analytics, this is secondary to the core monitoring and notification functionality. Clients can still receive real-time alerts without historical queries.

**Independent Test**: Can be tested by retrieving historical records for a specific product over a date range, verifying that all daily snapshots are returned with accurate timestamps and data values. Delivers value by enabling trend analysis and reporting.

**Acceptance Scenarios**:

1. **Given** a product with 30 days of monitoring history, **When** client queries historical data via API with date range, **Then** system returns all daily snapshots with timestamps, prices, stock status, and any detected changes
2. **Given** a product with extensive history, **When** client queries without date range limits, **Then** system returns paginated results (default 50 records per page) with pagination metadata
3. **Given** multiple products from the same website, **When** client queries all products for a specific date, **Then** system returns consolidated snapshot showing competitive landscape at that point in time
4. **Given** a product that was monitored then paused, **When** client queries historical data, **Then** system returns all available data with clear indicators of monitoring gaps

---

### User Story 4 - Manage API Keys (Priority: P4)

Clients need to generate, invalidate, and rotate API keys to maintain secure access to their monitoring data and control system access.

**Why this priority**: Essential for security but not blocking for MVP functionality. Initial API keys can be provisioned manually during client onboarding.

**Independent Test**: Can be tested by generating new API key, using it for authentication, invalidating it, and verifying that subsequent requests fail. Delivers value by enabling self-service security management.

**Acceptance Scenarios**:

1. **Given** a valid authenticated session, **When** client requests new API key generation, **Then** system creates cryptographically secure key, stores hash securely, and returns key once (never stored in plaintext)
2. **Given** an active API key, **When** client invalidates the key, **Then** system immediately marks key as invalid and all subsequent requests using that key receive 401 Unauthorized responses
3. **Given** multiple active API keys for one client, **When** client lists their keys, **Then** system returns metadata for each key (creation date, last used timestamp, key prefix) without revealing full key values
4. **Given** a compromised API key scenario, **When** client invalidates old key and generates replacement, **Then** system enables zero-downtime key rotation by allowing brief overlap period for client systems to update

---

### User Story 5 - Monitor Crawl Health and Status (Priority: P5)

System administrators and clients need visibility into crawl execution status, success rates, and error conditions to maintain service reliability.

**Why this priority**: Important for operational excellence but not required for basic functionality. Initial MVP can operate with basic logging.

**Independent Test**: Can be tested by executing crawls and querying status endpoints, verifying that crawl logs show execution times, success/failure status, and error details. Delivers value by enabling proactive problem resolution.

**Acceptance Scenarios**:

1. **Given** daily crawl schedule, **When** crawls execute, **Then** system logs each crawl attempt with timestamp, duration, products processed, changes detected, and final status
2. **Given** a crawl failure (network timeout, website structure change), **When** error occurs, **Then** system logs detailed error information, marks crawl for retry, and alerts if repeated failures occur for same website
3. **Given** a client monitoring multiple websites, **When** client queries crawl status, **Then** system returns health dashboard showing last successful crawl time, success rate (last 7 days), and any active alerts
4. **Given** a website that changes structure breaking crawl logic, **When** system detects consistent parsing failures, **Then** system flags website for manual review and continues attempting crawls with degraded mode (basic extraction)

---

### Edge Cases

- What happens when a monitored website goes offline or returns 404/500 errors consistently? System should log errors, pause crawling after 3 consecutive failures, and notify client that monitoring is paused pending website recovery.

- How does the system handle e-commerce websites with heavy anti-bot protection (rate limiting, CAPTCHAs)? System should implement respectful crawling (configurable delays, user agent rotation) and gracefully back off when detection occurs. For MVP, websites requiring JavaScript rendering or CAPTCHA solving may be unsupported.

- What happens when product URLs change or products are delisted? System normalizes URLs by removing query parameters and tracking codes to handle minor URL variations. Products are tracked by normalized URL combined with extracted product identifiers (SKU/product code). If normalized URL returns 404, system marks product as "delisted" in historical data and includes delisting timestamp in change notifications. If product identifier remains stable but URL structure changes significantly, system may create duplicate product record requiring manual reconciliation.

- How does the system handle websites with thousands of products? For MVP, monitoring is limited to 100 products per website to ensure conservative resource usage and reliable performance on a single VPS. Clients provide seed URLs (category or product pages), system discovers products from those seeds, and clients approve up to 100 products to monitor. If discovery finds more than 100 products, system ranks by relevance (based on seed URL proximity, product availability) and presents top candidates for client selection.

- What happens when webhook endpoints return errors repeatedly? After 3 failed attempts with exponential backoff, system marks webhook as failed and stores notification data for client to retrieve via API. System resumes webhook delivery when client updates endpoint.

- How does the system handle time zones for daily crawls? All timestamps are stored in UTC. Daily crawls execute at configurable time (default: 2 AM UTC) to minimize impact on target websites. Clients can specify preferred crawl window.

- What happens when a website uses dynamic pricing (prices change every few minutes)? System supports configurable crawl frequency from 2-4 times per day. Default is once daily at 2 AM UTC, but clients can configure multiple daily crawls (e.g., every 6, 8, or 12 hours) for volatile pricing scenarios. Each crawl schedule must respect website rate limits and avoid overwhelming target sites.

- How does the system ensure data consistency during crawl retries? Each crawl attempt is atomic - either all product data for a website is updated together, or none is updated. Partial crawl results are not persisted to avoid inconsistent snapshots.

- How are small price fluctuations handled? System applies a configurable price change threshold (default 1%) per website to filter trivial fluctuations before sending notifications. All price changes are logged in history regardless of threshold, but only changes exceeding the threshold trigger webhook notifications. Stock status changes always trigger notifications regardless of threshold. Clients can adjust threshold per-website (e.g., 5% for volatile markets, 0.1% for precise tracking).

- How does product discovery handle ambiguous page types? System uses common e-commerce URL patterns and page structure heuristics to identify product pages. If seed URL is a category/listing page, system extracts product links. If seed URL is already a product page, system treats it as direct product specification. Discovery errors (e.g., seed URL is neither product nor category) are flagged for client review. For MVP, discovery logic may require manual tuning per e-commerce platform.

- How long is historical data retained? System retains detailed historical snapshots for 90 days by default (configurable per website from 30 to 365 days). Data older than retention period is automatically purged during nightly maintenance. Aggregated statistics (min/max/average prices per product per month) are preserved indefinitely for long-term trend visualization without storing individual snapshots. Clients can extend retention for specific websites at additional storage cost.

- How are webhooks secured against spoofing? System signs each webhook payload using HMAC-SHA256 with client's unique webhook secret, including signature in X-Obsrv-Signature header. Clients verify authenticity by recomputing signature using their secret and comparing to header value. Webhook secrets are generated during client registration and can be rotated on demand via API. During secret rotation, system maintains 1-hour grace period accepting both old and new secrets to prevent disruption during client-side updates.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: System MUST provide REST API endpoints for website registration accepting website base URL, seed URLs (product or category pages), client identification, and optional monitoring configuration parameters
- **FR-002**: System MUST validate website URLs for proper format, accessibility, and basic structure before accepting registration
- **FR-003**: System MUST authenticate all API requests using API key authentication passed via Authorization header or query parameter
- **FR-004**: System MUST support API key invalidation on demand, taking effect immediately for all subsequent requests
- **FR-005**: System MUST perform product discovery crawl from provided seed URLs (category or product pages) to identify products for monitoring, then perform initial baseline crawl on client-approved products to establish baseline data
- **FR-005a**: System MUST extract product links from seed URLs using common e-commerce patterns (product listing pages, product detail page links) and present discovered products to client for approval before monitoring begins
- **FR-005b**: System MUST allow clients to approve, reject, or manually add product URLs to the monitoring list, enforcing the 100 product per website limit
- **FR-006**: System MUST execute daily automated crawls for all active monitored websites at scheduled times
- **FR-007**: System MUST extract product data including product name, price, stock status, product URL, and timestamp from target websites, and MUST normalize product URLs (removing tracking parameters, trailing slashes) and extract stable product identifiers (SKU, product code) from URL or page content for accurate cross-crawl tracking
- **FR-008**: System MUST store crawl results in flexible schema format to accommodate varying product attributes across different e-commerce platforms
- **FR-009**: System MUST detect price changes by comparing current crawl data against previous crawl data for the same product, applying a configurable percentage threshold (default 1%) to filter insignificant fluctuations before triggering notifications
- **FR-010**: System MUST detect stock status changes (in-stock, out-of-stock, limited availability) between consecutive crawls
- **FR-011**: System MUST maintain complete historical record of all crawl snapshots with timestamps for trend analysis, with default retention period of 90 days (configurable per website)
- **FR-011a**: System MUST automatically purge historical data older than the configured retention period to manage storage growth, while preserving aggregated statistics for long-term trend analysis
- **FR-012**: System MUST send webhook notifications to client-specified endpoints when product changes exceeding the configured threshold are detected (price changes meeting minimum percentage threshold, all stock status changes)
- **FR-013**: System MUST include in webhook payload: product identification, change type (price/stock), old value, new value, timestamp, and change metadata, and MUST include HMAC-SHA256 signature in X-Obsrv-Signature header computed from payload using client's webhook secret for authentication
- **FR-013a**: System MUST generate unique webhook secret for each client during registration and provide API endpoints for clients to rotate webhook secrets on demand
- **FR-014**: System MUST retry failed webhook deliveries with exponential backoff up to 3 attempts over 1 hour
- **FR-015**: System MUST log all webhook delivery attempts including timestamps, response codes, and retry counts
- **FR-016**: System MUST provide API endpoints to query historical product data with filtering by date range, product ID, and website
- **FR-017**: System MUST return paginated results for historical queries with configurable page size (default 50, max 500 records)
- **FR-018**: System MUST log all crawl attempts including execution time, success/failure status, products processed, and error details
- **FR-019**: System MUST implement crawl error handling including network timeouts, HTTP errors, and parsing failures with appropriate retries
- **FR-020**: System MUST provide API endpoints to query crawl logs and execution status for monitoring and debugging
- **FR-021**: System MUST respect website crawling etiquette including configurable delays between requests and proper User-Agent headers
- **FR-022**: System MUST isolate crawl tasks from API request handling to prevent blocking operations
- **FR-023**: System MUST support concurrent crawling of multiple websites with resource limits to prevent system overload
- **FR-024**: System MUST handle graceful shutdown ensuring in-progress crawls complete or are safely rolled back
- **FR-025**: System MUST provide API endpoints for API key generation returning cryptographically secure keys
- **FR-026**: System MUST store API keys securely using one-way hashing, never storing plaintext keys
- **FR-027**: System MUST provide API endpoints to list client's active API keys showing metadata without exposing full key values
- **FR-028**: System MUST associate each monitored website with client identity for access control and billing
- **FR-029**: System MUST prevent clients from accessing data for websites they do not own or have permission to monitor
- **FR-030**: System MUST provide health check endpoints for deployment monitoring and load balancer integration

### Key Entities

- **Monitored Website**: Represents an e-commerce website registered for continuous monitoring. Key attributes include website base URL, seed URLs (categories or products used for discovery), client ownership, registration timestamp, monitoring status (active/paused/pending-approval), monitoring configuration (crawl frequency, products to track, price change threshold percentage - default 1%, historical data retention period - default 90 days), discovered products pending approval, approved products list, last successful crawl timestamp, webhook endpoint URL, and webhook secret for HMAC signature verification.

- **Product**: Represents an individual product being tracked on a monitored website. Key attributes include normalized product URL (cleaned of tracking parameters), extracted product identifier (SKU/product code), original product URL, product name, current price, current stock status, last updated timestamp, and relationship to parent website. Products are uniquely identified by the combination of normalized URL and extracted identifier to ensure accurate tracking across crawls.

- **Product History Record**: Represents a point-in-time snapshot of product data. Key attributes include product reference, snapshot timestamp, price at that time, stock status at that time, change flags (was price changed, was stock changed), and raw crawl data in flexible format.

- **Crawl Execution Log**: Represents a single crawl operation execution. Key attributes include website reference, execution start time, execution end time, status (success/failure/partial), products processed count, changes detected count, error details if failed, and retry information.

- **Webhook Delivery Log**: Represents an attempt to deliver change notification. Key attributes include product change reference, target webhook URL, delivery timestamp, HTTP response code, delivery status (pending/success/failed), retry count, and response body for debugging.

- **API Key**: Represents authentication credential for client access. Key attributes include hashed key value, client ownership, creation timestamp, last used timestamp, invalidation timestamp (null if active), and key metadata (description, permissions scope).

- **Client Account**: Represents a customer of the Obsrv monitoring service. Key attributes include unique client identifier, registration timestamp, associated websites list, active API keys list, webhook secrets (current and previous during rotation grace period), subscription tier, and webhook configuration.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: Clients can register a new website for monitoring and receive initial product data within 5 minutes of submission
- **SC-002**: System successfully completes 95% of scheduled daily crawls without errors or manual intervention
- **SC-003**: Product change notifications are delivered to client webhook endpoints within 10 minutes of crawl completion
- **SC-004**: System processes and compares product data to detect changes for 100 products across all monitored websites within 30 minutes during daily crawl window
- **SC-005**: API response times for historical data queries remain under 2 seconds for datasets covering 90 days of history
- **SC-006**: System maintains 99% uptime for API endpoints over a 30-day period
- **SC-007**: Webhook delivery success rate exceeds 90% (including retries) for endpoints with proper availability
- **SC-008**: Zero unauthorized access incidents - all API requests without valid keys are rejected
- **SC-009**: Crawl error rate remains below 5% (excluding errors caused by target website downtime)
- **SC-010**: System handles at least 10 concurrent monitored websites with daily crawling without resource exhaustion
- **SC-011**: Historical data retrieval provides complete audit trail - 100% of crawl snapshots are preserved and queryable
- **SC-012**: Clients can invalidate compromised API keys and verify access is blocked within 1 minute

### Assumptions

- E-commerce websites to be monitored use standard HTML structure accessible without JavaScript rendering (for MVP)
- Target websites do not employ aggressive anti-bot measures that require sophisticated bypass techniques
- Clients will provide webhook endpoints with reasonable availability (>95% uptime)
- Daily monitoring frequency is sufficient for MVP - real-time or hourly monitoring is out of scope
- Single VPS resources (assumed: 4 CPU cores, 8GB RAM, 100GB storage) are adequate for monitoring up to 20 websites with 100 products each with 90-day retention (estimated: 360MB for historical snapshots + overhead)
- Clients are responsible for ensuring they have legal right to monitor competitor websites in their jurisdiction
- Product identification on target websites is stable (URLs or SKUs don't change frequently)
- Network bandwidth for VPS is sufficient for daily crawls (estimated: <1GB daily traffic for 20 websites)
- PostgreSQL and Redis are adequate for MVP scale without requiring distributed database setup
- Crawl extraction logic will require manual configuration per website (automated extraction learning is out of scope for MVP)

### Dependencies

- Target e-commerce websites must be publicly accessible without authentication requirements
- Client ERP systems or webhook receivers must be accessible from VPS network (no VPN required)
- DNS resolution must be reliable for target website URLs
- Container orchestration platform (Docker Compose) must be properly configured on VPS
- SSL/TLS certificates for API endpoints if HTTPS is required (recommended for production)
- Time synchronization (NTP) for accurate timestamp consistency across system components

### Out of Scope

- Real-time monitoring or sub-daily crawl frequencies (only daily crawls in MVP)
- JavaScript rendering for dynamic websites (only static HTML extraction)
- CAPTCHA solving or sophisticated anti-bot bypass mechanisms
- Automated extraction logic learning (requires manual configuration per website)
- Multi-region deployment or high availability setup (single VPS only)
- Built-in analytics dashboard or visualization (clients consume data via API/webhooks)
- User interface for non-technical users (API-only system)
- Support for monitoring websites requiring authentication/login
- Image analysis or visual product comparison
- Price prediction or trend forecasting
- Integration with specific ERP systems (generic webhook notifications only)
- Monitoring of product reviews, ratings, or seller information (price and stock only)
- Compliance with data privacy regulations specific to certain jurisdictions (client responsibility)
- Automatic crawl logic adjustment when website structure changes (requires manual update)

## Constraints

### Technical Constraints

- Single VPS deployment - no distributed architecture or horizontal scaling in MVP
- Monolithic application architecture with all components on one host
- Container-based deployment using Docker Compose for service orchestration
- Limited computational resources constrain maximum number of monitored websites and crawl parallelism
- Daily crawl frequency as baseline (higher frequencies increase resource requirements)
- Storage growth is linear with (number of products × crawl frequency × retention period)
- Network bandwidth limitations may constrain crawl parallelism for media-heavy websites

### Operational Constraints

- Manual deployment and configuration (no automated CI/CD pipeline in MVP)
- Manual crawl extraction logic configuration for each new website
- Limited observability - basic logging without sophisticated monitoring platform
- Single point of failure - VPS downtime means complete system unavailability
- Backup and disaster recovery require manual procedures
- Performance tuning requires application restart (no dynamic reconfiguration)
- Crawl scheduling changes require system configuration updates

### Business Constraints

- MVP budget constraints necessitate single VPS hosting model
- Limited support resources mean system must be operationally simple
- Time-to-market pressure prioritizes core functionality over advanced features
- Target market is small-to-medium businesses with cost sensitivity
- Competitive pressure requires rapid MVP validation before investing in scalable architecture
