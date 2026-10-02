"""Orders, plans, mappings, sales, redeem codes, purchase history."""

import json
import os
import re
from datetime import timedelta

from bot_app.timeutil import myanmar_now

from bot_app.config import PLANS
from bot_app.storage.kv import redis_get, redis_set
from bot_app.storage.paths import (ADMIN_MSG_MAP_FILE, KEY_ORDERS_FILE, MAPPING_FILE,
                             ORDERS_FILE, REDEEM_FILE, REPLACEMENT_MSG_MAP_FILE,
                             SALES_FILE, STATE_FILE, USER_HISTORY_FILE)


def load_all_user_history():
    data = redis_get("user_purchases_data")
    if data is not None:
        return data
    if os.path.exists(USER_HISTORY_FILE):
        try:
            with open(USER_HISTORY_FILE, 'r') as f:
                return json.load(f)
        except:
            pass
    return {}

def save_user_purchase_record(chat_id, order_id, plan_name, disp_gb, months_count, price_str, server_num, expire_date, vpn_key):
    history_data = load_all_user_history()
    uid = str(chat_id)
    if uid not in history_data:
        history_data[uid] = []
        
    now = myanmar_now()
    record = {
        "timestamp": now.strftime("%d/%m/%Y (%I:%M %p)"),
        "order_id": order_id if order_id else "N/A",
        "plan_name": plan_name,
        "disp_gb": disp_gb,
        "months": months_count,
        "price_str": price_str,
        "server": str(server_num),
        "expire_date": expire_date,
        "vpn_key": vpn_key
    }
    history_data[uid].append(record)
    redis_set("user_purchases_data", history_data)
    try:
        with open(USER_HISTORY_FILE, 'w') as f:
            json.dump(history_data, f)
    except:
        pass

def get_user_combined_purchase_records(chat_id):
    from bot_app.services.registry import load_persistent_keys
    history_data = load_all_user_history()
    records = list(history_data.get(str(chat_id), []))
    known_orders = set(r.get("order_id") for r in records if r.get("order_id") and r.get("order_id") != "N/A")

    sales = load_sales_history()
    user_sales = [s for s in sales if str(s.get("chat_id")) == str(chat_id)]
    persistent_registry = load_persistent_keys()

    for s in user_sales:
        s_ord = s.get("order_id", "N/A")
        if s_ord != "N/A" and s_ord in known_orders:
            continue
            
        srv_num = str(s.get("server", "1"))
        matched_key_link = "N/A"
        exp_date_found = "မသိရှိပါ"
        
        for k_data in persistent_registry.values():
            if str(k_data.get("chat_id")) == str(chat_id) and str(k_data.get("server")) == srv_num:
                matched_key_link = k_data.get("access_url", "N/A")
                exp_date_found = k_data.get("expire_date", "မသိရှိပါ")
                break

        p_info = PLANS.get(s.get("plan_code"), {})
        disp_gb = p_info.get("data", "N/A")

        legacy_rec = {
            "timestamp": s.get("timestamp", s.get("date", "N/A")),
            "order_id": s_ord,
            "plan_name": s.get("plan_name", "VPN Plan"),
            "disp_gb": disp_gb,
            "months": s.get("months", 1),
            "price_str": f"{s.get('price', 0):,} Ks",
            "server": srv_num,
            "expire_date": exp_date_found,
            "vpn_key": matched_key_link
        }
        records.append(legacy_rec)
        if s_ord != "N/A":
            known_orders.add(s_ord)
            
    return records

# 🔍 OCR Space Helper Functions

def load_orders():
    data = redis_get("orders_data")
    if data is not None:
        return data
    if os.path.exists(ORDERS_FILE):
        try:
            with open(ORDERS_FILE, 'r') as f:
                return json.load(f)
        except:
            pass
    return {}

def save_order(order_id, order_data):
    orders = load_orders()
    orders[str(order_id)] = order_data
    redis_set("orders_data", orders)
    try:
        with open(ORDERS_FILE, 'w') as f:
            json.dump(orders, f)
    except:
        pass

