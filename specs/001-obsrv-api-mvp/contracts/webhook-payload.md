# Webhook Payload Specification

**Feature**: Obsrv API - E-commerce Monitoring System MVP
**Version**: 1.0.0
**Date**: 2025-11-03

## Overview

This document specifies the webhook notification format sent by Obsrv API when product price or stock changes are detected. All webhooks are authenticated using HMAC-SHA256 signatures.

## Webhook Delivery

### HTTP Request

```http
POST {client_webhook_endpoint_url}
Content-Type: application/json
X-Obsrv-Signature: t=1699000000,v1=a1b2c3d4e5f6...
User-Agent: Obsrv-Webhook/1.0
```

### Headers

| Header Name | Required | Description |
|------------|----------|-------------|
| `Content-Type` | Yes | Always `application/json` |
| `X-Obsrv-Signature` | Yes | HMAC-SHA256 signature for verification |
| `User-Agent` | Yes | Obsrv webhook client identifier |
| `X-Obsrv-Event` | Yes | Event type: `product.price_changed` or `product.stock_changed` |
| `X-Obsrv-Delivery-ID` | Yes | Unique delivery attempt UUID |

## Signature Verification

### Signature Format

```
X-Obsrv-Signature: t={unix_timestamp},v1={hmac_signature}
```

**Components**:
- `t`: Unix timestamp when signature was generated (for replay attack prevention)
- `v1`: HMAC-SHA256 hex digest of `{timestamp}.{json_body}` using webhook secret

### Verification Steps

1. **Extract timestamp and signature**:
```python
signature_header = request.headers['X-Obsrv-Signature']
parts = dict(item.split('=') for item in signature_header.split(','))
timestamp = int(parts['t'])
signature = parts['v1']
```

2. **Check timestamp freshness** (prevent replay attacks):
```python
import time
if abs(time.time() - timestamp) > 300:  # 5 minute tolerance
    raise Exception("Webhook timestamp too old")
```

3. **Compute expected signature**:
```python
import hmac
import hashlib

payload_body = request.get_data(as_text=True)  # Raw JSON string
signed_payload = f"{timestamp}.{payload_body}"
expected_signature = hmac.new(
    webhook_secret.encode('utf-8'),
    signed_payload.encode('utf-8'),
    hashlib.sha256
).hexdigest()
```

4. **Compare signatures** (constant-time to prevent timing attacks):
```python
import hmac
if not hmac.compare_digest(expected_signature, signature):
    raise Exception("Invalid webhook signature")
```

### Example Verification (Python)

```python
import hmac
import hashlib
import time
from flask import request

def verify_webhook_signature(request, webhook_secret):
    """Verify Obsrv webhook HMAC signature"""
    # Extract signature header
    signature_header = request.headers.get('X-Obsrv-Signature')
    if not signature_header:
        return False, "Missing signature header"

    # Parse signature components
    try:
        parts = dict(item.split('=') for item in signature_header.split(','))
        timestamp = int(parts['t'])
        received_signature = parts['v1']
    except (KeyError, ValueError):
        return False, "Malformed signature header"

    # Check timestamp freshness (5 minute tolerance)
    if abs(time.time() - timestamp) > 300:
        return False, "Signature timestamp too old"

    # Compute expected signature
    payload_body = request.get_data(as_text=True)
    signed_payload = f"{timestamp}.{payload_body}"
    expected_signature = hmac.new(
        webhook_secret.encode('utf-8'),
        signed_payload.encode('utf-8'),
        hashlib.sha256
    ).hexdigest()

    # Constant-time comparison
    if not hmac.compare_digest(expected_signature, received_signature):
        return False, "Signature verification failed"

    return True, "Signature valid"
```

## Payload Schemas

### Price Change Event

**Event Type**: `product.price_changed`

**Payload**:
```json
{
  "event_type": "product.price_changed",
  "event_id": "a1b2c3d4-e5f6-7890-abcd-ef1234567890",
  "timestamp": "2025-11-03T14:30:00Z",
  "website": {
    "id": "website-uuid",
    "base_url": "https://example-shop.com",
    "name": "Example Shop"
  },
  "product": {
    "id": "product-uuid",
    "url": "https://example-shop.com/products/laptop-xyz",
    "name": "Gaming Laptop XYZ",
    "extracted_product_id": "SKU-12345"
  },
  "change": {
    "type": "price",
    "old_value": 1299.99,
    "new_value": 1199.99,
    "currency": "USD",
    "change_pct": -7.69,
    "absolute_change": -100.00,
    "detected_at": "2025-11-03T14:28:45Z"
  },
  "metadata": {
    "crawl_id": "crawl-uuid",
    "threshold_pct": 1.0,
    "exceeded_threshold": true
  }
}
```

**Field Descriptions**:

| Field | Type | Description |
|-------|------|-------------|
| `event_type` | string | Always `product.price_changed` |
| `event_id` | string (UUID) | Unique event identifier |
| `timestamp` | string (ISO 8601) | Webhook generation timestamp |
| `website.id` | string (UUID) | Monitored website identifier |
| `website.base_url` | string (URI) | Website base URL |
| `website.name` | string | Human-readable website name |
| `product.id` | string (UUID) | Product identifier |
| `product.url` | string (URI) | Product page URL |
| `product.name` | string | Product display name |
| `product.extracted_product_id` | string | Extracted SKU/product code |
| `change.type` | string | Always `price` for price change events |
| `change.old_value` | number | Previous price |
| `change.new_value` | number | Current price |
| `change.currency` | string | ISO 4217 currency code |
| `change.change_pct` | number | Percentage change (negative = decrease) |
| `change.absolute_change` | number | Absolute price difference |
| `change.detected_at` | string (ISO 8601) | When change was detected |
| `metadata.crawl_id` | string (UUID) | Crawl execution identifier |
| `metadata.threshold_pct` | number | Configured threshold percentage |
| `metadata.exceeded_threshold` | boolean | Whether change exceeded threshold |

---

### Stock Change Event

**Event Type**: `product.stock_changed`

**Payload**:
```json
{
  "event_type": "product.stock_changed",
  "event_id": "b2c3d4e5-f6g7-8901-bcde-fg2345678901",
  "timestamp": "2025-11-03T15:45:00Z",
  "website": {
    "id": "website-uuid",
    "base_url": "https://example-shop.com",
    "name": "Example Shop"
  },
  "product": {
    "id": "product-uuid",
    "url": "https://example-shop.com/products/monitor-abc",
    "name": "4K Monitor ABC",
    "extracted_product_id": "SKU-67890"
  },
  "change": {
    "type": "stock",
    "old_value": "in_stock",
    "new_value": "out_of_stock",
    "detected_at": "2025-11-03T15:43:12Z"
  },
  "metadata": {
    "crawl_id": "crawl-uuid",
    "price_at_change": 599.99,
    "currency": "USD"
  }
}
```

**Field Descriptions**:

| Field | Type | Description |
|-------|------|-------------|
| `event_type` | string | Always `product.stock_changed` |
| `event_id` | string (UUID) | Unique event identifier |
| `timestamp` | string (ISO 8601) | Webhook generation timestamp |
| `website.*` | object | Same as price change event |
| `product.*` | object | Same as price change event |
| `change.type` | string | Always `stock` for stock change events |
| `change.old_value` | string (enum) | Previous stock status: `in_stock`, `out_of_stock`, `limited_availability`, `unknown` |
| `change.new_value` | string (enum) | Current stock status: `in_stock`, `out_of_stock`, `limited_availability`, `unknown` |
| `change.detected_at` | string (ISO 8601) | When change was detected |
| `metadata.crawl_id` | string (UUID) | Crawl execution identifier |
| `metadata.price_at_change` | number | Product price at time of stock change |
| `metadata.currency` | string | ISO 4217 currency code |

---

## Retry Logic

### Retry Schedule

Obsrv API automatically retries failed webhook deliveries using exponential backoff:

1. **Attempt 1**: Immediate delivery (t=0)
2. **Attempt 2**: 5 minutes after failure (t+5min)
3. **Attempt 3**: 30 minutes after previous failure (t+35min)
4. **Exhausted**: After 3 failed attempts, webhook marked as failed

### Success Criteria

Webhook delivery is considered **successful** if:
- HTTP status code is `2xx` (200-299)
- Response received within 10 seconds

### Failure Conditions

Webhook delivery **fails** if:
- HTTP status code is `4xx` or `5xx`
- Network timeout (>10 seconds)
- Connection refused or DNS resolution failure

### Failed Webhook Recovery

If webhook delivery fails after 3 attempts:
1. Webhook log entry created with status `exhausted`
2. Failed payload stored in database for client retrieval
3. Client can query failed webhooks via API: `GET /webhooks/failed`
4. Manual retry available via API: `POST /webhooks/{webhook_id}/retry`

---

## Response Expectations

### Recommended Response

```http
HTTP/1.1 200 OK
Content-Type: application/json

{
  "received": true,
  "event_id": "a1b2c3d4-e5f6-7890-abcd-ef1234567890",
  "processed_at": "2025-11-03T14:30:05Z"
}
```

### Response Requirements

- Return HTTP status `200 OK` quickly (within 10 seconds)
- Process webhook asynchronously if needed (acknowledge first, process later)
- Idempotency: Handle duplicate deliveries gracefully using `event_id`
- Validation: Verify signature before processing payload

### Error Responses

If webhook receiver encounters an error:

```http
HTTP/1.1 500 Internal Server Error
Content-Type: application/json

{
  "error": "Internal processing error",
  "event_id": "a1b2c3d4-e5f6-7890-abcd-ef1234567890"
}
```

Obsrv API will automatically retry based on retry schedule.

---

## Testing Webhooks

### Test Payload Generation

Use API endpoint to generate test webhook:

