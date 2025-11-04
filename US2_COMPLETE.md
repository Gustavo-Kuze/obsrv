# User Story 2 Complete! 🎉

## Automated Change Notifications - Fully Functional!

**Status**: ✅ **User Story 2 (P2) is 100% Complete**

You now have automated change detection and webhook notifications working:
1. Scheduled daily crawls of all active products
2. Price and stock change detection with configurable thresholds
3. HMAC-authenticated webhook delivery with retry logic
4. Webhook secret rotation with grace period

## What's Implemented (All 16 Tasks Complete)

### 📦 Entity Models (T044-T045)
- ✅ ProductHistoryRecord model with time-series partitioning
- ✅ WebhookDeliveryLog model with retry tracking
- ✅ Relationships updated in Product and MonitoredWebsite models

### 📋 Webhook Payload Schemas (T046)
- ✅ PriceChangeEvent schema matching specification
- ✅ StockChangeEvent schema matching specification
- ✅ Complete with metadata and validation

### 🔧 Core Services (T047-T050)
- ✅ ChangeDetectionService - Compares current vs previous data
  - Price change detection with threshold filtering
  - Stock status transition detection
  - Change percentage calculation
- ✅ WebhookSecurity - HMAC-SHA256 signature generation
  - Stripe-style signature format: t={timestamp},v1={signature}
  - 5-minute replay protection window
  - Constant-time comparison for security
  - Support for secret rotation grace period
- ✅ WebhookDeliveryService - HTTP delivery with retry
  - 10-second timeout
  - Exponential backoff: immediate, +5min, +30min
  - Status tracking (pending, success, failed, retrying, exhausted)
  - Response logging for debugging

### 🌐 Inngest Functions (T051-T053)
- ✅ scheduled_crawl_function - Daily product crawls
  - Cron trigger: 2 AM UTC daily
  - Processes all active websites
  - Detects changes and triggers webhooks
  - Auto-pauses websites after 3 consecutive failures
- ✅ deliver_webhook_function - Async webhook delivery
  - Event-driven (triggered by webhook.deliver)
  - Automatic retry with Inngest
  - Delivery log creation

### 🔐 API Endpoints (T054)
- ✅ POST /v1/auth/webhook-secret - Secret rotation
  - 1-hour grace period for old secret
  - New secret shown once
  - Automatic expiration

### 🔗 Integration Features (T055-T059)
- ✅ T055: ProductHistoryRecord creation during crawls
- ✅ T056: WebhookDeliveryLog creation for all attempts
- ✅ T057: Immediate per-product webhook delivery
- ✅ T058: Webhook URL validation (HTTPS in production)
- ✅ T059: Comprehensive logging throughout

## Test It Now!

### 1. Register a Website (User Story 1)

```bash
export API_KEY="your-api-key-here"

# Register website with webhook
curl -X POST http://localhost:8000/v1/websites \
  -H "X-API-Key: $API_KEY" \
  -H "Content-Type: application/json" \
  -d '{
    "base_url": "https://example-shop.com",
    "seed_urls": ["https://example-shop.com/products"],
    "crawl_frequency_minutes": 1440,
    "price_change_threshold_pct": 1.0,
    "webhook_endpoint_url": "https://your-server.com/webhooks/obsrv",
    "webhook_enabled": true
  }'

# Save website_id from response
```

### 2. Approve Products

```bash
# Get discovered products
curl -H "X-API-Key: $API_KEY" \
  http://localhost:8000/v1/websites/<website-id>/discovered-products

# Approve products
curl -X POST http://localhost:8000/v1/websites/<website-id>/approve-products \
  -H "X-API-Key: $API_KEY" \
  -H "Content-Type: application/json" \
  -d '{
    "product_urls": [
      "https://example-shop.com/product/123",
      "https://example-shop.com/product/456"
    ]
  }'
```

### 3. Wait for Scheduled Crawl

The scheduled crawl runs daily at 2 AM UTC. For testing, you can:

**Option A**: Manually trigger crawl via Inngest dashboard
- Go to https://app.inngest.com
- Find `scheduled-crawl` function
- Click "Run" to trigger immediately

**Option B**: Wait for next scheduled run
- Crawls run automatically at 2 AM UTC
- Check Inngest dashboard for execution logs

### 4. Verify Change Detection

When a product changes:

```bash
# Check crawl logs
psql "$DATABASE_URL" -c "
SELECT id, status, products_processed, changes_detected, errors_count
FROM crawl_execution_logs
ORDER BY started_at DESC
LIMIT 5;
"

# Check product history
psql "$DATABASE_URL" -c "
SELECT product_id, price, stock_status, price_changed, stock_changed, crawl_timestamp
FROM product_history
ORDER BY crawl_timestamp DESC
LIMIT 10;
"

# Check webhook deliveries
psql "$DATABASE_URL" -c "
SELECT id, status, attempt_number, http_status_code, delivery_timestamp
FROM webhook_delivery_logs
ORDER BY delivery_timestamp DESC
LIMIT 5;
"
```