def load_key_orders():
    data = redis_get("key_orders")
    if data is not None:
        return data
    if os.path.exists(KEY_ORDERS_FILE):
        try:
            with open(KEY_ORDERS_FILE, 'r') as f:
                return json.load(f)
        except:
            pass
    return {}

def map_key_to_order(key_name, order_id):
    if not order_id or not key_name:
        return
    data = load_key_orders()
    clean_k = key_name.strip().lower()
    data[clean_k] = str(order_id)
    redis_set("key_orders", data)
    try:
        with open(KEY_ORDERS_FILE, 'w') as f:
            json.dump(data, f)
    except:
        pass

def get_order_id_for_key(key_name):
    data = load_key_orders()
    clean_k = key_name.strip().lower()
    return data.get(clean_k, "N/A")

def save_user_id(chat_id):
    users = redis_get("all_users") or []
    if str(chat_id) not in [str(u) for u in users]:
        users.append(str(chat_id))
        redis_set("all_users", users)

def load_all_users():
    data = redis_get("all_users")
    if data is not None:
        return data
    return []

def load_user_plans():
    data = redis_get("user_plans")
    if data is not None:
        return data
    if os.path.exists(STATE_FILE):
        try:
            with open(STATE_FILE, 'r') as f:
                return json.load(f)
        except:
            pass
    return {}

def save_user_plan(chat_id, plan_data):
    plans = load_user_plans()
    plans[str(chat_id)] = plan_data
    redis_set("user_plans", plans)
    try:
        with open(STATE_FILE, 'w') as f:
            json.dump(plans, f)
    except:
        pass

def load_key_mappings():
    data = redis_get("key_mappings")
    if data is not None:
        return data
    if os.path.exists(MAPPING_FILE):
        try:
            with open(MAPPING_FILE, 'r') as f:
                return json.load(f)
        except:
            pass
    return {}

def save_key_mapping(clean_name, chat_id):
    mappings = load_key_mappings()
    mappings[clean_name.strip().lower()] = str(chat_id)
    redis_set("key_mappings", mappings)
    try:
        with open(MAPPING_FILE, 'w') as f:
            json.dump(mappings, f)
    except:
        pass

def load_sales_history():
    data = redis_get("sales_history")
    if data is not None:
        return data
    if os.path.exists(SALES_FILE):
        try:
            with open(SALES_FILE, 'r') as f:
                return json.load(f)
        except:
            pass
    return []

def save_sale_transaction(server_num, chat_id, plan_code, plan_name, months_count, price_int, order_id=None):
    sales = load_sales_history()
    now = myanmar_now()
    sale_data = {
        "timestamp": now.strftime("%Y-%m-%d %H:%M:%S"),
        "date": now.strftime("%Y-%m-%d"),
        "year": now.year,
        "month": now.month,
        "server": str(server_num),
        "chat_id": str(chat_id),
        "plan_code": plan_code,
        "plan_name": plan_name,
        "months": months_count,
        "price": int(price_int) if price_int else 0,
        "order_id": order_id or "N/A"
    }
    sales.append(sale_data)
    redis_set("sales_history", sales)
    try:
        with open(SALES_FILE, 'w') as f:
            json.dump(sales, f)
    except:
        pass

def save_admin_msg_map(target_chat_id, admin_msg_dict):
    try:
        data = redis_get("admin_msg_map") or {}
        data[str(target_chat_id)] = admin_msg_dict
        redis_set("admin_msg_map", data)
    except:
        pass

def get_admin_msg_map(target_chat_id):
    try:
        data = redis_get("admin_msg_map") or {}
        if not data and os.path.exists(ADMIN_MSG_MAP_FILE):
            with open(ADMIN_MSG_MAP_FILE, 'r') as f:
                data = json.load(f)
        return data.get(str(target_chat_id), {})
    except:
        return {}

def save_replacement_msg_map(request_key, admin_msg_dict):
    try:
        data = redis_get("replacement_msg_map") or {}
        data[str(request_key)] = admin_msg_dict
        redis_set("replacement_msg_map", data)
    except:
        pass

