# Backend REST API Specification

## 1. Authentication & Security

### 1.1 Telegram Mini App Authentication (Primary)
The client sends the raw `initData` query string provided by the Telegram WebApp SDK in the `X-Telegram-Init-Data` header.

**Verification Algorithm (Python)**:
```python
import hmac
import hashlib
from urllib.parse import parse_qsl

def verify_telegram_init_data(init_data_raw: str, bot_token: str) -> dict | None:
    try:
        parsed_data = dict(parse_qsl(init_data_raw, keep_blank_values=True))
        hash_check = parsed_data.pop("hash", None)
        if not hash_check:
            return None
        
        data_check_string = "\n".join(f"{k}={v}" for k, v in sorted(parsed_data.items()))
        secret_key = hmac.new(b"WebAppData", bot_token.encode(), hashlib.sha256).digest()
        computed_hash = hmac.new(secret_key, data_check_string.encode(), hashlib.sha256).hexdigest()
        
        if hmac.compare_digest(computed_hash, hash_check):
            import json
            user = json.loads(parsed_data.get("user", "{}"))
            return user
    except Exception:
        return None
    return None
```
If `user["id"]` is in `ADMIN_CHAT_IDS`, the request is authenticated as an Admin.

### 1.2 Standalone Web Browser Authentication (Fallback)
Header: `Authorization: Bearer <ADMIN_SESSION_TOKEN>`
Generated via `POST /api/auth/login` using an Admin PIN/Password configured in `.env`.

---

## 2. API Endpoints

### 2.1 System Telemetry & Overview
#### `GET /api/admin/overview`
Returns live server metrics, customer totals, and pending actions.
- **Response `200 OK`**:
```json
{
  "servers": [
    {
      "id": 1,
      "name": "Server 1 (SG-1)",
      "is_active": true,
      "total_keys": 48,
      "total_transferred_gb": 421.5,
      "latency_ms": 45
    },
    {
      "id": 2,
      "name": "Server 2 (SG-2)",
      "is_active": true,
      "total_keys": 62,
      "total_transferred_gb": 612.8,
      "latency_ms": 42
    },
    {
      "id": 3,
      "name": "Server 3 (VIP)",
      "is_active": true,
      "total_keys": 32,
      "total_transferred_gb": 289.1,
      "latency_ms": 38
    }
  ],
  "metrics": {
    "total_active_keys": 142,
    "total_customers": 320,
    "pending_slips": 3,
    "today_revenue_ks": 150000,
    "month_revenue_ks": 3450000
  },
  "traffic_trend": [
    { "timestamp": "2026-09-23T12:00:00Z", "used_gb": 120.4 },
    { "timestamp": "2026-09-23T16:00:00Z", "used_gb": 310.2 },
    { "timestamp": "2026-09-23T20:00:00Z", "used_gb": 540.7 }
  ]
}
```

---

### 2.2 Outline Access Keys Management
#### `GET /api/admin/keys`
Query parameters: `server_id` (optional), `search` (name, id, port), `page`, `page_size`.
- **Response `200 OK`**:
```json
{
  "total": 142,
  "items": [
    {
      "id": 101,
      "outline_key_id": "12",
      "name": "user_8778394176_starter",
      "server_id": 1,
      "server_name": "Server 1",
      "used_bytes": 14520000000,
      "data_limit_bytes": 32212254720,
      "used_gb": 13.52,
      "limit_gb": 30.0,
      "expires_at": "2026-10-21T00:00:00Z",
      "status": "ACTIVE",
      "access_url": "ss://..."
    }
  ]
}
```

#### `POST /api/admin/keys`
Manually generate an access key.
- **Payload**:
```json
{
  "server_id": 1,
  "name": "Custom VIP Key",
  "data_limit_gb": 50,
  "valid_days": 30,
  "assign_to_user_id": 8778394176
}
```

#### `DELETE /api/admin/keys/{id}`
Deletes key from Outline Server and updates database status to `REVOKED`.

#### `POST /api/admin/keys/{id}/extend`
Extends key validity duration.
- **Payload**: `{ "add_days": 30, "add_gb": 0 }`

---

### 2.3 Slips & Payment Verification Queue
#### `GET /api/admin/slips`
Query parameters: `status` (PENDING, APPROVED, REJECTED, default: PENDING).
- **Response `200 OK`**:
```json
[
  {
    "id": 54,
    "user_id": 10,
    "telegram_id": 8778394176,
    "username": "H_M_A_2026",
    "amount_ks": 10000,
    "image_url": "https://storage.supabase.co/...",
    "extracted_tx_id": "981245",
    "created_at": "2026-09-23T20:45:00Z"
  }
]
```

#### `POST /api/admin/slips/{id}/review`
- **Payload**:
```json
{
  "action": "APPROVE", // or "REJECT"
  "reason": "Verified KBZPay transaction #981245"
}
```
*Note: Approving automatically increments `users.wallet_balance` and sends a notification message to the user via Telegram.*

---

### 2.4 Redeem Code Management
#### `GET /api/admin/redeems`
Lists active and past redeem codes.

#### `POST /api/admin/redeems/batch`
- **Payload**:
```json
{
  "amount_ks": 5000,
  "mode": "single", // "single" or "shared"
  "valid_days": 30,
  "count": 5
}
```
- **Response `200 OK`**:
```json
{
  "created_count": 5,
  "codes": ["RD-7A9B1C", "RD-2D4E6F", "RD-8G1H3J", "RD-5K7L9M", "RD-0N2P4Q"]
}
```

---

### 2.5 Customers & Wallets
#### `GET /api/admin/customers`
Returns paginated user list with wallet balances and subscription statuses.

#### `POST /api/admin/customers/{id}/balance`
- **Payload**:
```json
{
  "adjustment_type": "TOPUP", // or "DEDUCT"
  "amount_ks": 5000,
  "reason": "Special event bonus"
}
```
