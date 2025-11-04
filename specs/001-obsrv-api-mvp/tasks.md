# Tasks: Obsrv API - E-commerce Monitoring System MVP

**Input**: Design documents from `/specs/001-obsrv-api-mvp/`
**Prerequisites**: plan.md, spec.md, research.md, data-model.md, contracts/
**Branch**: `001-obsrv-api-mvp`

**Tests**: Not explicitly requested in the specification - tests are OPTIONAL for MVP

**Organization**: Tasks are grouped by user story to enable independent implementation and testing of each story.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel (different files, no dependencies)
- **[Story]**: Which user story this task belongs to (e.g., US1, US2, US3)
- Include exact file paths in descriptions

## Path Conventions

Based on plan.md, this is a backend-only project with the following structure:
- **Backend**: `backend/src/` (models, services, API endpoints, core)
- **Tests**: `backend/tests/` (unit, integration, contract)
- **Shared fixtures**: `tests/fixtures/`

---

## Phase 1: Setup (Shared Infrastructure)

**Purpose**: Project initialization and basic structure

- [X] T001 Create project directory structure: backend/src/{models,services,api,core}/, backend/tests/{unit,integration,contract}/, tests/{fixtures,utils}/
- [X] T002 [P] Initialize Python 3.11+ project with pyproject.toml and setup dependencies: FastAPI, Pydantic, SQLAlchemy, Alembic, crawl4ai, inngest, url-normalize, w3lib, bcrypt, httpx, pytest
- [X] T003 [P] Configure ruff linting and black formatting in pyproject.toml
- [X] T004 [P] Create .env.example with all required environment variables (DATABASE_URL, INNGEST_EVENT_KEY, INNGEST_SIGNING_KEY, SECRET_KEY, etc.)
- [X] T005 [P] Create .gitignore for Python projects (.env, __pycache__/, *.pyc, .pytest_cache/, etc.)
- [X] T006 [P] Create Docker Compose configuration in docker-compose.yml for API service with health checks
- [X] T007 [P] Create Dockerfile for FastAPI application with Python 3.11+ base image

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: Core infrastructure that MUST be complete before ANY user story can be implemented

**⚠️ CRITICAL**: No user story work can begin until this phase is complete

- [X] T008 Setup Neon PostgreSQL connection configuration in backend/src/core/database.py with connection pooling
- [X] T009 Configure Alembic migrations framework in backend/alembic/ with env.py and initial migration structure
- [X] T010 Create database schema migration for all entities in backend/alembic/versions/001_initial_schema.py based on data-model.md (clients, api_keys, monitored_websites, products, product_history, crawl_execution_logs, webhook_delivery_logs, product_statistics)
- [X] T011 [P] Implement API key authentication middleware in backend/src/core/auth.py with bcrypt verification and rate limiting
- [X] T012 [P] Setup FastAPI application factory in backend/src/api/main.py with CORS, error handlers, middleware registration
- [X] T013 [P] Create base Pydantic models and response schemas in backend/src/models/base.py (BaseModel, TimestampMixin, PaginationResponse, ErrorResponse)
- [X] T014 [P] Implement centralized error handling and custom exceptions in backend/src/core/exceptions.py (APIException, AuthenticationError, ValidationError, ResourceNotFoundError)
- [X] T015 [P] Configure structured logging with correlation IDs in backend/src/core/logging.py
- [X] T016 [P] Setup environment configuration management in backend/src/core/config.py using Pydantic Settings
- [X] T017 [P] Implement health check endpoints in backend/src/api/health.py (basic /health, detailed /health/detailed with database and Inngest connectivity checks)
- [X] T018 Setup Inngest client configuration in backend/src/core/inngest.py with event key and signing key
- [X] T019 [P] Create URL normalization utility in backend/src/core/url_utils.py using url-normalize and w3lib for tracking parameter removal
- [X] T020 [P] Create product ID extraction utility in backend/src/core/product_extractors.py with platform-specific patterns (Amazon, Shopify, generic) and HTML meta tag fallbacks

**Checkpoint**: Foundation ready - user story implementation can now begin in parallel

---

## Phase 3: User Story 1 - Register Target Website for Monitoring (Priority: P1) 🎯 MVP

**Goal**: Enable clients to register e-commerce websites for monitoring with product discovery and baseline data collection

**Independent Test**: Register a website via API with seed URLs, verify system performs product discovery, returns discovered products for approval, and allows selection of up to 100 products to monitor

