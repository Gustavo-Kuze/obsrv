#!/bin/bash
# Setup script for VPS deployment of Obsrv API

set -e

echo "======================================"
echo "Obsrv API - VPS Setup Script"
echo "======================================"
echo ""

# Check if running as root
if [ "$EUID" -eq 0 ]; then
  echo "Please do not run this script as root"
  exit 1
fi

# Check for required commands
command -v docker >/dev/null 2>&1 || {
  echo "Error: Docker is not installed. Please install Docker first."
  echo "Run: curl -fsSL https://get.docker.com | sh"
  exit 1
}

command -v docker compose >/dev/null 2>&1 || {
  echo "Error: Docker Compose is not installed."
  exit 1
}

echo "✓ Docker and Docker Compose are installed"
echo ""

# Check for .env file
if [ ! -f .env ]; then
  echo "Creating .env file from template..."
  cp .env.example .env
  echo "⚠️  Please edit .env file with your configuration:"
  echo "   - DATABASE_URL (from Neon)"
  echo "   - INNGEST_EVENT_KEY (from Inngest)"
  echo "   - INNGEST_SIGNING_KEY (from Inngest)"
  echo "   - SECRET_KEY (generate with: openssl rand -hex 32)"
  echo ""
  read -p "Press Enter after editing .env file..."
fi

# Validate required environment variables
echo "Validating configuration..."
source .env

if [ -z "$DATABASE_URL" ]; then
  echo "Error: DATABASE_URL is not set in .env"
  exit 1
fi

if [ -z "$INNGEST_EVENT_KEY" ]; then
  echo "Error: INNGEST_EVENT_KEY is not set in .env"
  exit 1
fi

if [ -z "$INNGEST_SIGNING_KEY" ]; then
  echo "Error: INNGEST_SIGNING_KEY is not set in .env"
  exit 1
fi

if [ -z "$SECRET_KEY" ] || [ "$SECRET_KEY" = "your-secret-key-here-min-32-chars-random" ]; then
  echo "Generating SECRET_KEY..."
  SECRET_KEY=$(openssl rand -hex 32)
  sed -i "s/SECRET_KEY=.*/SECRET_KEY=$SECRET_KEY/" .env
  echo "✓ SECRET_KEY generated"
fi

echo "✓ Configuration validated"
echo ""

# Build Docker image
echo "Building Docker image..."
docker compose -f docker-compose.prod.yml build
echo "✓ Docker image built"
echo ""

# Run database migrations
echo "Running database migrations..."
docker compose -f docker-compose.prod.yml run --rm api alembic upgrade head
echo "✓ Database migrations complete"
echo ""

# Start services
echo "Starting services..."
docker compose -f docker-compose.prod.yml up -d
echo "✓ Services started"
echo ""

# Wait for health check
echo "Waiting for API to be healthy..."
sleep 10

for i in {1..30}; do
  if curl -sf http://localhost:8000/health > /dev/null; then
    echo "✓ API is healthy"
    break
  fi
  if [ $i -eq 30 ]; then
    echo "⚠️  API health check timed out"
    echo "Check logs with: docker compose -f docker-compose.prod.yml logs"
    exit 1
  fi
  sleep 2
done

echo ""
echo "======================================"
echo "Setup Complete!"
echo "======================================"
echo ""
echo "API is running at: http://localhost:8000"
echo "API docs at: http://localhost:8000/docs"
echo ""
echo "Next steps:"
echo "1. Create your first client and API key (see README.md)"
echo "2. Test the API with curl or Postman"
echo "3. Configure Inngest webhooks to point to your VPS"
echo ""
echo "Useful commands:"
echo "  - View logs: docker compose -f docker-compose.prod.yml logs -f"
echo "  - Restart: docker compose -f docker-compose.prod.yml restart"
echo "  - Stop: docker compose -f docker-compose.prod.yml down"
echo ""