def get_replacement_msg_map(request_key):
    try:
        data = redis_get("replacement_msg_map") or {}
        if not data and os.path.exists(REPLACEMENT_MSG_MAP_FILE):
            with open(REPLACEMENT_MSG_MAP_FILE, 'r') as f:
                data = json.load(f)
        return data.get(str(request_key), {})
    except:
        return {}

# 🎟️ Wallet Amount Redeem Code Storage System

def load_redeem_codes():
    data = redis_get("redeem_codes")
    if data is not None:
        return data
    if os.path.exists(REDEEM_FILE):
        try:
            with open(REDEEM_FILE, 'r') as f:
                return json.load(f)
        except:
            pass
    return {}

def save_redeem_codes(codes):
    redis_set("redeem_codes", codes)
    try:
        with open(REDEEM_FILE, 'w') as f:
            json.dump(codes, f)
    except:
        pass


def is_code_expired(info: dict) -> bool:
    """True when a redeem code carries an ``expires_at`` in the past.

    Codes without ``expires_at`` (Telegram-generated) never expire. An
    unparseable timestamp is treated as not expired so a bad record can
    never lock out redemption silently — the dashboard shows the raw string.
    """
    raw = (info or {}).get("expires_at")
    if not raw:
        return False
    try:
        from datetime import datetime
        return datetime.strptime(str(raw), "%d/%m/%Y %I:%M %p") < myanmar_now()
    except (ValueError, TypeError):
        return False


# --- Admin purchase history (unified cross-store feed) ----------------------

# Each wallet purchase is written to two stores: ``sales_history`` (revenue-grade,
# numeric price) below, and ``user_purchases_data`` (display record with vpn_key /
# expire_date) keyed by chat_id above. The admin view needs both shapes, so merge
# them per order_id — same dedup rule as get_user_combined_purchase_records.

_HISTORY_TS_FMT = "%d/%m/%Y (%I:%M %p)"
_SALE_TS_FMT = "%Y-%m-%d %H:%M:%S"


def _parse_purchase_ts(raw, fmt):
    """Parse a stored timestamp; return a naive datetime or None."""
    from datetime import datetime
    try:
        return datetime.strptime(str(raw or "").strip(), fmt)
    except (ValueError, TypeError):
        return None


def _price_str_to_int(price_str):
    """Best-effort "5,000 Ks" -> 5000 (0 for free/"0 Ks (Points)" records)."""
    match = re.search(r"[\d,]+", str(price_str or ""))
    if not match:
        return 0
    try:
        return int(match.group(0).replace(",", ""))
    except ValueError:
        return 0