### Implementation for User Story 1

- [ ] T021 [P] [US1] Create Client entity model in backend/src/models/client.py with SQLAlchemy ORM mapping (matches data-model.md Client Account)
- [ ] T022 [P] [US1] Create APIKey entity model in backend/src/models/api_key.py with SQLAlchemy ORM mapping and bcrypt hashing
- [ ] T023 [P] [US1] Create MonitoredWebsite entity model in backend/src/models/website.py with status state machine (pending_approval → active → paused/failed)
- [ ] T024 [P] [US1] Create Product entity model in backend/src/models/product.py with normalized_url indexing and stock status enum
- [ ] T025 [P] [US1] Create CrawlExecutionLog entity model in backend/src/models/crawl_log.py with execution tracking fields
- [ ] T026 [P] [US1] Create Pydantic request/response schemas for website registration in backend/src/api/schemas/website_schemas.py (WebsiteRegistrationRequest, WebsiteRegistrationResponse, Website, DiscoveredProduct)
- [ ] T027 [US1] Implement crawl4ai integration service in backend/src/services/crawler_service.py with AsyncPlaywrightCrawlerStrategy, rate limiting (10 req/min per domain), retry logic (3 attempts with exponential backoff)
- [ ] T028 [US1] Implement product discovery service in backend/src/services/discovery_service.py that extracts product links from seed URLs using common e-commerce patterns and ranks by relevance
- [ ] T029 [US1] Implement baseline crawl service in backend/src/services/baseline_crawl_service.py that crawls approved products to establish initial data (price, stock, name)
- [ ] T030 [US1] Create Inngest function for product discovery in backend/src/services/inngest_functions/discover_products.py that processes seed URLs and stores discovered products in pending state
- [ ] T031 [US1] Create Inngest function for baseline crawl in backend/src/services/inngest_functions/baseline_crawl.py that crawls approved products and creates initial product records
- [ ] T032 [US1] Implement WebsiteService in backend/src/services/website_service.py with methods: register_website(), get_website(), list_websites(), update_website(), delete_website()
- [ ] T033 [US1] Implement POST /v1/websites endpoint in backend/src/api/routes/websites.py that accepts registration, validates URLs, triggers Inngest product discovery, returns 202 with website_id and discovery_job_id
- [ ] T034 [US1] Implement GET /v1/websites endpoint in backend/src/api/routes/websites.py with pagination and status filtering
- [ ] T035 [US1] Implement GET /v1/websites/{website_id} endpoint in backend/src/api/routes/websites.py with ownership validation
- [ ] T036 [US1] Implement PATCH /v1/websites/{website_id} endpoint in backend/src/api/routes/websites.py for updating crawl frequency, threshold, webhook settings
- [ ] T037 [US1] Implement DELETE /v1/websites/{website_id} endpoint in backend/src/api/routes/websites.py with cascade deletion of products and history
- [ ] T038 [US1] Implement GET /v1/websites/{website_id}/discovered-products endpoint in backend/src/api/routes/websites.py that returns pending products with discovery ranking
- [ ] T039 [US1] Implement POST /v1/websites/{website_id}/approve-products endpoint in backend/src/api/routes/websites.py that validates selection (max 100), triggers Inngest baseline crawl, updates website status to active
- [ ] T040 [US1] Add API route registration in backend/src/api/main.py for websites router
- [ ] T041 [US1] Add input validation for website registration (valid URLs, supported crawl frequencies, threshold ranges) in backend/src/api/schemas/website_schemas.py
- [ ] T042 [US1] Add error handling for duplicate website registration (409 Conflict) in backend/src/services/website_service.py
- [ ] T043 [US1] Add logging for website registration lifecycle events (registration, discovery start/complete, approval, baseline crawl) in relevant services

**Checkpoint**: At this point, User Story 1 should be fully functional - clients can register websites, discover products, approve them, and have baseline data collected

---

## Phase 4: User Story 2 - Receive Automated Change Notifications (Priority: P2)

**Goal**: Automatically detect price/stock changes during daily crawls and send HMAC-authenticated webhook notifications to client endpoints

**Independent Test**: Register webhook endpoint, simulate or trigger a product change, verify webhook receives accurate notification with before/after values and valid HMAC signature

### Implementation for User Story 2

