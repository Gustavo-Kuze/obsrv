#!/bin/bash
# Helper script to create first API key

set -e

echo "======================================"
echo "Create First API Key"
echo "======================================"
echo ""

# Check for DATABASE_URL
if [ -z "$DATABASE_URL" ]; then
  if [ -f .env ]; then
    source .env
  fi
fi

if [ -z "$DATABASE_URL" ]; then
  echo "Error: DATABASE_URL not set"
  echo "Please set DATABASE_URL environment variable or create .env file"
  exit 1
fi

# Get client details
read -p "Client name: " CLIENT_NAME
read -p "Client email: " CLIENT_EMAIL

echo ""
echo "Creating client and API key..."

# Generate API key and store in database
API_KEY=$(openssl rand -base64 32 | tr -d '=' | tr '+/' '-_')
FULL_KEY="obsrv_live_${API_KEY}"

# Create client and API key in database
psql "$DATABASE_URL" <<EOF
-- Create client
INSERT INTO clients (name, email, webhook_secret_current)
VALUES ('${CLIENT_NAME}', '${CLIENT_EMAIL}', encode(gen_random_bytes(48), 'base64'))
ON CONFLICT (email) DO NOTHING;

-- Create API key
WITH client_info AS (
  SELECT id FROM clients WHERE email = '${CLIENT_EMAIL}'
)
INSERT INTO api_keys (client_id, key_hash, key_prefix, permissions_scope)
SELECT
  id,
  crypt('${FULL_KEY}', gen_salt('bf', 12)),
  substring('${FULL_KEY}', 1, 8),
  '["read", "write", "admin"]'::jsonb
FROM client_info;

-- Show success
SELECT 'Client created successfully' AS status;
EOF

echo ""
echo "======================================"
echo "✓ Success!"
echo "======================================"
echo ""
echo "Your API Key:"
echo "$FULL_KEY"
echo ""
echo "⚠️  IMPORTANT: Save this key now!"
echo "   It will not be shown again."
echo ""
echo "Test your API key:"
echo "curl -H \"X-API-Key: $FULL_KEY\" http://localhost:8000/health"
echo ""
