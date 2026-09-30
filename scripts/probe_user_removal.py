"""Read-only probe: find every trace of a chat_id across all KV stores.

Usage: .venv/bin/python scripts/probe_user_removal.py <chat_id>
"""

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from dotenv import load_dotenv  # noqa: E402

load_dotenv()

from bot_app.storage.kv import redis_get  # noqa: E402

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
]


def find_paths(node, needle, path="$"):
    """Yield (json_path, container_repr) for every place needle appears."""
    hits = []
    if isinstance(node, dict):
        for k, v in node.items():
            if str(k) == needle:
                hits.append((f"{path}.{k}", json.dumps(v, ensure_ascii=False)[:200]))
            hits.extend(find_paths(v, needle, f"{path}.{k}"))
    elif isinstance(node, list):
        for i, v in enumerate(node):
            hits.extend(find_paths(v, needle, f"{path}[{i}]"))
    elif isinstance(node, str) and needle in node and path != "$":
        hits.append((path, repr(node)[:200]))
    return hits


def main():
    chat_id = sys.argv[1] if len(sys.argv) > 1 else "7672856636"
    for store in STORES:
        data = redis_get(store)
        if data is None:
            print(f"{store}: <empty/absent>")
            continue
        hits = find_paths(data, chat_id)
        size = len(data) if isinstance(data, (dict, list)) else 1
        print(f"{store}: {size} entries, {len(hits)} hits")
        for p, v in hits[:20]:
            print(f"    {p} = {v}")
        if len(hits) > 20:
            print(f"    ... +{len(hits) - 20} more")


if __name__ == "__main__":
    main()