- [ ] T044 [P] [US2] Create ProductHistoryRecord entity model in backend/src/models/product_history.py with time-series partitioning fields and change detection flags
- [ ] T045 [P] [US2] Create WebhookDeliveryLog entity model in backend/src/models/webhook_log.py with retry tracking and delivery status enum
- [ ] T046 [P] [US2] Create Pydantic schemas for webhook payloads in backend/src/api/schemas/webhook_schemas.py (PriceChangeEvent, StockChangeEvent matching webhook-payload.md specification)
- [ ] T047 [US2] Implement change detection service in backend/src/services/change_detector.py that compares current vs previous product data, applies price threshold filtering (configurable %), identifies stock status transitions
- [ ] T048 [US2] Implement HMAC signature generation in backend/src/core/webhook_security.py following Stripe-style format: t={timestamp},v1={signature} with SHA256 and replay protection (5-minute window)
- [ ] T049 [US2] Implement webhook delivery service in backend/src/services/webhook_service.py with HTTP POST, signature header injection, 10-second timeout, status code validation
- [ ] T050 [US2] Implement webhook retry logic in backend/src/services/webhook_service.py with exponential backoff schedule (immediate, +5min, +30min) and exhaustion handling after 3 attempts
- [ ] T051 [US2] Create Inngest function for scheduled crawls in backend/src/services/inngest_functions/scheduled_crawl.py that processes all active websites, crawls products, detects changes, logs execution
- [ ] T052 [US2] Create Inngest function for webhook delivery in backend/src/services/inngest_functions/deliver_webhook.py that sends notifications with automatic retry on failure
- [ ] T053 [US2] Implement cron scheduling for daily crawls in backend/src/services/inngest_functions/scheduled_crawl.py using Inngest cron trigger (default 2 AM UTC, configurable per website)
- [ ] T054 [US2] Implement POST /v1/auth/webhook-secret endpoint in backend/src/api/routes/auth.py for webhook secret rotation with 1-hour grace period
- [ ] T055 [US2] Add ProductHistoryRecord creation in crawl service when changes detected in backend/src/services/crawler_service.py
- [ ] T056 [US2] Add WebhookDeliveryLog creation for all delivery attempts in backend/src/services/webhook_service.py
- [ ] T057 [US2] Add webhook batching support (configurable: per-product immediate vs daily summary) in backend/src/services/webhook_service.py
- [ ] T058 [US2] Add webhook endpoint validation (HTTPS required in production) during website registration in backend/src/services/website_service.py
- [ ] T059 [US2] Add logging for change detection and webhook delivery (detected changes, delivery attempts, failures, retries) in relevant services

**Checkpoint**: At this point, User Stories 1 AND 2 should both work - websites can be registered, monitored, and change notifications delivered automatically

---

## Phase 5: User Story 3 - Query Historical Product Data (Priority: P3)

**Goal**: Provide API endpoints to retrieve historical price/stock snapshots for trend analysis and reporting

**Independent Test**: Register and monitor a product for multiple days, query historical data with date range filter, verify all daily snapshots are returned with accurate values

### Implementation for User Story 3

- [ ] T060 [P] [US3] Create Pydantic schemas for historical queries in backend/src/api/schemas/product_schemas.py (ProductHistoryRecord, ProductHistoryResponse with pagination)
- [ ] T061 [US3] Implement ProductService in backend/src/services/product_service.py with methods: get_product(), list_products(), get_product_history()
- [ ] T062 [US3] Implement efficient historical query with date range filtering in backend/src/services/product_service.py using indexed queries on (product_id, crawl_timestamp)
- [ ] T063 [US3] Implement pagination for historical queries in backend/src/services/product_service.py with configurable page size (default 50, max 500)
- [ ] T064 [US3] Implement GET /v1/products endpoint in backend/src/api/routes/products.py with filtering by website_id, stock_status, and pagination
- [ ] T065 [US3] Implement GET /v1/products/{product_id} endpoint in backend/src/api/routes/products.py with ownership validation
- [ ] T066 [US3] Implement GET /v1/products/{product_id}/history endpoint in backend/src/api/routes/products.py with date range parameters (start_date, end_date) and pagination
- [ ] T067 [US3] Add API route registration in backend/src/api/main.py for products router
- [ ] T068 [US3] Add query parameter validation for date ranges (ISO 8601 format, start < end, max range limits) in backend/src/api/schemas/product_schemas.py
- [ ] T069 [US3] Add response optimization for large historical datasets (consider materialized view for latest state) in backend/src/services/product_service.py
- [ ] T070 [US3] Add logging for historical data queries (query parameters, result counts, execution time) in backend/src/services/product_service.py

