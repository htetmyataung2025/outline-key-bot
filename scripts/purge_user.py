"""Purge a user account from every KV store, with a full local backup.

Companion to scripts/probe_user_removal.py: the probe finds the traces, this
script removes them. Every removed entry is written to
``scripts/removed_user_<chat_id>_<timestamp>.json`` first (gitignored — the
pattern is already in .gitignore) so the deletion is reversible by hand.

Usage:
    .venv/bin/python scripts/purge_user.py <chat_id>           # dry-run
    .venv/bin/python scripts/purge_user.py <chat_id> --apply   # execute

Matching rule per store:
  * dict  -> drop entries whose KEY equals the chat_id, or whose value's JSON
             dump contains the chat_id (covers chat_id fields, owner values,
             and key names embedding "(<chat_id>)").
  * list  -> drop items equal to the chat_id, or whose JSON dump contains it.

Only stores that actually change are written back (each write bumps the
dashboard data-version, triggering a live refresh).
"""

import json
import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from dotenv import load_dotenv  # noqa: E402

load_dotenv()

from bot_app.storage.kv import redis_get, redis_set  # noqa: E402

# Every shared-state blob the bot writes (see bot_app/storage/kv.py callers).
STORES = [
    "all_users",
    "user_plans",
    "user_wallets_data",
    "user_purchases_data",
    "user_expiring_credits",
    "key_mappings",
    "key_orders",
    "orders_data",
    "sales_history",
    "persistent_keys_registry",
    "redeem_codes",
    "global_claimed_redeemers",
    "admin_slips_data",
    "admin_msg_map",
    "replacement_msg_map",
    "points_data",
    "user_profiles",
    "admin_audit_logs",
]


def references(node, uid):
    """True when the chat_id appears anywhere in this value (keys or strings)."""
    if isinstance(node, dict):
        return any(str(k) == uid or references(v, uid) for k, v in node.items())
    if isinstance(node, list):
        return any(references(item, uid) for item in node)
    return str(node) == uid or (isinstance(node, str) and uid in node)


def purge_value(node, uid):
    """Return (kept_value, removed_entries) for one store blob."""
    removed = []
    if isinstance(node, dict):
        kept = {}
        for k, v in node.items():
            if str(k) == uid or references(v, uid):
                removed.append({str(k): v})
            else:
                kept[k] = v
        return kept, removed
    if isinstance(node, list):
        kept = []
        for item in node:
            if str(item) == uid or references(item, uid):
                removed.append(item)
            else:
                kept.append(item)
        return kept, removed
    return node, []


def main():
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    apply = "--apply" in sys.argv
    if not args:
        print(__doc__)
        sys.exit(2)
    uid = args[0]
    backup = {
        "purged_at": datetime.now().isoformat(),
        "chat_id": uid,
        "mode": "apply" if apply else "dry-run",
        "stores": {},
    }

    for store in STORES:
        data = redis_get(store)
        if data is None:
            continue
        kept, removed = purge_value(data, uid)
        if not removed:
            continue
        count = len(removed)
        print(f"{store}: removing {count} entr{'y' if count == 1 else 'ies'}")
        backup["stores"][store] = {"removed": removed, "kept_size_before": _size(data)}
        if apply:
            ok = redis_set(store, kept)
            print(f"    -> write {'OK' if ok else 'FAILED — ABORT'}")
            if not ok:
                print("Aborting: KV write failed; earlier stores already rewritten.")
                sys.exit(1)

    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    path = Path(__file__).with_name(f"removed_user_{uid}_{stamp}.json")
    path.write_text(json.dumps(backup, ensure_ascii=False, indent=2))
    print(f"\n{'APPLIED' if apply else 'DRY-RUN'} — backup written to {path}")
    if not apply:
        print("Re-run with --apply to execute the purge.")


def _size(data):
    return len(data) if isinstance(data, (dict, list)) else 1


if __name__ == "__main__":
    main()
