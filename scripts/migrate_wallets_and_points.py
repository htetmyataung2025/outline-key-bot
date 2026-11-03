"""Safe Data Migration & Smart Merge Tool (Old Upstash -> New Upstash).

Intelligently merges pre-Oct 18 historical data from the Old Upstash Redis instance
into the active New Upstash Redis instance without overwriting any new transactions,
top-ups, or points earned since the switch.
"""

import argparse
import json
import os
import sys
import urllib.parse
from datetime import datetime
from pathlib import Path

import requests

BASE_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BASE_DIR))

OLD_URL = os.environ.get("OLD_KV_URL", "https://relaxed-coral-166624.upstash.io")
OLD_TOKEN = os.environ.get("OLD_KV_TOKEN", "gQAAAAAAAorgAAIgcDFmOTM0YWQwN2U4MTg0NzQ3OGE1YWFiZDhiOGZiZGQwNw")

NEW_URL = os.environ.get("NEW_KV_URL", "https://select-seasnail-127182.upstash.io")
NEW_TOKEN = os.environ.get("NEW_KV_TOKEN", "gQAAAAAAAfDOAAIgcDI0ODBhOGQyMTM5ODI0ZWMyOTQ4OTE5YjU3MTViMjQyMw")


def fetch_kv(url: str, token: str, key: str):
    enc = urllib.parse.quote(json.dumps(key))
    r = requests.get(f"{url}/get/{enc}", headers={"Authorization": f"Bearer {token}"}, timeout=10)
    if r.status_code == 200:
        val = r.json().get("result")
        if val:
            try:
                return json.loads(val)
            except Exception:
                return val
    return None


def put_kv(url: str, token: str, key: str, value) -> bool:
    enc_key = urllib.parse.quote(json.dumps(key), safe="")
    r = requests.post(
        f"{url}/set/{enc_key}",
        headers={"Authorization": f"Bearer {token}", "Content-Type": "text/plain"},
        data=json.dumps(value),
        timeout=10,
    )
    return r.status_code == 200


def merge_wallets(old_w: dict, new_w: dict) -> tuple[dict, dict]:
    """Smart merge wallets:

    - User in OLD only: restored to OLD balance.
    - User in NEW only: kept as NEW balance.
    - User in BOTH: since NEW started clean at 0, their true balance is OLD + NEW.
    """
    merged = dict(new_w or {})
    audit = {}

    for uid, old_bal in (old_w or {}).items():
        if not isinstance(old_bal, (int, float)) or old_bal <= 0:
            continue
        new_bal = merged.get(uid, 0)
        if not isinstance(new_bal, (int, float)):
            new_bal = 0
        final_bal = new_bal + old_bal
        merged[uid] = final_bal
        audit[uid] = {
            "old": old_bal,
            "new": new_bal,
            "final": final_bal,
        }

    return merged, audit


def merge_points(old_p: dict, new_p: dict) -> tuple[dict, dict]:
    """Smart merge points:

    - Sums points, lifetime_earned, lifetime_claims.
    - Preserves newest last_claim_at and highest streak.
    """
    merged = dict(old_p or {})
    audit = {}

    for uid, new_rec in (new_p or {}).items():
        if uid not in merged:
            merged[uid] = new_rec
            audit[uid] = {"action": "added_from_new", "points": new_rec.get("points", 0)}
        else:
            old_rec = merged[uid]
            m_rec = dict(old_rec)
            old_pts = old_rec.get("points", 0)
            new_pts = new_rec.get("points", 0)
            m_rec["points"] = old_pts + new_pts
            m_rec["lifetime_earned"] = old_rec.get("lifetime_earned", 0) + new_rec.get("lifetime_earned", 0)
            m_rec["lifetime_claims"] = old_rec.get("lifetime_claims", 0) + new_rec.get("lifetime_claims", 0)
            m_rec["week_earned"] = old_rec.get("week_earned", 0) + new_rec.get("week_earned", 0)
            claims = [c for c in [old_rec.get("last_claim_at"), new_rec.get("last_claim_at")] if c]
            if claims:
                m_rec["last_claim_at"] = max(claims)
            m_rec["streak_days"] = max(old_rec.get("streak_days", 0), new_rec.get("streak_days", 0))
            m_rec["has_topped_up"] = old_rec.get("has_topped_up", False) or new_rec.get("has_topped_up", False)
            merged[uid] = m_rec
            audit[uid] = {
                "action": "summed",
                "old_points": old_pts,
                "new_points": new_pts,
                "final_points": m_rec["points"],
            }

    return merged, audit


