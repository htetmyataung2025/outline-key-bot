"""Disaster Recovery Script: Restore Customers, Key Mappings, and Profiles from Outline Servers to Upstash Redis."""

import os
import re
import sys
import requests
import urllib3
urllib3.disable_warnings()

from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from dotenv import load_dotenv
load_dotenv(".env", override=True)

from bot_app.storage.kv import redis_set, redis_get, _kv_config
from bot_app.services.orders import load_all_users, load_key_mappings, load_user_plans
from bot_app.services.registry import load_persistent_keys

def run_restore():
    url, token = _kv_config()
    print(f"Target Upstash Redis: {url}")
    if not url or not token:
        print("ERROR: No KV credentials configured in .env!")
        return

    # Load configured Outline servers
    u1 = os.environ.get("OUTLINE_API_URL_1")
    u2 = os.environ.get("OUTLINE_API_URL_2")
    servers = [(1, u1), (2, u2)]

    all_users = set(load_all_users() or [])
    key_mappings = load_key_mappings() or {}
    user_plans = load_user_plans() or {}
    persistent_keys = load_persistent_keys() or {}
    user_profiles = redis_get("user_profiles") or {}

    total_keys_processed = 0

    for s_idx, api_url in servers:
        if not api_url:
            continue
        print(f"\n--- Scanning Outline Server {s_idx} ({api_url.split('@')[-1] if '@' in api_url else api_url[:30]}...) ---")
        try:
            r = requests.get(f"{api_url}/access-keys", verify=False, timeout=8)
            if r.status_code != 200:
                print(f"Server {s_idx} returned HTTP {r.status_code}")
                continue
            keys = r.json().get("accessKeys", [])
            print(f"Found {len(keys)} keys on Server {s_idx}.")
            total_keys_processed += len(keys)

            for k in keys:
                kid = str(k.get("id"))
                name = k.get("name") or ""
                access_url = k.get("accessUrl") or ""
                limit_b = k.get("dataLimit", {}).get("bytes")

                # Extract chat_id from (12345678)
                cid_match = re.search(r'\((\d{6,15})\)', name)
                cid = cid_match.group(1) if cid_match else ""

                # Extract expiry date DD.MM.YYYY
                date_match = re.search(r'\d{1,2}\.\d{1,2}\.(\d{4}|\d{2})', name)
                exp_date = date_match.group(0) if date_match else "မသိရှိပါ"

                # Clean label
                clean_name = re.sub(r'\(\s*\d+\s*\)', '', name)
                clean_name = re.sub(r'\d{1,2}\.\d{1,2}\.(\d{4}|\d{2})', '', clean_name).strip(' -–—·|')

                uid = f"{s_idx}_{kid}"
                persistent_keys[uid] = {
                    "server": str(s_idx),
                    "key_id": kid,
                    "name": name,
                    "access_url": f"{access_url}#{name}" if name else access_url,
                    "limit_bytes": limit_b,
                    "expire_date": exp_date,
                    "order_id": "N/A",
                    "chat_id": cid
                }

                if name:
                    key_mappings[name.strip().lower()] = cid

                if cid:
                    all_users.add(str(cid))
                    if str(cid) not in user_profiles:
                        user_profiles[str(cid)] = {
                            "chat_id": int(cid),
                            "name": clean_name or f"User {cid}",
                            "username": "",
                            "first_seen": "2026-10-18 00:00:00",
                            "last_seen": "2026-10-18 00:00:00"
                        }
                    user_plans[str(cid)] = {
                        "plan_name": "Active Key",
                        "server": str(s_idx),
                        "key_id": kid,
                        "access_url": access_url,
                        "expiry": exp_date
                    }
        except Exception as e:
            print(f"Server {s_idx} connection error: {e}")

    # Write to Upstash Redis
    all_users_list = sorted(list(all_users))
    print("\n--- Restoring Data into Upstash Redis ---")
    print(f"Total Unique Customers: {len(all_users_list)}")
    print(f"Total Persistent Keys: {len(persistent_keys)}")
    print(f"Total User Profiles: {len(user_profiles)}")
    print(f"Total Key Mappings: {len(key_mappings)}")
    print(f"Total User Plans: {len(user_plans)}")

    redis_set("all_users", all_users_list)
    redis_set("user_profiles", user_profiles)
    redis_set("persistent_keys_registry", persistent_keys)
    redis_set("key_mappings", key_mappings)
    redis_set("user_plans", user_plans)

    # Initialize points_data and user_wallets_data if empty
    existing_points = redis_get("points_data")
    if not existing_points:
        # Initialize default structure for each user with 0 points
        points_map = {}
        for uid in all_users_list:
            points_map[uid] = {
                "points": 0,
                "streak": 0,
                "last_claim_at": None,
                "highest_streak": 0,
                "lifetime_claims": 0,
                "reminder_sent": False
            }
        redis_set("points_data", points_map)
        print("Initialized points_data for all customers (ready for manual or backup balance merge).")

    existing_wallets = redis_get("user_wallets_data")
    if not existing_wallets:
        wallets_map = {uid: 0 for uid in all_users_list}
        redis_set("user_wallets_data", wallets_map)
        print("Initialized user_wallets_data for all customers.")

    existing_sales = redis_get("sales_history")
    if existing_sales is None:
        redis_set("sales_history", [])
        print("Initialized empty sales_history.")

    existing_slips = redis_get("admin_slips_data")
    if existing_slips is None:
        redis_set("admin_slips_data", [])
        print("Initialized empty admin_slips_data.")

    print("\nSUCCESS: All Outline keys and customers restored to new Upstash Redis database!")

if __name__ == "__main__":
    run_restore()
