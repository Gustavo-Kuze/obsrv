# Quick Deployment Reference

## One-Command Setup (Linux VPS)

```bash
# Make script executable and run
chmod +x setup-vps.sh
./setup-vps.sh
```

## Manual Setup Steps

### 1. Install Docker
```bash
curl -fsSL https://get.docker.com | sh
sudo usermod -aG docker $USER
# Log out and back in
```

### 2. Configure Environment
```bash
cp .env.example .env
nano .env  # Edit with your values
```

**Required values**:
- `DATABASE_URL` - From Neon dashboard
- `INNGEST_EVENT_KEY` - From Inngest dashboard
- `INNGEST_SIGNING_KEY` - From Inngest dashboard
- `SECRET_KEY` - Generate with: `openssl rand -hex 32`

### 3. Deploy
```bash
# Build and start
docker compose -f docker-compose.prod.yml up -d

# Run migrations
docker compose -f docker-compose.prod.yml run --rm api alembic upgrade head

# Check health
curl http://localhost:8000/health
```

## Common Commands

### Service Management
```bash
# View logs
docker compose -f docker-compose.prod.yml logs -f

# Restart
docker compose -f docker-compose.prod.yml restart

# Stop
docker compose -f docker-compose.prod.yml down

# Rebuild after code changes
docker compose -f docker-compose.prod.yml build
docker compose -f docker-compose.prod.yml up -d
```

### Database Operations
```bash
# Run migrations
docker compose -f docker-compose.prod.yml run --rm api alembic upgrade head

# Connect to database
psql "$DATABASE_URL"

# Backup
pg_dump "$DATABASE_URL" | gzip > backup-$(date +%Y%m%d).sql.gz

# Restore
gunzip < backup.sql.gz | psql "$DATABASE_URL"
```

### API Operations
```bash
# Health check
curl http://localhost:8000/health

# List websites (requires API key)
curl -H "X-API-Key: your-key" http://localhost:8000/v1/websites

# View API docs
# Open: http://your-server:8000/docs
```

## Initial Setup - Creating First API Key

Since the API requires authentication, you'll need to create your first client and API key manually:

```sql
-- Connect to database
psql "$DATABASE_URL"

-- Create client
INSERT INTO clients (name, email, webhook_secret_current)
VALUES ('My Company', 'admin@example.com', encode(gen_random_bytes(48), 'base64'));

-- Get client ID
SELECT id FROM clients WHERE email = 'admin@example.com';

-- Create API key (save this key!)
WITH new_key AS (
  SELECT 'obsrv_live_' || encode(gen_random_bytes(32), 'base64') AS key_value
)
INSERT INTO api_keys (client_id, key_hash, key_prefix, permissions_scope)
SELECT
  (SELECT id FROM clients WHERE email = 'admin@example.com'),
  crypt(key_value, gen_salt('bf', 12)),
  substring(key_value, 1, 8),
  '["read", "write", "admin"]'::jsonb
FROM new_key
RETURNING 'Your API Key: ' || (SELECT key_value FROM new_key);
```

## Troubleshooting

### Container won't start
```bash
# Check logs
docker compose -f docker-compose.prod.yml logs api

# Remove and recreate
docker compose -f docker-compose.prod.yml down -v
docker compose -f docker-compose.prod.yml up -d
```

### Database connection error
```bash
# Test connection
psql "$DATABASE_URL" -c "SELECT 1"

# Check Neon status
# Visit: https://console.neon.tech
```

### API returns 401 Unauthorized
- Verify API key is correct
- Check key hasn't been invalidated
- Ensure key has correct permissions

## Port Forwarding (Optional)

If running behind NAT/firewall:

```bash
# Allow traffic on port 8000
sudo ufw allow 8000/tcp

# Or setup Nginx reverse proxy
sudo apt install nginx
# Configure Nginx to proxy to localhost:8000
```

## Production Checklist

- [ ] Set `ENVIRONMENT=production` in .env
- [ ] Set `DEBUG=false` in .env
- [ ] Use strong `SECRET_KEY` (32+ chars)
- [ ] Configure firewall (only expose necessary ports)
- [ ] Setup SSL/TLS (use Caddy or Certbot)
- [ ] Configure log rotation
- [ ] Setup monitoring (UptimeRobot, Sentry)
- [ ] Configure automated backups
- [ ] Test webhook delivery
- [ ] Document API keys and secrets

## Monitoring

### Resource Usage
```bash
# Docker stats
docker stats obsrv-api-prod

# Disk usage
df -h
du -sh /var/lib/docker
```

### Logs
```bash
# Tail logs
docker compose -f docker-compose.prod.yml logs -f api

# Last 100 lines
docker compose -f docker-compose.prod.yml logs --tail 100 api

# Export logs
docker compose -f docker-compose.prod.yml logs --no-color > app.log
```

### Inngest Dashboard
Monitor background tasks: https://app.inngest.com

## Updating

```bash
# Pull latest code
git pull origin 001-obsrv-api-mvp

# Rebuild and deploy
docker compose -f docker-compose.prod.yml down
docker compose -f docker-compose.prod.yml build
docker compose -f docker-compose.prod.yml run --rm api alembic upgrade head
docker compose -f docker-compose.prod.yml up -d
```

## Support

- **Issues**: https://github.com/your-org/observer-microservices/issues
- **Docs**: See `specs/001-obsrv-api-mvp/` directory
- **Health**: http://your-server:8000/health