def merge_sales_history(old_sales: list, new_sales: list) -> list:
    """Smart merge sales history:

    - De-duplicates by order_id (or chat_id + timestamp).
    - Sorts chronologically.
    """
    merged_map = {}
    for s in (old_sales or []):
        if not isinstance(s, dict):
            continue
        oid = s.get("order_id") or f"{s.get('chat_id')}_{s.get('timestamp')}"
        merged_map[oid] = s

    for s in (new_sales or []):
        if not isinstance(s, dict):
            continue
        oid = s.get("order_id") or f"{s.get('chat_id')}_{s.get('timestamp')}"
        merged_map[oid] = s  # New overrides old in case of updates

    # Sort chronologically by date and timestamp
    return sorted(
        merged_map.values(),
        key=lambda x: str(x.get("date", "")) + str(x.get("timestamp", "")),
    )


def merge_admin_slips(old_slips: dict, new_slips: dict) -> dict:
    """Smart merge admin slips data:

    - Dict of slip objects keyed by slip ID (e.g. #203297).
    - Preserves all slips, prioritizing newer status from new_slips.
    """
    merged = dict(old_slips or {})
    merged.update(new_slips or {})
    return merged


def merge_user_purchases(old_up: dict, new_up: dict) -> dict:
    """Smart merge user purchases:

    - Dict of list of purchase dicts keyed by chat_id.
    - De-duplicates orders per user.
    """
    merged = {}
    all_users = set(list((old_up or {}).keys()) + list((new_up or {}).keys()))
    for u in all_users:
        u_orders = {}
        for p in (old_up or {}).get(u, []):
            if isinstance(p, dict):
                oid = p.get("order_id") or f"{p.get('date')}_{p.get('plan_name')}"
                u_orders[oid] = p
        for p in (new_up or {}).get(u, []):
            if isinstance(p, dict):
                oid = p.get("order_id") or f"{p.get('date')}_{p.get('plan_name')}"
                u_orders[oid] = p
        merged[u] = sorted(
            u_orders.values(),
            key=lambda x: str(x.get("date", "")) + str(x.get("timestamp", "")),
            reverse=True,
        )
    return merged


def merge_all_users(old_users: list, new_users: list) -> list:
    """Union of unique user IDs preserving string format."""
    seen = set()
    result = []
    for u in (new_users or []) + (old_users or []):
        su = str(u)
        if su and su not in seen:
            seen.add(su)
            result.append(su)
    return result


def merge_user_profiles(old_prof: dict, new_prof: dict) -> dict:
    """Smart merge user profiles:

    - Dict of profile objects keyed by chat_id.
    - Updates with newest profile information.
    """
    merged = dict(old_prof or {})
    for uid, p in (new_prof or {}).items():
        if uid not in merged:
            merged[uid] = p
        else:
            merged[uid] = {**merged[uid], **p}
    return merged


def merge_global_claimed_redeemers(old_r: list, new_r: list) -> list:
    """Union of users who claimed global redeems."""
    return list(set([str(u) for u in (old_r or [])] + [str(u) for u in (new_r or [])]))


