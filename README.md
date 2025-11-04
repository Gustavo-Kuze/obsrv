# Obsrv API - E-commerce Monitoring System

Simple REST API for monitoring competitor e-commerce websites and tracking price/stock changes.

## Quick Start (VPS Deployment)

### Prerequisites

1. **VPS Requirements**:
   - Ubuntu 22.04+ (or similar Linux distribution)
   - 1 CPU core, 4GB RAM, 50GB storage
   - Docker 24.0+ and Docker Compose 2.20+

2. **Managed Services** (Free Tiers Available):
   - [Neon PostgreSQL](https://neon.tech) - Database
   - [Inngest](https://inngest.com) - Background tasks

### Step 1: Install Docker

```bash
# Update system
sudo apt-get update

# Install Docker
curl -fsSL https://get.docker.com -o get-docker.sh
sudo sh get-docker.sh

# Add your user to docker group
sudo usermod -aG docker $USER

# Log out and back in, then verify
docker --version
docker compose version
```

### Step 2: Setup Managed Services

#### Neon PostgreSQL
1. Sign up at [neon.tech](https://neon.tech)
2. Create a new project
3. Copy your connection string from the dashboard
   - Format: `postgresql://username:password@hostname/database`

#### Inngest
1. Sign up at [inngest.com](https://inngest.com)
2. Create a new app named `obsrv-api`
3. Copy your API keys from Settings → API Keys:
   - Event Key
   - Signing Key

### Step 3: Clone and Configure

```bash
# Clone repository
git clone https://github.com/your-org/observer-microservices.git
cd observer-microservices

# Checkout feature branch
git checkout 001-obsrv-api-mvp

# Create environment file
cp .env.example .env

# Edit configuration
nano .env
```

**Required `.env` Configuration**:
```bash
# Database (from Neon)
DATABASE_URL=postgresql://your-neon-connection-string

# Inngest (from Inngest dashboard)
INNGEST_EVENT_KEY=your-event-key
INNGEST_SIGNING_KEY=your-signing-key
INNGEST_APP_ID=obsrv-api

# Security (generate a secure random string)
SECRET_KEY=$(openssl rand -hex 32)

# Environment
ENVIRONMENT=production
DEBUG=false
```

### Step 4: Initialize Database

```bash
# Run database migrations
docker compose -f docker-compose.prod.yml run --rm api alembic upgrade head
```

### Step 5: Start the Application

```bash
# Start services
docker compose -f docker-compose.prod.yml up -d

# Check status
docker compose -f docker-compose.prod.yml ps

# View logs
docker compose -f docker-compose.prod.yml logs -f
```

### Step 6: Verify Deployment

```bash
# Health check
curl http://localhost:8000/health

# Expected response:
# {"status":"healthy","timestamp":"..."}
```

## API Usage

### Create Your First API Key

Since this is a fresh deployment, you'll need to manually create your first client and API key in the database:

```bash
# Connect to your Neon database
psql "your-neon-connection-string"

# Create a client
INSERT INTO clients (id, name, email, webhook_secret_current)
VALUES (
    gen_random_uuid(),
    'My Company',
    'admin@mycompany.com',
    encode(gen_random_bytes(48), 'base64')
);

# Get the client_id
SELECT id, name FROM clients;

# Create an API key (replace <client-id> with actual UUID)
INSERT INTO api_keys (id, client_id, key_hash, key_prefix, permissions_scope)
VALUES (
    gen_random_uuid(),
    '<client-id>',
    crypt('obsrv_live_' || encode(gen_random_bytes(32), 'base64'), gen_salt('bf', 12)),
    'obsrv_li',
    '["read", "write", "admin"]'::jsonb
);

# Note: The actual key is: obsrv_live_<the-random-base64-string>
# You'll need to save it for API calls
```

**Better approach**: Create a setup script after Phase 2 is complete that handles initial client/key creation via API.

### Register a Website for Monitoring

```bash
# Register website
curl -X POST http://localhost:8000/v1/websites \
  -H "X-API-Key: your-api-key" \
  -H "Content-Type: application/json" \
  -d '{
    "base_url": "https://example-shop.com",
    "seed_urls": ["https://example-shop.com/products"],
    "crawl_frequency_minutes": 1440,
    "price_change_threshold_pct": 1.0,
    "webhook_endpoint_url": "https://your-server.com/webhook"
  }'
```

### Query Monitored Websites

```bash
# List all websites
curl http://localhost:8000/v1/websites \
  -H "X-API-Key: your-api-key"

# Get specific website
curl http://localhost:8000/v1/websites/<website-id> \
  -H "X-API-Key: your-api-key"
```

## Common Operations

### View Logs
```bash
docker compose -f docker-compose.prod.yml logs -f
```

### Restart Services
```bash
docker compose -f docker-compose.prod.yml restart
```

### Stop Services
```bash
docker compose -f docker-compose.prod.yml down
```

### Database Backup
```bash
# Neon handles automatic backups
# For manual backup:
pg_dump "$DATABASE_URL" | gzip > backup-$(date +%Y%m%d).sql.gz
```

### Update Application
```bash
git pull origin 001-obsrv-api-mvp
docker compose -f docker-compose.prod.yml down
docker compose -f docker-compose.prod.yml build
docker compose -f docker-compose.prod.yml up -d
```

## Development Setup

For local development:

```bash
# Copy environment
cp .env.example .env

# Edit with development settings
nano .env

# Start development server
docker compose up -d

# Run migrations
docker compose run --rm api alembic upgrade head

# View logs
docker compose logs -f

# API available at: http://localhost:8000
# API docs at: http://localhost:8000/docs
```

## Project Structure

```
observer-microservices/
├── backend/
│   ├── src/
│   │   ├── models/          # Data models
│   │   ├── services/        # Business logic
│   │   ├── api/             # API endpoints
│   │   └── core/            # Core utilities
│   ├── tests/               # Tests
│   └── alembic/             # Database migrations
├── specs/                   # Feature specifications
├── docker-compose.yml       # Development
├── docker-compose.prod.yml  # Production
├── Dockerfile               # Container definition
└── pyproject.toml           # Python dependencies
```

## Monitoring

### Health Checks
```bash
# Basic health
curl http://localhost:8000/health

# Detailed health (requires API key)
curl -H "X-API-Key: your-key" http://localhost:8000/v1/health/detailed
```

### Resource Usage
```bash
# Monitor Docker containers
docker stats

# Check disk usage
df -h
du -sh /var/lib/docker
```

### Inngest Dashboard
Monitor background tasks at: https://app.inngest.com

## Troubleshooting

### Container Won't Start
```bash
# Check logs
docker compose -f docker-compose.prod.yml logs api

# Verify environment variables
docker compose -f docker-compose.prod.yml config

# Restart fresh
docker compose -f docker-compose.prod.yml down -v
docker compose -f docker-compose.prod.yml up -d
```

### Database Connection Issues
```bash
# Test database connection
psql "$DATABASE_URL" -c "SELECT 1"

# Check Neon dashboard for status
# Visit: https://console.neon.tech
```

### API Not Responding
```bash
# Check if container is running
docker ps

# Check container health
docker inspect obsrv-api-prod | grep -A 10 Health

# Restart API
docker compose -f docker-compose.prod.yml restart api
```

## Security Notes

1. **API Keys**: Store securely, rotate every 90 days
2. **Database**: Use strong passwords, enable SSL in production
3. **Webhook Secrets**: Verify HMAC signatures on webhook receiver
4. **Firewall**: Only expose port 8000 (or 443 with reverse proxy)
5. **Updates**: Keep Docker and dependencies updated

## Production Recommendations

1. **Use a reverse proxy** (Nginx/Caddy) with SSL/TLS
2. **Setup automated backups** for database
3. **Configure log rotation** to prevent disk filling
4. **Monitor with external service** (UptimeRobot, Sentry)
5. **Setup alerts** for service failures and rate limits

## API Documentation

Interactive API documentation available at:
- Swagger UI: http://localhost:8000/docs
- ReDoc: http://localhost:8000/redoc

## Support

- **Documentation**: See `specs/001-obsrv-api-mvp/` for detailed specs
- **Issues**: Create GitHub issues for bugs
- **Deployment Guide**: See `specs/001-obsrv-api-mvp/quickstart.md` for comprehensive guide

## Current Status

⚠️ **MVP in Development**: Core infrastructure is fully implemented and ready for deployment! But the user stories are still in progress.

**Completed** (Ready to Deploy Now!):
- ✅ Project setup and Docker configuration
- ✅ Database schema and migrations (9 tables)
- ✅ Authentication middleware with rate limiting
- ✅ Structured logging and error handling
- ✅ FastAPI application with CORS and middleware
- ✅ Health check endpoints (basic, detailed, readiness, liveness)
- ✅ Inngest integration for background tasks
- ✅ URL normalization and product ID extraction
- ✅ Complete documentation and deployment scripts

**Next Steps** (User Story Implementation):
- ⏳ User Story 1: Website registration and monitoring (23 tasks)
- ⏳ User Story 2: Change detection and webhooks (16 tasks)
- ⏳ User Story 3: Historical data queries (11 tasks)
- ⏳ User Story 4: API key management (12 tasks)
- ⏳ User Story 5: Crawl health monitoring (9 tasks)
- ⏳ Data retention automation (5 tasks)
- ⏳ Production optimization (12 tasks)

**See PHASE2_COMPLETE.md for detailed status and next steps!**

## License

MIT License - See LICENSE file for details
