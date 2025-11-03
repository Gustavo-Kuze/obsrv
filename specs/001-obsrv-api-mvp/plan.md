# Implementation Plan: Obsrv API - E-commerce Monitoring System MVP

**Branch**: `001-obsrv-api-mvp` | **Date**: 2025-11-02 | **Spec**: [spec.md](./spec.md)
**Input**: Feature specification from `/specs/001-obsrv-api-mvp/spec.md`

**Note**: This template is filled in by the `/speckit.plan` command. See `.specify/templates/commands/plan.md` for the execution workflow.

## Summary

The Obsrv API is a low-cost e-commerce monitoring system that tracks competitor product prices and stock status across multiple websites. The system performs daily automated crawls, detects changes, and sends webhook notifications to client ERP systems. Built as a monolithic application deployed on a single VPS using Docker Compose, it supports up to 20 monitored websites with 100 products each. Key capabilities include: hybrid product discovery from seed URLs, configurable price change thresholds (1% default), HMAC-authenticated webhooks, 90-day historical data retention, and API key-based authentication.

## Technical Context

**Language/Version**: Python 3.11+
**Primary Dependencies**: FastAPI (REST API), Celery (task queue), crawl4ai (web crawling), Redis (task broker/cache), PostgreSQL (primary storage), Docker Compose (orchestration)
**Storage**: PostgreSQL with JSONB for flexible crawl data, Redis for task queue and caching
**Testing**: pytest with pytest-asyncio, httpx for API testing, pytest-celery for task testing
**Target Platform**: Linux VPS (single server, Docker Compose deployment)
**Project Type**: Web/API backend (monolithic architecture)
**Performance Goals**: 95% crawl success rate, <2s API response for 90-day historical queries, process 100 products across 20 websites within 30 minutes
**Constraints**: Single VPS (4 CPU, 8GB RAM, 100GB storage), <10 minute webhook delivery latency, 99% API uptime, daily crawl frequency baseline (2-4x per day configurable)
**Scale/Scope**: MVP supporting 10-20 monitored websites, 100 products per website, 90-day retention (360MB estimated storage), 35 functional requirements, 5 prioritized user stories

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

**Status**: Constitution file contains template placeholders only. No project-specific principles defined yet. Proceeding with best practices for Python API development:

- ✅ **Clear separation of concerns**: API layer (FastAPI), business logic (services), data access (repositories), background tasks (Celery)
- ✅ **Testability**: pytest with clear unit/integration/contract test boundaries
- ✅ **Observability**: Structured logging with correlation IDs, health check endpoints
- ✅ **Security**: API key authentication, HMAC webhook signatures, hashed credentials
- ✅ **Simplicity**: Monolithic MVP architecture, avoid premature optimization
- ⚠️ **Documentation**: OpenAPI schema auto-generation, deployment quickstart required

**Recommendation**: After MVP validation, codify successful patterns into project constitution.

## Project Structure

### Documentation (this feature)

```text
specs/[###-feature]/
├── plan.md              # This file (/speckit.plan command output)
├── research.md          # Phase 0 output (/speckit.plan command)
├── data-model.md        # Phase 1 output (/speckit.plan command)
├── quickstart.md        # Phase 1 output (/speckit.plan command)
├── contracts/           # Phase 1 output (/speckit.plan command)
└── tasks.md             # Phase 2 output (/speckit.tasks command - NOT created by /speckit.plan)
```

### Source Code (repository root)

```text
src/
├── api/                    # FastAPI application
│   ├── routes/            # REST endpoints
│   │   ├── websites.py    # Website registration & management
│   │   ├── products.py    # Product queries & history
│   │   ├── auth.py        # API key management
│   │   └── health.py      # Health check endpoints
│   ├── dependencies.py    # DI (database, auth)
│   ├── middleware.py      # Request logging, CORS, auth
│   └── main.py           # FastAPI app initialization
│
├── models/                # SQLAlchemy ORM models
│   ├── client.py         # Client account
│   ├── website.py        # Monitored website
│   ├── product.py        # Product & product history
│   ├── crawl_log.py      # Crawl execution log
│   ├── webhook_log.py    # Webhook delivery log
│   └── api_key.py        # API key authentication
│
├── services/              # Business logic layer
│   ├── website_service.py      # Website registration, product discovery
│   ├── crawl_service.py        # Crawl orchestration & execution
│   ├── product_service.py      # Product identification, change detection
│   ├── notification_service.py # Webhook delivery with HMAC
│   ├── auth_service.py         # API key generation, validation
│   └── history_service.py      # Historical data queries, retention
│
├── tasks/                 # Celery background tasks
│   ├── crawl_tasks.py    # Scheduled/on-demand crawls
│   ├── discovery_tasks.py # Product discovery from seed URLs
│   ├── notification_tasks.py # Webhook delivery with retries
│   └── maintenance_tasks.py  # Data retention, cleanup
│
├── crawlers/              # Web crawling logic
│   ├── base_crawler.py   # Abstract crawler with crawl4ai
│   ├── product_extractor.py # URL normalization, SKU extraction
│   ├── discovery_crawler.py  # Seed URL → product list
│   └── platform_adapters/    # E-commerce platform specific logic
│       └── generic.py    # Generic HTML extraction (MVP)
│
├── schemas/               # Pydantic models (API contracts)
│   ├── website.py        # Website registration, configuration
│   ├── product.py        # Product data, history queries
│   ├── webhook.py        # Webhook payload format
│   └── auth.py           # API key schemas
│
├── repositories/          # Data access layer
│   ├── website_repo.py
│   ├── product_repo.py
│   ├── crawl_log_repo.py
│   └── webhook_log_repo.py
│
├── utils/                 # Shared utilities
│   ├── url_normalizer.py # URL cleaning, product ID extraction
│   ├── hmac_signer.py    # Webhook signature generation/verification
│   ├── logger.py         # Structured logging setup
│   └── config.py         # Environment configuration
│
└── db/                    # Database setup
    ├── session.py        # SQLAlchemy session management
    ├── migrations/       # Alembic migrations
    └── seed.py           # Development seed data

tests/
├── contract/             # OpenAPI contract validation
│   └── test_api_contracts.py
├── integration/          # Multi-component tests
│   ├── test_crawl_flow.py       # Registration → discovery → crawl
│   ├── test_notification_flow.py # Change → webhook delivery
│   └── test_auth_flow.py         # API key lifecycle
└── unit/                 # Isolated component tests
    ├── services/
    ├── crawlers/
    ├── repositories/
    └── utils/

docker-compose.yml        # Orchestration: API, Celery, PostgreSQL, Redis
Dockerfile               # Application container image
alembic.ini              # Database migration config
pyproject.toml           # Python dependencies (Poetry)
pytest.ini               # Test configuration
.env.example             # Environment variables template
```

**Structure Decision**: Monolithic web API backend using layered architecture. Clear separation between API layer (FastAPI routes), business logic (services), data access (repositories), and background processing (Celery tasks). Crawling logic isolated in dedicated module with platform adapters for extensibility. This structure supports the MVP scope while enabling future modularization if needed.

## Complexity Tracking

> **Fill ONLY if Constitution Check has violations that must be justified**

No violations identified. Architecture follows established FastAPI/Celery patterns appropriate for the problem domain.