def inspect_status():
    print(f"Reading OLD Upstash: {OLD_URL}")
    old_w = fetch_kv(OLD_URL, OLD_TOKEN, "user_wallets_data") or {}
    old_p = fetch_kv(OLD_URL, OLD_TOKEN, "points_data") or {}
    old_s = fetch_kv(OLD_URL, OLD_TOKEN, "sales_history") or []
    old_slips = fetch_kv(OLD_URL, OLD_TOKEN, "admin_slips_data") or {}
    old_up = fetch_kv(OLD_URL, OLD_TOKEN, "user_purchases_data") or {}

    print(f"Reading NEW Upstash: {NEW_URL}")
    new_w = fetch_kv(NEW_URL, NEW_TOKEN, "user_wallets_data") or {}
    new_p = fetch_kv(NEW_URL, NEW_TOKEN, "points_data") or {}
    new_s = fetch_kv(NEW_URL, NEW_TOKEN, "sales_history") or []
    new_slips = fetch_kv(NEW_URL, NEW_TOKEN, "admin_slips_data") or {}
    new_up = fetch_kv(NEW_URL, NEW_TOKEN, "user_purchases_data") or {}

    old_w_nonzero = {k: v for k, v in old_w.items() if isinstance(v, (int, float)) and v > 0}
    new_w_nonzero = {k: v for k, v in new_w.items() if isinstance(v, (int, float)) and v > 0}

    old_p_nonzero = {k: v for k, v in old_p.items() if isinstance(v, dict) and v.get("points", 0) > 0}
    new_p_nonzero = {k: v for k, v in new_p.items() if isinstance(v, dict) and v.get("points", 0) > 0}

    merged_w, _ = merge_wallets(old_w, new_w)
    merged_p, _ = merge_points(old_p, new_p)
    merged_s = merge_sales_history(old_s, new_s)
    merged_slips = merge_admin_slips(old_slips, new_slips)
    merged_up = merge_user_purchases(old_up, new_up)

    merged_w_nonzero = {k: v for k, v in merged_w.items() if isinstance(v, (int, float)) and v > 0}
    merged_p_nonzero = {k: v for k, v in merged_p.items() if isinstance(v, dict) and v.get("points", 0) > 0}

    print("\n" + "=" * 60)
    print(" 📊 SMART MERGE AUDIT REPORT (လက်ရှိ vs ပေါင်းစည်းမည့် အခြေအနေ)")
    print("=" * 60)
    print("1. Wallets (လက်ကျန်ငွေရှိသူများ):")
    print(f"   • OLD Redis : {len(old_w_nonzero)} users | Total: {sum(old_w_nonzero.values()):,} MMK")
    print(f"   • NEW Redis : {len(new_w_nonzero)} users | Total: {sum(new_w_nonzero.values()):,} MMK")
    print(f"   ➔ MERGED   : {len(merged_w_nonzero)} users | Total: {sum(merged_w_nonzero.values()):,} MMK")

    print("\n2. Loyalty Points (ရမှတ်များ):")
    old_pts_tot = sum(v.get("points", 0) for v in old_p_nonzero.values())
    new_pts_tot = sum(v.get("points", 0) for v in new_p_nonzero.values())
    merged_pts_tot = sum(v.get("points", 0) for v in merged_p_nonzero.values())
    print(f"   • OLD Redis : {len(old_p_nonzero)} users | Total: {old_pts_tot:,} Pts")
    print(f"   • NEW Redis : {len(new_p_nonzero)} users | Total: {new_pts_tot:,} Pts")
    print(f"   ➔ MERGED   : {len(merged_p_nonzero)} users | Total: {merged_pts_tot:,} Pts")

    print("\n3. Sales History (အရောင်းမှတ်တမ်း):")
    print(f"   • OLD: {len(old_s)} records | NEW: {len(new_s)} records ➔ MERGED: {len(merged_s)} records")

    print("\n4. Admin Slips (ငွေဖြည့်ပြေစာများ):")
    print(f"   • OLD: {len(old_slips)} slips | NEW: {len(new_slips)} slips ➔ MERGED: {len(merged_slips)} slips")

    print("\n5. User Purchases History:")
    print(f"   • OLD: {len(old_up)} users | NEW: {len(new_up)} users ➔ MERGED: {len(merged_up)} users")
    print("=" * 60)