```http
POST /v1/webhooks/test
X-API-Key: {your_api_key}
Content-Type: application/json

{
  "event_type": "product.price_changed",
  "webhook_endpoint_url": "https://your-endpoint.example.com/webhooks/obsrv"
}
```

### Test Signature Verification

```bash
# Example signature verification using curl
WEBHOOK_SECRET="your_webhook_secret"
TIMESTAMP=$(date +%s)
PAYLOAD='{"event_type":"product.price_changed","test":true}'
SIGNATURE=$(echo -n "${TIMESTAMP}.${PAYLOAD}" | openssl dgst -sha256 -hmac "$WEBHOOK_SECRET" | cut -d' ' -f2)

curl -X POST https://your-endpoint.example.com/webhooks/obsrv \
  -H "Content-Type: application/json" \
  -H "X-Obsrv-Signature: t=${TIMESTAMP},v1=${SIGNATURE}" \
  -H "X-Obsrv-Event: product.price_changed" \
  -H "X-Obsrv-Delivery-ID: test-delivery-id" \
  -d "${PAYLOAD}"
```

---

## Best Practices

### Security

1. **Always verify signatures**: Never trust webhook payloads without signature verification
2. **Use HTTPS only**: Obsrv API rejects HTTP webhook endpoints in production
3. **Rotate secrets regularly**: Use API to rotate webhook secrets every 90 days
4. **Implement replay protection**: Check timestamp freshness (5-minute window)
5. **Rate limiting**: Implement rate limiting on webhook endpoint to prevent DoS

### Reliability

1. **Idempotency**: Use `event_id` to deduplicate events (same event may be delivered multiple times)
2. **Fast responses**: Return `200 OK` quickly, process asynchronously if needed
3. **Graceful degradation**: If webhook receiver is down, failed webhooks can be retrieved via API
4. **Monitoring**: Alert on high webhook failure rates (>10%)

### Performance

1. **Async processing**: Queue webhook payloads for background processing
2. **Batching**: If receiving high webhook volume, batch database updates
3. **Connection pooling**: Reuse database connections for webhook processing

---

## Example Implementations

### Python (Flask)

```python
from flask import Flask, request, jsonify
import hmac
import hashlib
import time

app = Flask(__name__)
WEBHOOK_SECRET = "your_webhook_secret"

@app.route('/webhooks/obsrv', methods=['POST'])
def handle_obsrv_webhook():
    # Verify signature
    is_valid, message = verify_webhook_signature(request, WEBHOOK_SECRET)
    if not is_valid:
        return jsonify({"error": message}), 401

    # Parse payload
    payload = request.get_json()
    event_type = payload['event_type']
    event_id = payload['event_id']

    # Process event (async recommended)
    if event_type == 'product.price_changed':
        process_price_change(payload)
    elif event_type == 'product.stock_changed':
        process_stock_change(payload)

    # Return success
    return jsonify({
        "received": True,
        "event_id": event_id,
        "processed_at": time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime())
    }), 200

def verify_webhook_signature(request, webhook_secret):
    # Implementation from earlier example
    pass

def process_price_change(payload):
    # Queue for async processing
    pass

def process_stock_change(payload):
    # Queue for async processing
    pass
```

### Node.js (Express)

```javascript
const express = require('express');
const crypto = require('crypto');

const app = express();
const WEBHOOK_SECRET = 'your_webhook_secret';

app.use(express.json());

app.post('/webhooks/obsrv', (req, res) => {
  // Verify signature
  const signatureHeader = req.headers['x-obsrv-signature'];
  if (!verifySignature(signatureHeader, req.body, WEBHOOK_SECRET)) {
    return res.status(401).json({ error: 'Invalid signature' });
  }

  // Process event
  const { event_type, event_id } = req.body;

  if (event_type === 'product.price_changed') {
    processPriceChange(req.body);
  } else if (event_type === 'product.stock_changed') {
    processStockChange(req.body);
  }

  // Return success
  res.status(200).json({
    received: true,
    event_id: event_id,
    processed_at: new Date().toISOString()
  });
});

function verifySignature(signatureHeader, payload, secret) {
  const parts = signatureHeader.split(',').reduce((acc, part) => {
    const [key, value] = part.split('=');
    acc[key] = value;
    return acc;
  }, {});

  const timestamp = parseInt(parts.t);
  const signature = parts.v1;

  // Check timestamp freshness
  if (Math.abs(Date.now() / 1000 - timestamp) > 300) {
    return false;
  }

  // Compute expected signature
  const signedPayload = `${timestamp}.${JSON.stringify(payload)}`;
  const expectedSignature = crypto
    .createHmac('sha256', secret)
    .update(signedPayload)
    .digest('hex');

  // Constant-time comparison
  return crypto.timingSafeEqual(
    Buffer.from(expectedSignature),
    Buffer.from(signature)
  );
}

app.listen(3000);
```

---

**Status**: ✅ Webhook specification complete