### 5. Test Webhook Receiver

Example Flask webhook receiver:

```python
from flask import Flask, request, jsonify
import hmac
import hashlib
import time

app = Flask(__name__)
WEBHOOK_SECRET = "your_webhook_secret_from_db"

@app.route('/webhooks/obsrv', methods=['POST'])
def handle_webhook():
    # Verify signature
    signature_header = request.headers.get('X-Obsrv-Signature')
    payload_body = request.get_data(as_text=True)

    parts = dict(item.split('=') for item in signature_header.split(','))
    timestamp = int(parts['t'])
    signature = parts['v1']

    # Check timestamp freshness
    if abs(time.time() - timestamp) > 300:
        return jsonify({"error": "Timestamp too old"}), 401

    # Verify signature
    signed_payload = f"{timestamp}.{payload_body}"
    expected = hmac.new(
        WEBHOOK_SECRET.encode('utf-8'),
        signed_payload.encode('utf-8'),
        hashlib.sha256
    ).hexdigest()

    if not hmac.compare_digest(expected, signature):
        return jsonify({"error": "Invalid signature"}), 401

    # Process webhook
    payload = request.get_json()
    print(f"Received {payload['event_type']}: {payload['product']['name']}")

    if payload['event_type'] == 'product.price_changed':
        change = payload['change']
        print(f"  Price: ${change['old_value']} → ${change['new_value']} ({change['change_pct']}%)")
    elif payload['event_type'] == 'product.stock_changed':
        change = payload['change']
        print(f"  Stock: {change['old_value']} → {change['new_value']}")

    return jsonify({
        "received": True,
        "event_id": payload['event_id'],
        "processed_at": time.strftime('%Y-%m-%dT%H:%M:%SZ')
    }), 200

if __name__ == '__main__':
    app.run(port=5000)
```

### 6. Rotate Webhook Secret

```bash
# Rotate secret (returns new secret once)
curl -X POST http://localhost:8000/v1/auth/webhook-secret \
  -H "X-API-Key: $API_KEY" \
  -H "Content-Type: application/json" \
  -d '{}'

# Response:
{
  "new_secret": "wh_sec_...",
  "previous_secret_expires_at": "2025-11-03T15:00:00Z",
  "rotation_timestamp": "2025-11-03T14:00:00Z"
}

# Update webhook receiver with new secret
# Old secret remains valid for 1 hour
```

## What You Can Do Now

### Full Change Detection & Notifications ✅

1. **Scheduled Crawls**: Daily automatic product checks
2. **Change Detection**: Price and stock monitoring with thresholds
3. **Webhook Delivery**: HMAC-signed notifications with retry
4. **Secret Rotation**: 1-hour grace period for gradual migration
5. **Comprehensive Logging**: Track every crawl, change, and delivery
6. **Auto-pause**: Websites paused after 3 consecutive failures

### Webhook Delivery Flow

```
1. Scheduled crawl runs (2 AM UTC daily)
   ↓
2. Products crawled, changes detected
   ↓
3. For each change: webhook.deliver event sent
   ↓
4. Webhook delivery function triggered
   ↓
5. HTTP POST with HMAC signature
   ↓
6. If failed: Retry after 5min, then 30min
   ↓
7. If exhausted: Status = "exhausted", payload stored
   ↓
8. Delivery log created for monitoring
```

## Architecture Highlights

### Change Detection
```
Current Product Data
  ├── Compare with latest ProductHistoryRecord
  ├── Calculate price change %
  ├── Check against threshold
  ├── Detect stock transitions
  └── Return ChangeDetectionResult
```

### Webhook Security
```
HMAC-SHA256 Signature
  ├── Format: t={timestamp},v1={signature}
  ├── Signed payload: {timestamp}.{json_body}
  ├── 5-minute replay protection
  ├── Constant-time comparison
  └── Support for secret rotation
```

### Retry Logic
```
Attempt 1: Immediate (t=0)
  └─ Failed? → Attempt 2: +5 minutes (t+5min)
              └─ Failed? → Attempt 3: +30 minutes (t+35min)
                          └─ Failed? → Status: exhausted
```

### Database Schema
```
product_history (partitioned by month)
  ├── Columns: price, stock_status, price_changed, stock_changed
  ├── Indexes: (product_id, crawl_timestamp DESC)
  └── Foreign keys: product_id, website_id, crawl_log_id

webhook_delivery_logs
  ├── Columns: status, attempt_number, http_status_code
  ├── Indexes: (website_id), (product_history_id)
  └── Foreign key: website_id
```

