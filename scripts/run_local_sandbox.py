"""Local Sandbox Runner for Outline Key Bot & Customer Mini App.

Runs the Flask backend and Mini App locally with 100% file-based storage
(.local_sandbox/*.json, persistent across restarts) — completely bypassing
Upstash Redis, Supabase, and live Outline VPN servers so you can test every
feature offline in 0ms.

Usage:
    .venv/bin/python scripts/run_local_sandbox.py
    .venv/bin/python scripts/run_local_sandbox.py --seed
    .venv/bin/python scripts/run_local_sandbox.py --reset
    .venv/bin/python scripts/run_local_sandbox.py --empty
"""

import argparse
import json
import os
import sys
import threading
import time
from datetime import timedelta

# Ensure project root is on sys.path
ROOT_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if ROOT_DIR not in sys.path:
    sys.path.insert(0, ROOT_DIR)

# Activate Local Sandbox & Dev Auth BEFORE importing bot_app
SANDBOX_DIR = os.path.join(ROOT_DIR, ".local_sandbox")
os.makedirs(SANDBOX_DIR, exist_ok=True)
os.environ.setdefault("LOCAL_STATE_DIR", SANDBOX_DIR)
os.environ["LOCAL_SANDBOX"] = "1"
os.environ["DISABLE_REMOTE_DB"] = "1"
os.environ["DEV_MODE"] = "1"
os.environ.setdefault("DEV_CUSTOMER_ID", "8777968077")

from bot_app import app, bot  # noqa: E402
from bot_app.config import is_telegram_configured  # noqa: E402
from bot_app.helpers.webhook_guard import polling_conflict  # noqa: E402
from bot_app.storage import paths  # noqa: E402
from bot_app.timeutil import myanmar_now  # noqa: E402


ALL_SANDBOX_FILES = [
    paths.STATE_FILE,
    paths.MAPPING_FILE,
    paths.REDEEM_FILE,
    paths.USED_REDEEMERS_FILE,
    paths.SEARCH_STATE_FILE,
    paths.REDEEM_STATE_FILE,
    paths.REPLACEMENT_STATE_FILE,
    paths.SALES_FILE,
    paths.ADMIN_MSG_MAP_FILE,
    paths.REPLACEMENT_MSG_MAP_FILE,
    paths.BROADCAST_STATE_FILE,
    paths.ALL_USERS_FILE,
    paths.ORDERS_FILE,
    paths.KEY_ORDERS_FILE,
    paths.USER_HISTORY_FILE,
    paths.PERSISTENT_KEYS_FILE,
    paths.WALLET_FILE,
    paths.TOPUP_STATE_FILE,
    paths.CUSTOM_TOPUP_STATE_FILE,
    paths.EXPIRING_CREDITS_FILE,
    paths.DEDUCT_STATE_FILE,
    paths.RENEW_CHOICE_STATE_FILE,
    paths.MANUAL_DISPATCH_STATE_FILE,
    paths.SLIPS_FILE,
    paths.AUDIT_LOGS_FILE,
    paths.DATA_VERSION_FILE,
    paths.USER_PROFILES_FILE,
    paths.POINTS_FILE,
    paths.SETTINGS_FILE,
]


def clear_sandbox_files() -> None:
    """Remove all local /tmp/*.json state files."""
    for file_path in ALL_SANDBOX_FILES:
        if os.path.exists(file_path):
            try:
                os.remove(file_path)
            except OSError:
                pass


