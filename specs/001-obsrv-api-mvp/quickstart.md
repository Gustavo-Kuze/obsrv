# Quickstart Guide: Obsrv API MVP

**Feature**: Obsrv API - E-commerce Monitoring System MVP
**Branch**: `001-obsrv-api-mvp`
**Date**: 2025-11-03

## Overview

This quickstart guide provides step-by-step instructions for deploying the Obsrv API MVP on a single VPS using Docker Compose. Total setup time: ~30 minutes.

## Prerequisites

### System Requirements

- **VPS Specifications**:
  - 1 CPU core
  - 4 GB RAM
  - 50 GB storage
  - Ubuntu 22.04 LTS or later (recommended)
  - Public IPv4 address

### Managed Services

- **Neon PostgreSQL**: Managed database (free tier: 512MB storage, 100 hours compute)
- **Inngest**: Serverless background processing (free tier: 50K function runs/month)

### Software Requirements

- Docker 24.0+ and Docker Compose 2.20+
- Git 2.30+
- Python 3.11+ (for development/testing)
- OpenSSL (for SSL certificate generation)

### Account Setup

- **Neon PostgreSQL Account**: [neon.tech](https://neon.tech) - Free tier available
- **Inngest Account**: [inngest.com](https://inngest.com) - Free tier available

### Network Requirements

- Ports to expose:
  - `80` - HTTP (redirects to HTTPS)
  - `443` - HTTPS (API endpoints)
- Firewall rules allowing outbound HTTPS (443) to target e-commerce websites and managed services
- Stable internet connection for web crawling

---

## Quick Start (Production)

### 1. Setup Managed Services Accounts

#### Neon PostgreSQL Setup
```bash
# Visit https://neon.tech and create account
# Create a new project with these settings:
# - Region: Choose closest to your VPS
# - Compute: Free tier (0.25 vCPU, 1GB RAM)
# - Storage: 512MB (expandable to 10GB free)

# After creation, get your connection string from Dashboard → Connection Details
# It will look like: postgresql://username:password@hostname/database
```

#### Inngest Setup
```bash
# Visit https://inngest.com and create account
# Create a new app:
# - Name: obsrv-api
# - Region: Choose closest to your VPS

# Get API keys from App Settings → API Keys:
# - Event Key: For webhook authentication
# - Signing Key: For function authentication
```

---

### 2. Install Docker and Docker Compose

```bash
# Update package index
sudo apt-get update

# Install prerequisites
sudo apt-get install -y \
    ca-certificates \
    curl \
    gnupg \
    lsb-release

# Add Docker GPG key
sudo mkdir -p /etc/apt/keyrings
curl -fsSL https://download.docker.com/linux/ubuntu/gpg | sudo gpg --dearmor -o /etc/apt/keyrings/docker.gpg

# Add Docker repository
echo \
  "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.gpg] https://download.docker.com/linux/ubuntu \
  $(lsb_release -cs) stable" | sudo tee /etc/apt/sources.list.d/docker.list > /dev/null

# Install Docker Engine and Docker Compose
sudo apt-get update
sudo apt-get install -y docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin

# Add current user to docker group
sudo usermod -aG docker $USER

# Log out and back in for group changes to take effect
```

Verify installation:
```bash
docker --version  # Should show 24.0+
docker compose version  # Should show 2.20+
```

---

### 2. Clone Repository and Setup Environment

```bash
# Clone repository
git clone https://github.com/your-org/obsrv-api.git
cd obsrv-api

# Checkout feature branch
git checkout 001-obsrv-api-mvp

# Copy environment template
cp .env.example .env

# Generate secure secrets
# Note: Neon and Inngest provide their own secure connection strings
# Only generate SECRET_KEY if not using auto-generated

# Edit .env with your production values
nano .env
```

---

### 3. Configure Environment Variables

Edit `.env` file with production values:

```bash
# Application
ENVIRONMENT=production
DEBUG=false
SECRET_KEY=<generate-32-char-secret>

# Server
HOST=0.0.0.0
PORT=8000

# Database (Neon PostgreSQL)
DATABASE_URL=<your-neon-connection-string>

# Inngest
INNGEST_EVENT_KEY=<your-inngest-event-key>
INNGEST_SIGNING_KEY=<your-inngest-signing-key>
INNGEST_APP_ID=obsrv-api

# Security
API_KEY_LENGTH=32

# CORS
CORS_ORIGINS=https://obsrv.example.com

# Crawling
DEFAULT_CRAWL_TIMEOUT=30
MAX_CONCURRENT_CRAWLS=5

# Webhooks
WEBHOOK_TIMEOUT=10
WEBHOOK_MAX_RETRIES=3
WEBHOOK_RETRY_BACKOFF=60

# Data Retention
DEFAULT_RETENTION_DAYS=90
MAX_RETENTION_DAYS=365

# Pagination
DEFAULT_PAGE_SIZE=50
MAX_PAGE_SIZE=500

# Logging
LOG_LEVEL=INFO
```

**Security Note**: Ensure all auto-generated passwords are strong (32+ characters, random alphanumeric + symbols).

---

### 4. Setup SSL Certificates (Production)

#### Option A: Let's Encrypt (Recommended)

```bash
# Install Certbot
sudo apt-get install -y certbot

# Generate certificate (HTTP-01 challenge)
sudo certbot certonly --standalone \
  -d api.obsrv.example.com \
  --email admin@obsrv.example.com \
  --agree-tos \
  --non-interactive

# Certificates will be at:
# /etc/letsencrypt/live/api.obsrv.example.com/fullchain.pem
# /etc/letsencrypt/live/api.obsrv.example.com/privkey.pem

# Setup auto-renewal
sudo systemctl enable certbot.timer
sudo systemctl start certbot.timer
```

#### Option B: Self-Signed Certificate (Development/Testing Only)

```bash
mkdir -p ./certs
openssl req -x509 -newkey rsa:4096 -nodes \
  -keyout ./certs/privkey.pem \
  -out ./certs/fullchain.pem \
  -days 365 \
  -subj "/CN=api.obsrv.localhost"
```

Update `docker-compose.prod.yml` to mount certificate paths:
```yaml
services:
  api:
    volumes:
      - /etc/letsencrypt/live/api.obsrv.example.com:/etc/letsencrypt/live/api.obsrv.example.com:ro
```

---

### 5. Initialize Database

```bash
# Run database migrations (connects to Neon PostgreSQL)
docker compose -f docker-compose.prod.yml run --rm api alembic upgrade head

# (Optional) Seed test data
docker compose -f docker-compose.prod.yml run --rm api python scripts/seed-dev-data.py
```

---

### 6. Start API Service

```bash
# Start the API service
docker compose -f docker-compose.prod.yml up -d

# Verify container is running
docker compose -f docker-compose.prod.yml ps

# Expected output:
# NAME            STATUS    PORTS
# obsrv-api-api   Up        0.0.0.0:8000->8000/tcp

# Check logs
docker compose -f docker-compose.prod.yml logs -f api
```

---

### 7. Verify Deployment

```bash
# Health check
curl https://api.obsrv.example.com/v1/health

# Expected response:
# {
#   "status": "healthy",
#   "timestamp": "2025-11-03T10:00:00Z"
# }

# Detailed health check (requires API key)
curl -H "X-API-Key: <your-api-key>" https://api.obsrv.example.com/v1/health/detailed
```

---

### 8. Create First Client and API Key

```bash
# Use the API to create your first client and API key
curl -X POST https://api.obsrv.example.com/v1/auth/keys \
  -H "Content-Type: application/json" \
  -d '{
    "description": "Initial admin API key",
    "permissions_scope": ["read", "write", "admin"]
  }'

# Response will include:
# {
#   "api_key": "obsrv_live_a1b2c3d4e5f6g7h8i9j0k1l2m3n4o5p6q7r8",
#   "key_id": "<uuid>",
#   "created_at": "2025-11-03T...",
#   "permissions_scope": ["read", "write", "admin"]
# }

# Save the API key - it will not be shown again!
```

---

### 9. Register First Website

```bash
# Register website with seed URLs
curl -X POST https://api.obsrv.example.com/v1/websites \
  -H "X-API-Key: obsrv_live_a1b2c3d4..." \
  -H "Content-Type: application/json" \
  -d '{
    "base_url": "https://example-shop.com",
    "seed_urls": [
      "https://example-shop.com/category/electronics"
    ],
    "crawl_frequency_minutes": 1440,
    "price_change_threshold_pct": 1.0,
    "webhook_endpoint_url": "https://your-erp.example.com/webhooks/obsrv"
  }'

# Response:
# {
#   "website_id": "<uuid>",
#   "status": "pending_approval",
#   "message": "Website registered, product discovery in progress",
#   "discovery_job_id": "<uuid>"
# }
```

---

### 10. Monitor Background Processing

Access Inngest dashboard for real-time function monitoring:

```bash
# Open in browser: https://app.inngest.com
# Navigate to your obsrv-api app
```

**Dashboard Features**:
- Function execution status and history
- Step-by-step execution tracing
- Retry and failure analysis
- Performance metrics and logs
- Real-time event streaming

---

## Development Setup

### 1. Local Development with Docker Compose

```bash
# Clone repository
git clone https://github.com/your-org/obsrv-api.git
cd obsrv-api
git checkout 001-obsrv-api-mvp

# Copy development environment
cp .env.example .env

# Edit .env with your Neon and Inngest credentials
nano .env

# Start development API
docker compose -f docker-compose.yml up -d

# Run migrations (connects to Neon)
docker compose -f docker-compose.yml run --rm api alembic upgrade head

# Access service
# API: http://localhost:8000
# Inngest Dashboard: https://app.inngest.com
```

### 2. Local Development without Docker (Python Virtual Environment)

```bash
# Create virtual environment
python3.11 -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate

# Install dependencies
pip install -e .

# Install crawl4ai separately (large dependencies)
pip install crawl4ai[all]

# Set environment variables (use your Neon and Inngest credentials)
export DATABASE_URL="your-neon-connection-string"
export INNGEST_EVENT_KEY="your-event-key"
export INNGEST_SIGNING_KEY="your-signing-key"
export INNGEST_APP_ID="obsrv-api"

# Run migrations
alembic upgrade head

# Start API server
uvicorn src.api.main:create_application --reload --host 0.0.0.0 --port 8000 --factory
```

### 3. Running Tests

```bash
# Run all tests
pytest

# Run with coverage
pytest --cov=src --cov-report=html --cov-report=term

# Run specific test categories
pytest tests/unit/              # Unit tests only
pytest tests/integration/       # Integration tests
pytest tests/contract/          # API contract validation

# Run tests in Docker
docker compose -f docker-compose.dev.yml run --rm api pytest
```

---

## Common Operations

### View Logs

```bash
# API service logs
docker compose -f docker-compose.prod.yml logs -f

# Specific service
docker compose -f docker-compose.prod.yml logs -f api

# Last 100 lines
docker compose -f docker-compose.prod.yml logs --tail=100 api
```

### Restart Services

```bash
# Restart API service
docker compose -f docker-compose.prod.yml restart
```

### Database Backup

Neon PostgreSQL provides automatic backups. For manual backups:

```bash
# Backup database (connect directly to Neon)
pg_dump "$DATABASE_URL" | gzip > backup-$(date +%Y%m%d-%H%M%S).sql.gz

# Restore database
gunzip < backup-20251103-120000.sql.gz | psql "$DATABASE_URL"
```

**Note**: Neon handles automated backups, point-in-time recovery, and high availability. Manual backups are primarily for development/testing.

### Manual Crawl Trigger

```bash
# Trigger immediate crawl for website
curl -X POST https://api.obsrv.example.com/v1/websites/<website-id>/crawl \
  -H "X-API-Key: <your-api-key>"
```

---

## Monitoring and Maintenance

### Health Checks

```bash
# Simple health check
curl https://api.obsrv.example.com/health

# Detailed health (includes database, Inngest connectivity)
curl -H "X-API-Key: <your-api-key>" https://api.obsrv.example.com/v1/health/detailed
```

### Resource Monitoring

```bash
# Docker stats
docker stats

# Specific container
docker stats obsrv-api-api

# Disk usage
docker system df
df -h
```

### Log Rotation

Add to `/etc/logrotate.d/docker-containers`:

```bash
/var/lib/docker/containers/*/*.log {
  rotate 7
  daily
  compress
  missingok
  delaycompress
  copytruncate
  maxsize 100M
}
```

### Database Maintenance

Neon PostgreSQL handles most maintenance automatically. For manual operations:

```bash
# Run VACUUM ANALYZE (Neon optimizes this automatically)
psql "$DATABASE_URL" -c "VACUUM ANALYZE;"

# Check table sizes
psql "$DATABASE_URL" -c "
  SELECT
    schemaname,
    tablename,
    pg_size_pretty(pg_total_relation_size(schemaname||'.'||tablename)) AS size
  FROM pg_tables
  WHERE schemaname = 'public'
  ORDER BY pg_total_relation_size(schemaname||'.'||tablename) DESC;
"
```

**Note**: Neon provides automated vacuuming, partitioning, and performance optimization.

---

## Troubleshooting

### API Not Responding

```bash
# Check if container is running
docker compose -f docker-compose.prod.yml ps api

# Check logs for errors
docker compose -f docker-compose.prod.yml logs api --tail=100

# Restart API
docker compose -f docker-compose.prod.yml restart api
```

### Crawls Not Executing

```bash
# Check Inngest function status
# Visit: https://app.inngest.com/apps/obsrv-api/functions

# Check recent function runs and failures
# Look for crawl-related functions in the dashboard

# Verify Inngest connectivity
curl -H "X-API-Key: <your-api-key>" https://api.obsrv.example.com/v1/health/detailed

# Check API logs for Inngest webhook errors
docker compose -f docker-compose.prod.yml logs api --tail=100
```

### Database Connection Issues

```bash
# Test Neon database connectivity
psql "$DATABASE_URL" -c "SELECT 1;"

# Check Neon dashboard for connection issues
# Visit: https://console.neon.tech

# Verify connection from API container
docker compose -f docker-compose.prod.yml exec api python -c "
import os
from sqlalchemy import create_engine
engine = create_engine(os.getenv('DATABASE_URL'))
with engine.connect() as conn:
    result = conn.execute('SELECT 1')
    print('Database connection successful')
"

### Webhook Delivery Failures

```bash
# Check webhook logs (via API or direct database connection)
psql "$DATABASE_URL" -c "
  SELECT
    target_url,
    status,
    http_status_code,
    error_message,
    delivery_timestamp
  FROM webhook_delivery_logs
  WHERE status != 'success'
  ORDER BY delivery_timestamp DESC
  LIMIT 20;
"

# Retry failed webhooks
curl -X POST https://api.obsrv.example.com/v1/webhooks/<webhook-id>/retry \
  -H "X-API-Key: <your-api-key>"
```

---

## Security Best Practices

1. **API Keys**:
   - Generate unique API keys per client/integration
   - Rotate keys every 90 days
   - Never log API keys
   - Store keys in secure vault (e.g., HashiCorp Vault, AWS Secrets Manager)

2. **Webhook Secrets**:
   - Rotate webhook secrets regularly (90 days)
   - Always verify HMAC signatures on webhook receiver side
   - Use 1-hour grace period for zero-downtime rotation

3. **Database**:
   - Use strong passwords (32+ characters)
   - Enable SSL connections for remote access
   - Regular backups with encryption
   - Restrict network access (firewall rules)

4. **Network**:
   - Use HTTPS only (TLS 1.2+)
   - Configure firewall to allow only necessary ports
   - Rate limit API endpoints (use nginx rate limiting)
   - Block suspicious IPs using fail2ban

5. **Updates**:
   - Keep Docker and Docker Compose updated
   - Regularly update base images
   - Monitor security advisories for dependencies
   - Apply OS security patches monthly

---

## Performance Tuning

### API Server

```yaml
# docker-compose.prod.yml
services:
  api:
    environment:
      # Uvicorn configuration
      UVICORN_WORKERS: 4  # Increase for more concurrent requests (2 × CPU cores)
      UVICORN_TIMEOUT_KEEP_ALIVE: 65
```

### Inngest Functions

Inngest automatically scales based on load. Monitor performance in the Inngest dashboard:

```bash
# Visit: https://app.inngest.com/apps/obsrv-api/functions
# Monitor function duration, success rates, and resource usage
```

### Neon PostgreSQL

Neon provides automatic performance optimization. Monitor via:

```bash
# Neon Console: https://console.neon.tech
# Check query performance and connection pooling
# Scale compute resources as needed (0.25-4 vCPUs available)
```

---

## Next Steps

1. **Setup Monitoring**: Integrate with Sentry for error tracking
2. **Configure Alerts**: Setup alerts for high failure rates, disk usage
3. **Backup Automation**: Implement automated daily backups
4. **Load Testing**: Run load tests to validate performance targets
5. **Documentation**: Share API documentation with clients (OpenAPI spec)

---

## Support

- **Documentation**: https://docs.obsrv.example.com
- **API Reference**: https://api.obsrv.example.com/docs (OpenAPI/Swagger UI)
- **Support Email**: support@obsrv.example.com
- **Status Page**: https://status.obsrv.example.com

---

**Status**: ✅ Quickstart guide complete - Ready for deployment
