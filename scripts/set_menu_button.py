#!/usr/bin/env python3
"""CLI utility to view and set Telegram Bot Chat Menu Button."""

import argparse
import os
import sys
import requests
from dotenv import load_dotenv

load_dotenv()

TOKEN = os.environ.get("TELEGRAM_TOKEN", "").strip()
MINI_APP_URL = os.environ.get("MINI_APP_URL", "https://outline.htetmyat.site/app/").strip()
MENU_BUTTON_TEXT = os.environ.get("MENU_BUTTON_TEXT", "Open App").strip()


def check_menu_button(token, chat_id=None):
    url = f"https://api.telegram.org/bot{token}/getChatMenuButton"
    payload = {"chat_id": chat_id} if chat_id else {}
    resp = requests.post(url, json=payload, timeout=15).json()
    return resp


def set_menu_button(token, text, web_app_url, chat_id=None):
    url = f"https://api.telegram.org/bot{token}/setChatMenuButton"
    payload = {
        "menu_button": {
            "type": "web_app",
            "text": text,
            "web_app": {"url": web_app_url},
        }
    }
    if chat_id:
        payload["chat_id"] = chat_id
    resp = requests.post(url, json=payload, timeout=15).json()
    return resp


def main():
    parser = argparse.ArgumentParser(description="Manage Telegram Bot Menu Button")
    subparsers = parser.add_subparsers(dest="action", required=True)

    # Check
    check_p = subparsers.add_parser("check", help="View current menu button")
    check_p.add_argument("--chat-id", type=int, default=None, help="Specific chat ID (optional)")

    # Set
    set_p = subparsers.add_parser("set", help="Set menu button")
    set_p.add_argument("--text", default=MENU_BUTTON_TEXT, help="Button label (default: Open App)")
    set_p.add_argument("--url", default=MINI_APP_URL, help="Mini App HTTPS URL")
    set_p.add_argument("--chat-id", type=int, default=None, help="Specific chat ID (optional)")

    args = parser.parse_args()

    if not TOKEN or TOKEN.startswith("00000"):
        print("❌ Error: TELEGRAM_TOKEN not configured in .env")
        sys.exit(1)

    if args.action == "check":
        res = check_menu_button(TOKEN, args.chat_id)
        target = f"Chat {args.chat_id}" if args.chat_id else "Global Default (All chats)"
        print(f"🔍 Current Menu Button for [{target}]:")
        print(res.get("result", res))

    elif args.action == "set":
        # 1. Set for specific chat if provided
        if args.chat_id:
            res = set_menu_button(TOKEN, args.text, args.url, args.chat_id)
            print(f"✅ Set for Chat {args.chat_id}: {res}")
        else:
            # Set globally as default for ALL users
            res_global = set_menu_button(TOKEN, args.text, args.url)
            print(f"✅ Set Global Default for ALL users: {res_global}")
            # Also set for admin chat if present in env
            admin_id = os.environ.get("DEV_CUSTOMER_ID") or os.environ.get("ADMIN_CHAT_IDS", "").split(",")[0].strip()
            if admin_id and admin_id.isdigit():
                res_admin = set_menu_button(TOKEN, args.text, args.url, int(admin_id))
                print(f"✅ Set for Admin ({admin_id}): {res_admin}")


if __name__ == "__main__":
    main()