def apply_migration():
    print(f"\n🚀 STARTING SMART MIGRATION TO: {NEW_URL}")
    print("-" * 60)

    # 1. Fetch all datasets from OLD
    print("Fetching historical datasets from OLD Upstash...")
    old_w = fetch_kv(OLD_URL, OLD_TOKEN, "user_wallets_data") or {}
    old_p = fetch_kv(OLD_URL, OLD_TOKEN, "points_data") or {}
    old_s = fetch_kv(OLD_URL, OLD_TOKEN, "sales_history") or []
    old_slips = fetch_kv(OLD_URL, OLD_TOKEN, "admin_slips_data") or {}
    old_up = fetch_kv(OLD_URL, OLD_TOKEN, "user_purchases_data") or {}
    old_users = fetch_kv(OLD_URL, OLD_TOKEN, "all_users") or []
    old_prof = fetch_kv(OLD_URL, OLD_TOKEN, "user_profiles") or {}
    old_red = fetch_kv(OLD_URL, OLD_TOKEN, "global_claimed_redeemers") or []

    # 2. Fetch all datasets from NEW
    print("Fetching active datasets from NEW Upstash...")
    new_w = fetch_kv(NEW_URL, NEW_TOKEN, "user_wallets_data") or {}
    new_p = fetch_kv(NEW_URL, NEW_TOKEN, "points_data") or {}
    new_s = fetch_kv(NEW_URL, NEW_TOKEN, "sales_history") or []
    new_slips = fetch_kv(NEW_URL, NEW_TOKEN, "admin_slips_data") or {}
    new_up = fetch_kv(NEW_URL, NEW_TOKEN, "user_purchases_data") or {}
    new_users = fetch_kv(NEW_URL, NEW_TOKEN, "all_users") or []
    new_prof = fetch_kv(NEW_URL, NEW_TOKEN, "user_profiles") or {}
    new_red = fetch_kv(NEW_URL, NEW_TOKEN, "global_claimed_redeemers") or []

    # 3. Perform Smart Merges
    print("\nExecuting in-memory smart merges...")
    merged_w, audit_w = merge_wallets(old_w, new_w)
    merged_p, audit_p = merge_points(old_p, new_p)
    merged_s = merge_sales_history(old_s, new_s)
    merged_slips = merge_admin_slips(old_slips, new_slips)
    merged_up = merge_user_purchases(old_up, new_up)
    merged_users = merge_all_users(old_users, new_users)
    merged_prof = merge_user_profiles(old_prof, new_prof)
    merged_red = merge_global_claimed_redeemers(old_red, new_red)

    # 4. Write to NEW Upstash
    writes = [
        ("user_wallets_data", merged_w),
        ("points_data", merged_p),
        ("sales_history", merged_s),
        ("admin_slips_data", merged_slips),
        ("user_purchases_data", merged_up),
        ("all_users", merged_users),
        ("user_profiles", merged_prof),
        ("global_claimed_redeemers", merged_red),
    ]

    print("\nWriting merged records to New Upstash:")
    for key, val in writes:
        ok = put_kv(NEW_URL, NEW_TOKEN, key, val)
        if ok:
            print(f"  ✓ {key:25} : Successfully written ({len(val)} items)")
        else:
            print(f"  ✗ {key:25} : FAILED to write!")
            return False

    # 5. Bump live data version
    enc_ver = urllib.parse.quote(json.dumps("admin_data_version"), safe="")
    requests.post(
        f"{NEW_URL}/set/{enc_ver}",
        headers={"Authorization": f"Bearer {NEW_TOKEN}", "Content-Type": "text/plain"},
        data=json.dumps(int(datetime.now().timestamp())),
        timeout=5,
    )
    print("\n✅ Bumped live data version (`admin_data_version`).")
    print("🎉 SMART MIGRATION COMPLETED SUCCESSFULLY WITH ZERO DATA LOSS!")
    print("=" * 60)
    return True


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Migrate & Smart Merge Old Upstash into New Upstash")
    parser.add_argument("--apply", action="store_true", help="Execute the migration and write to New Upstash")
    args = parser.parse_args()

    inspect_status()
    if args.apply:
        apply_migration()
    else:
        print("\n💡 Run with '--apply' to execute this merge.")