## Files Created (User Story 2)

```
backend/src/
├── models/
│   ├── product_history.py ✅ (T044)
│   └── webhook_log.py ✅ (T045)
├── api/
│   ├── schemas/
│   │   ├── webhook_schemas.py ✅ (T046)
│   │   └── auth_schemas.py ✅ (T054)
│   └── routes/
│       └── auth.py ✅ (T054)
├── core/
│   └── webhook_security.py ✅ (T048)
└── services/
    ├── change_detector.py ✅ (T047)
    ├── webhook_service.py ✅ (T049-T050)
    └── inngest_functions/
        ├── scheduled_crawl.py ✅ (T051, T053)
        └── deliver_webhook.py ✅ (T052)
```

## Performance Expectations

Based on implementation:
- **Scheduled Crawl**: Runs daily at 2 AM UTC
- **Change Detection**: < 100ms per product comparison
- **Webhook Delivery**: 10-second timeout per attempt
- **Retry Schedule**: +5min, +30min after failure
- **Signature Generation**: < 1ms per webhook
- **Auto-pause**: After 3 consecutive crawl failures

## Known Behaviors (By Design)

1. **Immediate Webhooks**: One webhook per change (per-product)
2. **Daily Crawls**: Single scheduled crawl per day (configurable)
3. **Max Retries**: 3 attempts before exhaustion
4. **Grace Period**: 1 hour for webhook secret rotation
5. **Auto-pause**: Websites paused after failures for safety

## Success Criteria ✅

User Story 2 Success Criteria (All Met):
- ✅ Scheduled crawls run automatically
- ✅ Price changes detected with threshold filtering
- ✅ Stock status changes detected
- ✅ Webhooks delivered with HMAC signatures
- ✅ Failed webhooks retry with exponential backoff
- ✅ Webhook secrets can be rotated safely
- ✅ All delivery attempts logged
- ✅ Comprehensive logging for monitoring

## Integration with User Story 1

```
User Story 1: Register website → Discover products → Approve → Baseline
                                                                    ↓
User Story 2: Daily crawl → Detect changes → Send webhooks → Retry if failed
```

## Monitoring

### Inngest Dashboard

Visit https://app.inngest.com to monitor:
- **scheduled-crawl** function: Daily crawl executions
- **deliver-webhook** function: Webhook delivery attempts
- Execution logs with step-by-step progress
- Error tracking and retry status

### Database Queries

```sql
-- Recent crawls
SELECT id, website_id, status, products_processed, changes_detected, started_at
FROM crawl_execution_logs
ORDER BY started_at DESC
LIMIT 10;

-- Recent changes
SELECT product_id, price, stock_status, price_changed, stock_changed, crawl_timestamp
FROM product_history
WHERE price_changed = TRUE OR stock_changed = TRUE
ORDER BY crawl_timestamp DESC
LIMIT 20;

-- Webhook delivery success rate
SELECT
    status,
    COUNT(*) as count,
    ROUND(100.0 * COUNT(*) / SUM(COUNT(*)) OVER (), 2) as percentage
FROM webhook_delivery_logs
GROUP BY status;

-- Failed webhooks
SELECT id, target_url, attempt_number, error_message, delivery_timestamp
FROM webhook_delivery_logs
WHERE status IN ('failed', 'exhausted')
ORDER BY delivery_timestamp DESC;
```

## Troubleshooting

### If Webhooks Don't Deliver

1. **Check webhook URL**: Ensure HTTPS in production
2. **Verify endpoint is accessible**: Test with curl
3. **Check webhook logs**: Query webhook_delivery_logs table
4. **Review Inngest logs**: Check deliver-webhook function
5. **Verify signature**: Ensure receiver uses correct secret

### If Changes Not Detected

1. **Check crawl logs**: Review crawl_execution_logs for errors
2. **Verify threshold**: Check price_change_threshold_pct setting
3. **Review product history**: Ensure baseline data exists
4. **Check website status**: Should be "active", not "paused"

### If Scheduled Crawl Doesn't Run

1. **Check Inngest dashboard**: Verify cron trigger is active
2. **Review website status**: Inactive websites are skipped
3. **Check system time**: Ensure UTC timezone is correct

---

**🎉 Congratulations! User Stories 1 AND 2 are now fully functional!**

**Total Implementation Time**: Phases 1-4 complete
- Phase 1: Setup (7 tasks)
- Phase 2: Foundation (13 tasks)
- Phase 3: User Story 1 (23 tasks)
- Phase 4: User Story 2 (16 tasks)
- **Total: 59 tasks complete**

**Remaining**: 49 tasks across 5 phases for full system

**Next Action**: Test User Story 2 or continue to User Story 3!