**Checkpoint**: All three priority user stories (P1, P2, P3) should now be independently functional

---

## Phase 6: User Story 4 - Manage API Keys (Priority: P4)

**Goal**: Enable clients to generate, list, invalidate, and rotate API keys for secure access control

**Independent Test**: Generate new API key via API, use it for authentication, invalidate it, verify subsequent requests fail with 401

### Implementation for User Story 4

- [ ] T071 [P] [US4] Create Pydantic schemas for API key management in backend/src/api/schemas/auth_schemas.py (ApiKeyCreateRequest, ApiKeyResponse, ApiKeyMetadata)
- [ ] T072 [US4] Implement ApiKeyService in backend/src/services/api_key_service.py with methods: generate_key(), list_keys(), invalidate_key(), verify_key()
- [ ] T073 [US4] Implement secure API key generation in backend/src/services/api_key_service.py using secrets.token_urlsafe(32) with format: obsrv_live_{random_43_chars}
- [ ] T074 [US4] Implement bcrypt hashing for API key storage in backend/src/services/api_key_service.py with work factor 12
- [ ] T075 [US4] Implement POST /v1/auth/keys endpoint in backend/src/api/routes/auth.py that generates key, returns it once, requires admin permission scope
- [ ] T076 [US4] Implement GET /v1/auth/keys endpoint in backend/src/api/routes/auth.py that returns metadata (key_prefix, created_at, last_used_at) without full key values
- [ ] T077 [US4] Implement DELETE /v1/auth/keys/{key_id} endpoint in backend/src/api/routes/auth.py that immediately invalidates key (sets invalidated_at timestamp)
- [ ] T078 [US4] Add API route registration in backend/src/api/main.py for auth router
- [ ] T079 [US4] Add permission scope validation (read, write, admin) in backend/src/core/auth.py middleware
- [ ] T080 [US4] Add last_used_at timestamp update on successful authentication in backend/src/core/auth.py
- [ ] T081 [US4] Add rate limiting per API key (1000 requests/hour) in backend/src/core/auth.py
- [ ] T082 [US4] Add logging for API key lifecycle events (generation, usage, invalidation) in backend/src/services/api_key_service.py

**Checkpoint**: User Story 4 complete - clients can fully manage their API keys without manual intervention

---

## Phase 7: User Story 5 - Monitor Crawl Health and Status (Priority: P5)

**Goal**: Provide visibility into crawl execution status, success rates, and error conditions for operational monitoring

**Independent Test**: Execute crawls and query status endpoints, verify crawl logs show execution times, success/failure status, and detailed error information

### Implementation for User Story 5

- [ ] T083 [P] [US5] Create Pydantic schemas for crawl logs in backend/src/api/schemas/crawl_schemas.py (CrawlLog, CrawlLogResponse with pagination)
- [ ] T084 [US5] Implement crawl health monitoring in backend/src/services/crawl_monitor_service.py that tracks success rates, consecutive failures, alert thresholds
- [ ] T085 [US5] Implement automatic website pausing after 3 consecutive crawl failures in backend/src/services/crawl_monitor_service.py
- [ ] T086 [US5] Implement GET /v1/websites/{website_id}/crawl-logs endpoint in backend/src/api/routes/websites.py with status filtering and pagination
- [ ] T087 [US5] Add detailed error logging in crawl execution (network timeouts, parsing failures, HTTP errors) in backend/src/services/crawler_service.py
- [ ] T088 [US5] Add crawl duration tracking (started_at, completed_at, duration_seconds) in backend/src/services/crawler_service.py
- [ ] T089 [US5] Add structured error details in crawl logs (error_type, error_message, stack_trace, affected_products) in backend/src/models/crawl_log.py
- [ ] T090 [US5] Add crawl metrics computation (products_processed, changes_detected, errors_count) in backend/src/services/crawler_service.py
- [ ] T091 [US5] Add health dashboard data aggregation (last 7 days success rate, average duration, alert status) in backend/src/services/crawl_monitor_service.py

**Checkpoint**: All five user stories are now complete and independently functional

---

## Phase 8: Data Retention & Maintenance (Background Operations)

**Purpose**: Automated data lifecycle management to control storage growth

