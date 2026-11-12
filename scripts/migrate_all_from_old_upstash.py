"""Full Migration Script: Clones 100% of keys and values from Old Upstash to New Upstash."""

import json
import os
import sys
import requests

from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

OLD_URL = os.environ.get("OLD_UPSTASH_URL", "https://relaxed-coral-166624.upstash.io")
OLD_TOKEN = os.environ.get("OLD_UPSTASH_TOKEN", "")

NEW_URL = os.environ.get("UPSTASH_REDIS_REST_URL") or os.environ.get("KV_REST_API_URL") or "https://select-seasnail-127182.upstash.io"
NEW_TOKEN = os.environ.get("UPSTASH_REDIS_REST_TOKEN") or os.environ.get("KV_REST_API_TOKEN", "")

def migrate():
    if not OLD_TOKEN or not NEW_TOKEN:
        print("ERROR: OLD_UPSTASH_TOKEN and UPSTASH_REDIS_REST_TOKEN / KV_REST_API_TOKEN must be set in environment.")
        return False
    print(f"Connecting to Old Upstash: {OLD_URL}")
    r = requests.get(f"{OLD_URL}/keys/*", headers={"Authorization": f"Bearer {OLD_TOKEN}"})
    if r.status_code != 200:
        print(f"FAILED to read keys from Old Upstash: HTTP {r.status_code}")
        print(r.text)
        return False

    keys = r.json().get("result", [])
    print(f"SUCCESS: Found {len(keys)} keys in Old Upstash!")

    success_count = 0
    for raw_k in keys:
        # Key might be JSON quoted or plain string
        clean_k = raw_k.strip('"')
        
        # Read from old
        get_res = requests.get(f"{OLD_URL}/get/{clean_k}", headers={"Authorization": f"Bearer {OLD_TOKEN}"})
        if get_res.status_code != 200:
            print(f"Error fetching {clean_k}: {get_res.text}")
            continue
        
        val = get_res.json().get("result")
        if val is None:
            continue

        try:
            parsed = json.loads(val)
        except Exception:
            parsed = val

        from bot_app.storage.kv import redis_set
        ok = redis_set(clean_k, parsed)
        if ok:
            print(f"  ✓ Migrated key: {clean_k}")
            success_count += 1
        else:
            print(f"  ✗ Failed to write {clean_k}")

    print("\n==========================================")
    print(f"MIGRATION COMPLETE: {success_count}/{len(keys)} keys copied to New Upstash!")
    print("==========================================")
    return True

if __name__ == "__main__":
    migrate()
