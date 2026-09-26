"""Persistent key registry (Outline keys + legacy sales/orders)."""

import json
import os
import re

from bot_app.services.orders import load_key_orders, load_orders, load_sales_history
from bot_app.storage.kv import redis_get, redis_set
from bot_app.storage.paths import PERSISTENT_KEYS_FILE


def load_persistent_keys():
    data = redis_get("persistent_keys_registry")
    if data is not None:
        return data
    if os.path.exists(PERSISTENT_KEYS_FILE):
        try:
            with open(PERSISTENT_KEYS_FILE, 'r') as f:
                return json.load(f)
        except:
            pass
    return {}

def save_persistent_key(server_num, key_id, name, access_url, limit_bytes=None, order_id=None, chat_id=None):
    if not key_id or not server_num:
        return
    registry = load_persistent_keys()
    uid = f"{server_num}_{key_id}"
    
    date_match = re.search(r'\d{1,2}\.\d{1,2}\.(\d{4}|\d{2})', name)
    exp_date = date_match.group(0) if date_match else "မသိရှိပါ"
    
    existing = registry.get(uid, {})
    registry[uid] = {
        "server": str(server_num),
        "key_id": str(key_id),
        "name": name,
        "access_url": access_url if access_url else existing.get("access_url", ""),
        "limit_bytes": limit_bytes if limit_bytes else existing.get("limit_bytes"),
        "expire_date": exp_date if exp_date != "မသိရှိပါ" else existing.get("expire_date", "မသိရှိပါ"),
        "order_id": order_id if order_id else existing.get("order_id", "N/A"),
        "chat_id": str(chat_id) if chat_id else existing.get("chat_id", "")
    }
    redis_set("persistent_keys_registry", registry)
    try:
        with open(PERSISTENT_KEYS_FILE, 'w') as f:
            json.dump(registry, f)
    except:
        pass

def sync_keys_to_persistent_registry(server_num, keys_data):
    if not keys_data:
        return
    registry = load_persistent_keys()
    key_orders_map = load_key_orders()
    changed = False

    for k in keys_data:
        k_id = str(k.get("id"))
        uid = f"{server_num}_{k_id}"
        k_name = k.get("name", "")
        raw_url = k.get("accessUrl", "")
        full_url = f"{raw_url}#{k_name}" if k_name else raw_url
        l_bytes = k.get("dataLimit", {}).get("bytes")
        ord_id = key_orders_map.get(k_name.strip().lower(), "N/A")
        
        cid_match = re.search(r'\((\d+)\)', k_name)
        cid = cid_match.group(1) if cid_match else ""

        date_match = re.search(r'\d{1,2}\.\d{1,2}\.(\d{4}|\d{2})', k_name)
        exp_date = date_match.group(0) if date_match else "မသိရှိပါ"

        registry[uid] = {
            "server": str(server_num),
            "key_id": k_id,
            "name": k_name,
            "access_url": full_url,
            "limit_bytes": l_bytes,
            "expire_date": exp_date,
            "order_id": ord_id,
            "chat_id": cid
        }
        changed = True

    if changed:
        redis_set("persistent_keys_registry", registry)
        try:
            with open(PERSISTENT_KEYS_FILE, 'w') as f:
                json.dump(registry, f)
        except:
            pass

def delete_persistent_key(server_num, key_id):
    """Remove a key from the persistent registry. Returns True if an entry was removed."""
    registry = load_persistent_keys()
    uid = f"{server_num}_{key_id}"
    removed = registry.pop(uid, None)

    if removed is None:
        # Fallback: match by key_id + server across differently-keyed entries.
        for k in list(registry.keys()):
            v = registry[k]
            if str(v.get("key_id")) == str(key_id) and str(v.get("server")) == str(server_num):
                removed = registry.pop(k)
                break

    if removed is not None:
        redis_set("persistent_keys_registry", registry)
        try:
            with open(PERSISTENT_KEYS_FILE, 'w') as f:
                json.dump(registry, f)
        except:
            pass

    return removed is not None


def sync_legacy_redis_data_to_registry():
    registry = load_persistent_keys()
    changed = False
    
    sales = load_sales_history()
    for idx, s in enumerate(sales, 1):
        s_cid = str(s.get("chat_id", ""))
        s_srv = str(s.get("server", "1"))
        s_ord = s.get("order_id", "N/A")
        p_name = s.get("plan_name", "VPN Plan")
        
        uid = f"{s_srv}_sale_{s_ord if s_ord != 'N/A' else idx}"
        if uid not in registry:
            registry[uid] = {
                "server": s_srv,
                "key_id": f"sale_{idx}",
                "name": f"{p_name} ({s_cid})" if s_cid else p_name,
                "access_url": "N/A",
                "limit_bytes": None,
                "expire_date": s.get("date", "မသိရှိပါ"),
                "order_id": s_ord,
                "chat_id": s_cid
            }
            changed = True

    orders = load_orders()
    for o_id, o_data in orders.items():
        o_cid = str(o_data.get("chat_id", ""))
        u_name = o_data.get("user_name", "Customer")
        uid = f"1_ord_{o_id}"
        if uid not in registry:
            registry[uid] = {
                "server": "1",
                "key_id": f"ord_{o_id}",
                "name": f"{u_name} ({o_cid})",
                "access_url": "N/A",
                "limit_bytes": None,
                "expire_date": o_data.get("date", "မသိရှိပါ"),
                "order_id": o_id,
                "chat_id": o_cid
            }
            changed = True

    if changed:
        redis_set("persistent_keys_registry", registry)
        try:
            with open(PERSISTENT_KEYS_FILE, 'w') as f:
                json.dump(registry, f)
        except:
            pass

# 📇 Customer Purchase History Storage Helpers