def get_purchase_history(days=None, server=None, search=None, limit=500):
    """Newest-first purchase feed merging both purchase stores.

    ``days`` keeps records from the last N Myanmar-time days, ``server``
    filters by server id (exact string, "VIP" included), ``search`` matches
    chat_id / order_id / plan name / customer name. Points-redemption
    records (kind "points", written only to user_purchases_data) are included
    and excluded from revenue sums. Returns summary counters computed over the
    server/search filter but before the days window, plus the (capped) items.
    """
    from bot_app.services.outline import get_server_display_name
    from bot_app.services.profiles import load_all_profiles

    history = load_all_user_history()
    sales = load_sales_history()
    profiles = load_all_profiles()

    merged = {}   # order_id -> item (detail record wins)
    extras = []   # records without a usable order_id, keyed by (chat_id, ts)

    def _server_name(sid):
        sid = str(sid or "")
        return get_server_display_name(sid) if sid.isdigit() else (sid or "—")

    def _finalize(item):
        profile = profiles.get(str(item.get("chat_id", "")), {})
        item["username"] = profile.get("username", "")
        item["full_name"] = profile.get("full_name", "")
        item["server_name"] = _server_name(item.get("server"))
        dt = item.get("_dt")
        item["ts"] = dt.strftime("%Y-%m-%dT%H:%M:%S") if dt else ""
        item["time_str"] = dt.strftime("%d/%m/%Y %H:%M") if dt else (item.get("timestamp") or "")
        del item["_dt"]
        return item

    # Detail store: one record per delivered purchase.
    for uid, records in history.items():
        for rec in records or []:
            order_id = rec.get("order_id") or "N/A"
            item = {
                "order_id": order_id,
                "chat_id": str(uid),
                "timestamp": rec.get("timestamp", ""),
                "_dt": _parse_purchase_ts(rec.get("timestamp"), _HISTORY_TS_FMT),
                "plan_name": rec.get("plan_name", ""),
                "months": rec.get("months", 1),
                "disp_gb": rec.get("disp_gb", ""),
                "price": _price_str_to_int(rec.get("price_str")),
                "price_str": rec.get("price_str", ""),
                "server": str(rec.get("server", "")),
                "expire_date": rec.get("expire_date", ""),
                "vpn_key": rec.get("vpn_key", ""),
                "kind": "points" if "Points" in str(rec.get("price_str", "")) else "paid",
                "source": "history",
            }
            if order_id != "N/A" and order_id not in merged:
                merged[order_id] = item
            else:
                extras.append(item)

    # Revenue store: fill chat_id/numeric price, add sales-only records.
    for s in sales:
        order_id = s.get("order_id") or "N/A"
        dt = _parse_purchase_ts(s.get("timestamp"), _SALE_TS_FMT)
        price = int(s.get("price", 0) or 0)
        if order_id != "N/A" and order_id in merged:
            item = merged[order_id]
            item["chat_id"] = item["chat_id"] or str(s.get("chat_id", ""))
            if item["kind"] != "points":
                item["price"] = price
                item["price_str"] = item["price_str"] or f"{price:,} Ks"
            item["source"] = "both"
            if item["_dt"] is None:
                item["_dt"] = dt
            continue
        item = {
            "order_id": order_id,
            "chat_id": str(s.get("chat_id", "")),
            "timestamp": s.get("timestamp", ""),
            "_dt": dt,
            "plan_name": s.get("plan_name", ""),
            "months": s.get("months", 1),
            "disp_gb": "",
            "price": price,
            "price_str": f"{price:,} Ks",
            "server": str(s.get("server", "")),
            "expire_date": "",
            "vpn_key": "",
            "kind": "paid",
            "source": "sale",
        }
        if order_id != "N/A":
            merged[order_id] = item
        else:
            extras.append(item)

    items = [_finalize(i) for i in merged.values()]
    extras = [_finalize(i) for i in extras]
    # N/A-order duplicates can exist in both stores; drop extras whose
    # (chat_id, ts) already appeared through a merged record.
    seen_keys = {(i["chat_id"], i["ts"]) for i in items}
    for item in extras:
        key = (item["chat_id"], item["ts"])
        if key in seen_keys:
            continue
        seen_keys.add(key)
        items.append(item)

    q = (search or "").strip().lower()
    if server:
        items = [i for i in items if str(i.get("server")) == str(server)]
    if q:
        def _match(i):
            return (q in str(i.get("chat_id", "")).lower()
                    or q in str(i.get("order_id", "")).lower()
                    or q in str(i.get("plan_name", "")).lower()
                    or q in str(i.get("username", "")).lower()
                    or q in str(i.get("full_name", "")).lower())
        items = [i for i in items if _match(i)]

    def _paid(i):
        return i.get("kind") != "points"

    now = myanmar_now()
    today_s = now.strftime("%Y-%m-%d")
    month_s = now.strftime("%Y-%m")
    paid_items = [i for i in items if _paid(i)]
    # Counters key on the normalized ISO ts (both stores' raw formats differ).
    def _on(item, prefix):
        return str(item.get("ts", ""))[: len(prefix)] == prefix
    summary = {
        "today_revenue_ks": sum(i["price"] for i in paid_items if _on(i, today_s)),
        "today_count": sum(1 for i in items if _on(i, today_s)),
        "month_revenue_ks": sum(i["price"] for i in paid_items if _on(i, month_s)),
        "month_count": sum(1 for i in items if _on(i, month_s)),
    }

    items.sort(key=lambda i: i.get("ts") or "", reverse=True)
    if days:
        cutoff = (now - timedelta(days=int(days))).strftime("%Y-%m-%dT%H:%M:%S")
        items = [i for i in items if i.get("ts") and i["ts"] >= cutoff]

    if limit:
        items = items[: int(limit)]
    return {"total": len(items), "summary": summary, "items": items}