- [ ] T092 [P] Create Inngest function for data retention cleanup in backend/src/services/inngest_functions/cleanup_old_data.py that purges historical data older than configured retention period
- [ ] T093 [P] Create ProductStatistics aggregation service in backend/src/services/statistics_service.py that computes monthly min/max/avg prices before partition drops
- [ ] T094 [P] Implement Inngest cron schedule for weekly cleanup (Sunday 3 AM UTC) in backend/src/services/inngest_functions/cleanup_old_data.py
- [ ] T095 [P] Implement Inngest cron schedule for monthly statistics aggregation in backend/src/services/inngest_functions/aggregate_statistics.py
- [ ] T096 [P] Add logging for retention cleanup operations (records deleted, partitions dropped, statistics aggregated) in cleanup functions

---

## Phase 9: Polish & Cross-Cutting Concerns

**Purpose**: Production readiness, documentation, and deployment preparation

- [ ] T097 [P] Create API documentation using FastAPI's automatic OpenAPI generation in backend/src/api/main.py with descriptions, examples, and response schemas
- [ ] T098 [P] Create README.md at repository root with project overview, quick start, and links to detailed documentation
- [ ] T099 [P] Validate quickstart.md guide by following deployment steps in test environment
- [ ] T100 [P] Create database seeding script for development in backend/scripts/seed_dev_data.py with sample clients, websites, products
- [ ] T101 [P] Configure production Docker Compose with health checks, restart policies, and resource limits in docker-compose.prod.yml
- [ ] T102 [P] Add API request/response logging with correlation IDs for request tracing in backend/src/core/logging.py
- [ ] T103 [P] Add performance monitoring hooks (request duration, database query counts) in backend/src/api/main.py middleware
- [ ] T104 [P] Implement graceful shutdown handling for in-progress operations in backend/src/api/main.py
- [ ] T105 [P] Add CORS configuration for production domains in backend/src/core/config.py
- [ ] T106 [P] Review and apply security hardening (SQL injection prevention via ORM, XSS prevention in API responses, rate limiting) across all endpoints
- [ ] T107 [P] Create deployment checklist document in docs/deployment-checklist.md
- [ ] T108 Run quickstart.md validation on clean VPS to verify end-to-end deployment

---

## Dependencies & Execution Order

### Phase Dependencies

- **Setup (Phase 1)**: No dependencies - can start immediately
- **Foundational (Phase 2)**: Depends on Setup completion - BLOCKS all user stories
- **User Story 1 (Phase 3)**: Depends on Foundational phase completion
- **User Story 2 (Phase 4)**: Depends on Foundational phase completion AND User Story 1 product/website models
- **User Story 3 (Phase 5)**: Depends on Foundational phase completion AND User Story 2 historical data collection
- **User Story 4 (Phase 6)**: Depends on Foundational phase completion (independent from other stories)
- **User Story 5 (Phase 7)**: Depends on Foundational phase completion AND User Story 1 crawl infrastructure
- **Data Retention (Phase 8)**: Depends on User Story 2 historical data structure
- **Polish (Phase 9)**: Depends on all desired user stories being complete

### User Story Dependencies

- **User Story 1 (P1)**: Can start after Foundational (Phase 2) - No dependencies on other stories
- **User Story 2 (P2)**: Requires US1 (needs Product and MonitoredWebsite models) - Can start after US1 models complete
- **User Story 3 (P3)**: Requires US2 (needs ProductHistoryRecord model and data collection) - Can start after US2 complete
- **User Story 4 (P4)**: Independent - Can start after Foundational (Phase 2) in parallel with other stories
- **User Story 5 (P5)**: Requires US1 (needs CrawlExecutionLog model) - Can start after US1 models complete

### Within Each User Story

1. Models before services (data layer first)
2. Core services before Inngest functions (business logic before async tasks)
3. Services before API endpoints (implementation before interface)
4. Core implementation before integration (foundational features before cross-cutting)
5. Story complete before moving to next priority

### Parallel Opportunities

- **Phase 1 (Setup)**: All tasks marked [P] can run in parallel (T002-T007)
- **Phase 2 (Foundational)**: Tasks T011-T017, T019-T020 can run in parallel after T008-T010 complete
- **User Story 1**: Tasks T021-T026 (models and schemas) can run in parallel
- **User Story 2**: Tasks T044-T046 (models and schemas) can run in parallel
- **User Story 3**: Task T060 can start early (just schemas)
- **User Story 4**: Tasks T071-T074 can run mostly in parallel
- **User Story 5**: Tasks T083-T084 can start in parallel
- **Different user stories**: US1 and US4 can be worked on in parallel after Foundational phase; US2 and US4 can overlap after US1 models complete

