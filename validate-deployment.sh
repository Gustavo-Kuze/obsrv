#!/bin/bash
# Validation script to verify deployment is working correctly

set -e

echo "======================================"
echo "Obsrv API - Deployment Validation"
echo "======================================"
echo ""

API_URL="${1:-http://localhost:8000}"
FAILED=0

# Colors
GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

check_endpoint() {
    local name=$1
    local endpoint=$2
    local expected_status=${3:-200}
    local auth_header=$4

    echo -n "Testing ${name}... "

    if [ -n "$auth_header" ]; then
        response=$(curl -s -w "\n%{http_code}" -H "X-API-Key: $auth_header" "${API_URL}${endpoint}")
    else
        response=$(curl -s -w "\n%{http_code}" "${API_URL}${endpoint}")
    fi

    status_code=$(echo "$response" | tail -n1)
    body=$(echo "$response" | head -n-1)

    if [ "$status_code" -eq "$expected_status" ]; then
        echo -e "${GREEN}✓ PASS${NC} (HTTP $status_code)"
        if [ -n "$body" ]; then
            echo "  Response: $(echo "$body" | head -c 100)"
        fi
    else
        echo -e "${RED}✗ FAIL${NC} (HTTP $status_code, expected $expected_status)"
        FAILED=$((FAILED + 1))
        if [ -n "$body" ]; then
            echo "  Response: $body"
        fi
    fi
}

echo "Target: $API_URL"
echo ""

# Check if API is accessible
echo -n "Checking API accessibility... "
if curl -s --connect-timeout 5 "${API_URL}/health" > /dev/null 2>&1; then
    echo -e "${GREEN}✓ API is accessible${NC}"
else
    echo -e "${RED}✗ API is not accessible${NC}"
    echo ""
    echo "Please check:"
    echo "  1. Is the API running? docker compose ps"
    echo "  2. Is the port correct? Default is 8000"
    echo "  3. Check logs: docker compose logs api"
    exit 1
fi

echo ""
echo "Running endpoint tests..."
echo ""

# Test public endpoints
check_endpoint "Root endpoint" "/"
check_endpoint "Basic health check" "/health"
check_endpoint "Liveness probe" "/v1/health/live"
check_endpoint "Readiness probe" "/v1/health/ready"

# Test authentication
echo ""
echo "Testing authentication..."
check_endpoint "Protected endpoint (no auth)" "/v1/health/detailed" 401

# If API key provided, test with auth
if [ -n "$API_KEY" ]; then
    echo ""
    echo "Testing with API key..."
    check_endpoint "Protected endpoint (with auth)" "/v1/health/detailed" 200 "$API_KEY"
else
    echo ""
    echo -e "${YELLOW}⚠ No API key provided${NC}"
    echo "  To test authenticated endpoints:"
    echo "  API_KEY=your-key ./validate-deployment.sh"
fi

# Test documentation (if DEBUG mode)
echo ""
echo "Checking documentation..."
check_endpoint "OpenAPI docs" "/docs" 200 || echo "  (Disabled in production mode)"

# Summary
echo ""
echo "======================================"
if [ $FAILED -eq 0 ]; then
    echo -e "${GREEN}✓ All tests passed!${NC}"
    echo "======================================"
    echo ""
    echo "Your Obsrv API is working correctly!"
    echo ""
    echo "Next steps:"
    echo "  1. Create your first API key (if not done yet)"
    echo "     ./create-first-apikey.sh"
    echo ""
    echo "  2. Test with authenticated requests"
    echo "     curl -H \"X-API-Key: your-key\" ${API_URL}/v1/health/detailed"
    echo ""
    echo "  3. View API documentation"
    echo "     ${API_URL}/docs (if DEBUG=true)"
    echo ""
    echo "  4. Start implementing user stories!"
    echo "     See specs/001-obsrv-api-mvp/tasks.md"
    echo ""
else
    echo -e "${RED}✗ ${FAILED} test(s) failed${NC}"
    echo "======================================"
    echo ""
    echo "Troubleshooting:"
    echo "  1. Check logs: docker compose logs api"
    echo "  2. Verify environment: docker compose config"
    echo "  3. Check database: psql \"\$DATABASE_URL\" -c \"SELECT 1\""
    echo "  4. Restart services: docker compose restart"
    echo ""
    exit 1
fi
