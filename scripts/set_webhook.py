#!/usr/bin/env python3
"""Telegram webhook manager with an `allowed_updates` guard.

Background: this bot once went half-dead because the webhook had
``allowed_updates`` restricted to message-type updates only, so Telegram
silently dropped every ``callback_query`` (all inline buttons, including
Verify). This script makes that class of outage visible and fixable:

    python scripts/set_webhook.py check   # verify url + callback_query delivery
    python scripts/set_webhook.py set     # (re)set webhook with full updates
    python scripts/set_webhook.py reset   # delete + set (clears stuck filters)

Config via flags or env: TELEGRAM_TOKEN, WEBHOOK_URL.
Exit codes: 0 ok, 1 failed check / API error, 2 usage error. Token never printed.
"""

import argparse
import os
import sys

import requests

API_TIMEOUT = 20
REQUIRED_UPDATE = "callback_query"  # inline buttons die without this


def _mask(token):
    if not token or len(token) < 8:
        return "***"
    return token[:4] + "..." + token[-4:]


def api_call(token, method, params=None):
    try:
        resp = requests.get(
            f"https://api.telegram.org/bot{token}/{method}",
            params=params or {},
            timeout=API_TIMEOUT,
        )
    except requests.RequestException as exc:
        return False, f"network error calling {method}: {exc}"
    try:
        data = resp.json()
    except ValueError:
        return False, f"{method}: non-JSON response (HTTP {resp.status_code})"
    if not data.get("ok"):
        return False, f"{method}: {data.get('description', 'unknown error')}"
    return True, data.get("result")


def evaluate(info, expected_url):
    """Return (ok, issues) for a getWebhookInfo result dict."""
    issues = []
    actual_url = (info.get("url") or "").rstrip("/")
    if actual_url != expected_url.rstrip("/"):
        issues.append(f"webhook url mismatch: got '{actual_url}', want '{expected_url}'")
    allowed = info.get("allowed_updates")
    if allowed is not None and REQUIRED_UPDATE not in allowed:
        issues.append(
            f"allowed_updates={allowed} drops '{REQUIRED_UPDATE}' "
            "(inline buttons incl. Verify will NOT be delivered). "
            "Run `set` or `reset` to fix."
        )
    pending = info.get("pending_update_count") or 0
    if pending > 50:
        issues.append(f"pending_update_count={pending} (updates piling up)")
    if info.get("last_error_message"):
        issues.append(
            f"last delivery error: {info.get('last_error_message')} "
            f"(date={info.get('last_error_date')})"
        )
    return (len(issues) == 0), issues


def cmd_check(token, url):
    ok, info = api_call(token, "getWebhookInfo")
    if not ok:
        print(f"FAIL: {info}")
        return 1
    good, issues = evaluate(info if isinstance(info, dict) else {}, url)
    print(f"url: {info.get('url')}")
    print(f"allowed_updates: {info.get('allowed_updates', '<absent = ALL updates>')}")
    print(f"pending: {info.get('pending_update_count')}")
    print(f"last_error: {info.get('last_error_message')}")
    if good:
        print(f"OK: webhook delivers '{REQUIRED_UPDATE}'")
        return 0
    for issue in issues:
        print(f"FAIL: {issue}")
    return 1


def cmd_set(token, url):
    # allowed_updates=[] means Telegram default = all update types.
    ok, result = api_call(token, "setWebhook",
                          {"url": url, "allowed_updates": "[]"})
    if not ok:
        print(f"FAIL: {result}")
        return 1
    print(f"setWebhook accepted ({result}); verifying...")
    return cmd_check(token, url)


def cmd_reset(token, url, drop_pending=False):
    ok, result = api_call(token, "deleteWebhook",
                          {"drop_pending_updates": drop_pending})
    if not ok:
        print(f"FAIL: {result}")
        return 1
    print("webhook deleted; setting fresh...")
    return cmd_set(token, url)


def build_parser():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=["check", "set", "reset"],
                        nargs="?", default="check")
    parser.add_argument("--url", default=os.environ.get("WEBHOOK_URL", ""),
                        help="public webhook URL (or $WEBHOOK_URL)")
    parser.add_argument("--token", default=os.environ.get("TELEGRAM_TOKEN", ""),
                        help="bot token (or $TELEGRAM_TOKEN)")
    parser.add_argument("--drop-pending", action="store_true",
                        help="with reset: also drop queued updates")
    return parser


def main(argv=None):
    args = build_parser().parse_args(argv)
    if not args.token or ":" not in args.token:
        print("FAIL: provide --token or $TELEGRAM_TOKEN", file=sys.stderr)
        return 2
    if not args.url.startswith("https://"):
        print("FAIL: provide --url https://... or $WEBHOOK_URL", file=sys.stderr)
        return 2
    print(f"token: {_mask(args.token)}  action: {args.action}")
    if args.action == "check":
        return cmd_check(args.token, args.url)
    if args.action == "set":
        return cmd_set(args.token, args.url)
    return cmd_reset(args.token, args.url, args.drop_pending)


if __name__ == "__main__":
    sys.exit(main())