---

## Parallel Example: Foundational Phase

```bash
# After database setup (T008-T010), launch these together:
Task T011: "Implement API key authentication middleware"
Task T012: "Setup FastAPI application factory"
Task T013: "Create base Pydantic models"
Task T014: "Implement centralized error handling"
Task T015: "Configure structured logging"
Task T016: "Setup environment configuration"
Task T017: "Implement health check endpoints"
Task T019: "Create URL normalization utility"
Task T020: "Create product ID extraction utility"
```

---

## Parallel Example: User Story 1 Models

```bash
# Launch all US1 entity models together:
Task T021: "Create Client entity model"
Task T022: "Create APIKey entity model"
Task T023: "Create MonitoredWebsite entity model"
Task T024: "Create Product entity model"
Task T025: "Create CrawlExecutionLog entity model"
Task T026: "Create Pydantic request/response schemas"
```

---

## Implementation Strategy

### MVP First (User Story 1 Only)

1. Complete Phase 1: Setup (T001-T007)
2. Complete Phase 2: Foundational (T008-T020) - CRITICAL
3. Complete Phase 3: User Story 1 (T021-T043)
4. **STOP and VALIDATE**: Test website registration, product discovery, and approval flow independently
5. Deploy/demo if ready

**MVP Delivered**: Clients can register websites and start monitoring products

### Incremental Delivery

1. **Foundation** (Phases 1-2) → Infrastructure ready
2. **MVP** (Phase 3: US1) → Website registration and product discovery → Deploy/Demo
3. **Notifications** (Phase 4: US2) → Automated change detection and webhooks → Deploy/Demo
4. **Analytics** (Phase 5: US3) → Historical data queries for trend analysis → Deploy/Demo
5. **Self-Service** (Phase 6: US4) → API key management without admin intervention → Deploy/Demo
6. **Operations** (Phase 7: US5) → Crawl monitoring and health dashboards → Deploy/Demo
7. **Production** (Phases 8-9) → Data lifecycle and polish → Final production deployment

Each increment adds value without breaking previous functionality.

### Parallel Team Strategy

With multiple developers:

1. **Team together**: Complete Setup + Foundational (Phases 1-2)
2. **After Foundational complete**:
   - Developer A: User Story 1 (T021-T043)
   - Developer B: User Story 4 (T071-T082) - independent
3. **After US1 models complete** (T021-T025):
   - Developer A: Continue US1 services (T027-T043)
   - Developer B: Continue US4 (T071-T082)
   - Developer C: Start US5 (T083-T091) - depends on US1 models only
4. **After US1 complete**:
   - Developer A: User Story 2 (T044-T059)
5. **After US2 complete**:
   - Developer A: User Story 3 (T060-T070)

Stories integrate independently without blocking each other.

---

## Task Statistics

**Total Tasks**: 108
- **Phase 1 (Setup)**: 7 tasks
- **Phase 2 (Foundational)**: 13 tasks (BLOCKING)
- **Phase 3 (US1 - P1 MVP)**: 23 tasks
- **Phase 4 (US2 - P2)**: 16 tasks
- **Phase 5 (US3 - P3)**: 11 tasks
- **Phase 6 (US4 - P4)**: 12 tasks
- **Phase 7 (US5 - P5)**: 9 tasks
- **Phase 8 (Retention)**: 5 tasks
- **Phase 9 (Polish)**: 12 tasks

**Parallel Opportunities**: 45 tasks marked [P] for parallel execution
**Critical Path**: Setup → Foundational → US1 → US2 → US3 (minimum for full functionality)
**MVP Path**: Setup → Foundational → US1 only (23 tasks after foundation)

---

## Notes

- All tasks follow strict checklist format: `- [ ] [TaskID] [P?] [Story] Description with file path`
- [P] tasks target different files with no shared state dependencies
- [Story] labels map tasks to user stories from spec.md for traceability
- Each user story is independently completable and testable
- Tests are OPTIONAL per specification - not included in task list
- Commit after each task or logical group of parallel tasks
- Stop at any checkpoint to validate story independently
- Inngest handles background task orchestration and retry logic
- Neon PostgreSQL handles data storage, partitioning, and backups
- Follow quickstart.md for deployment validation

---

**Status**: ✅ Task list complete - Ready for implementation via `/speckit.implement`