def seed_sandbox_data(uid: str) -> None:
    """Populate realistic local sample data for immediate UI testing."""
    now = myanmar_now()
    exp_30d = (now + timedelta(days=26)).strftime("%d.%m.%Y")
    exp_4d = (now + timedelta(days=4)).strftime("%d.%m.%Y")
    promo_exp = (now + timedelta(days=30)).strftime("%d/%m/%Y %I:%M %p")

    # 1. Wallet balance (15,000 Ks)
    with open(paths.WALLET_FILE, "w") as f:
        json.dump({uid: 15000}, f)

    # 2. Loyalty points (1,250 PTS, eligible for top-up gated perks)
    with open(paths.POINTS_FILE, "w") as f:
        json.dump({
            uid: {
                "points": 1250,
                "streak": 3,
                "last_claim_ts": 0,
                "has_topped_up": True,
                "history": [
                    {"ts": int(now.timestamp()) - 3600, "delta": 1250, "reason": "topup"},
                ],
            },
            "900001": {
                "points": 3400,
                "streak": 6,
                "last_claim_ts": 0,
                "has_topped_up": True,
                "history": [
                    {"ts": int(now.timestamp()) - 7200, "delta": 3400, "reason": "topup"},
                ],
            },
            "900002": {
                "points": 2100,
                "streak": 4,
                "last_claim_ts": 0,
                "has_topped_up": True,
                "history": [
                    {"ts": int(now.timestamp()) - 5400, "delta": 2100, "reason": "topup"},
                ],
            },
        }, f)

    # 3. User profiles
    with open(paths.USER_PROFILES_FILE, "w") as f:
        json.dump({
            uid: {"first_name": "Ryan", "last_name": "Wez", "username": "ryan_wez"},
            "900001": {"first_name": "Aung", "last_name": "Ko", "username": "aungko"},
            "900002": {"first_name": "Su", "last_name": "Myat", "username": "sumyat"},
        }, f)

    # 4. Persistent keys with simulated usage
    key1_url = f"ss://Y2hhY2hhMjA6c2FuZGJveEtleTFAMTI3LjAuMC4xOjEwODA=#Ryan Wez ({uid}) {exp_30d}"
    key2_url = f"ss://Y2hhY2hhMjA6c2FuZGJveEtleTJAMTI3LjAuMC4xOjEwODA=#Ryan Wez ({uid}) (2) {exp_4d}"
    with open(paths.PERSISTENT_KEYS_FILE, "w") as f:
        json.dump({
            "1_101": {
                "server": "1",
                "key_id": "101",
                "name": f"Ryan Wez ({uid}) {exp_30d}",
                "access_url": key1_url,
                "limit_bytes": int(150 * 1000**3),
                "used_bytes": int(42.5 * 1000**3),
                "order_id": "#SBX101",
                "chat_id": uid,
                "expire_date": exp_30d,
            },
            "2_102": {
                "server": "2",
                "key_id": "102",
                "name": f"Ryan Wez ({uid}) (2) {exp_4d}",
                "access_url": key2_url,
                "limit_bytes": int(50 * 1000**3),
                "used_bytes": int(38.2 * 1000**3),
                "order_id": "#SBX102",
                "chat_id": uid,
                "expire_date": exp_4d,
            },
        }, f)

    # 5. Purchase history
    with open(paths.USER_HISTORY_FILE, "w") as f:
        json.dump({
            uid: [
                {
                    "timestamp": (now - timedelta(days=26)).strftime("%d/%m/%Y (%I:%M %p)"),
                    "order_id": "#SBX102",
                    "plan_name": "Basic Plan",
                    "disp_gb": "50 GB",
                    "months": 1,
                    "price_str": "2,000 Ks",
                    "server": "2",
                    "expire_date": exp_4d,
                    "vpn_key": key2_url,
                    "key_id": "102",
                },
                {
                    "timestamp": (now - timedelta(days=4)).strftime("%d/%m/%Y (%I:%M %p)"),
                    "order_id": "#SBX101",
                    "plan_name": "VIP Plan",
                    "disp_gb": "150 GB",
                    "months": 1,
                    "price_str": "5,000 Ks",
                    "server": "1",
                    "expire_date": exp_30d,
                    "vpn_key": key1_url,
                    "key_id": "101",
                },
            ]
        }, f)

    # 6. Sample payment slips
    with open(paths.SLIPS_FILE, "w") as f:
        json.dump({
            "SLP-LOCAL1": {
                "id": "SLP-LOCAL1",
                "slip_id": "SLP-LOCAL1",
                "chat_id": uid,
                "amount": 10000,
                "method": "KBZ",
                "status": "APPROVED",
                "created_at": (now - timedelta(days=4)).strftime("%Y-%m-%d %H:%M"),
            }
        }, f)

    # 7. Sample Promo / Gift Codes
    with open(paths.REDEEM_FILE, "w") as f:
        json.dump({
            "TEST1000": {
                "amount": 1000,
                "validity_days": 3,
                "mode": "single",
                "expires_at": promo_exp,
                "created_at": now.strftime("%d/%m/%Y %I:%M %p"),
            },
            "VIP5000": {
                "amount": 5000,
                "validity_days": 7,
                "mode": "single",
                "expires_at": promo_exp,
                "created_at": now.strftime("%d/%m/%Y %I:%M %p"),
            },
        }, f)


def main() -> None:
    parser = argparse.ArgumentParser(description="Run Outline Key Bot & Mini App in Local Sandbox mode (No DB required)")
    parser.add_argument("--port", type=int, default=5000, help="Port to run the local server on (default: 5000)")
    parser.add_argument("--seed", action="store_true", help="Reset and seed sample sandbox data (15,000 Ks, 2 keys)")
    parser.add_argument("--reset", action="store_true", help="Clear local sandbox data and start from 0")
    parser.add_argument("--empty", action="store_true", help="Clear local sandbox data and start from 0")
    parser.add_argument("--no-bot", action="store_true", help="Skip Telegram bot polling thread")
    args = parser.parse_args()

    uid = str(os.environ.get("DEV_CUSTOMER_ID", "8777968077"))

    if args.seed:
        clear_sandbox_files()
        seed_sandbox_data(uid)
        print("🌱 Seeded local sandbox sample data in .local_sandbox/*.json:")
        print(f"   • Customer ID : {uid} (Ryan Wez)")
        print("   • Wallet      : 15,000 Ks")
        print("   • Points      : 1,250 PTS")
        print("   • Active Keys : 2 keys (Server 1 VIP 150GB & Server 2 Basic 50GB)")
        print("   • Promo Codes : TEST1000 (+1,000 Ks), VIP5000 (+5,000 Ks)")
    elif args.empty or args.reset:
        clear_sandbox_files()
        print("🧹 Local sandbox cleared (starting fresh from 0 in .local_sandbox/*.json).")
    else:
        print("💾 Using persistent local sandbox state in .local_sandbox/*.json (starts at 0 when empty).")

    if not args.no_bot and is_telegram_configured():
        allowed, active_url = polling_conflict(bot, allow_remove=False)
        if allowed:
            def _sandbox_polling():
                while True:
                    try:
                        bot.infinity_polling(skip_pending=False, timeout=30)
                    except Exception as exc:
                        print(f"⚠️ Sandbox bot polling error: {exc}", flush=True)
                    time.sleep(3)

            threading.Thread(target=_sandbox_polling, daemon=True).start()
            print("🤖 Telegram Bot Polling active (Approve/Reject inline buttons ready).")
        else:
            print(f"⚠️ Telegram Bot Polling skipped — active webhook detected: {active_url}")

    print("\n🚀 Local Sandbox Mode (Database-Free) is running!")
    print(f"👉 Built Mini App URL : http://127.0.0.1:{args.port}/app/")
    print("👉 Vite Dev URL       : http://localhost:3000/ (if running 'npm --prefix mini_app run dev')")
    print("   (Press Ctrl+C to stop)\n")
    app.run(host="0.0.0.0", port=args.port, debug=False)


if __name__ == "__main__":
    main()

