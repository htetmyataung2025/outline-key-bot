"""Google Sheets backup: a one-way mirror of the bot's records.

The live stores stay exactly where they are (Upstash Redis for wallets,
history, points and the keys registry; Supabase for settings) — this
service periodically copies them into a Google Sheet the owner controls,
so there is always a human-readable backup if a free-tier account is ever
lost. Nothing ever reads the Sheet back into the bot.

Configuration (Vercel env) — either transport enables the backup:

Apps Script (preferred; new Google Cloud projects block service-account
key creation by default policy, so this is the path that works there):
- ``GOOGLE_SHEETS_BACKUP_SCRIPT_URL``: URL of the web app deployed from
  ``docs/sheets_backup_webapp.gs`` inside the backup spreadsheet.
- ``GOOGLE_SHEETS_BACKUP_SCRIPT_SECRET``: shared secret matching the
  script's ``SECRET`` constant.

Service account (classic):
- ``GOOGLE_SHEETS_BACKUP_ID``: the spreadsheet id (from its URL).
- ``GOOGLE_SERVICE_ACCOUNT_JSON``: the full JSON key of a Google service
  account that the spreadsheet has been shared with as Editor.

Runs daily from the Vercel cron branch (see ``maybe_run_daily_backup``),
on demand from the admin API (``POST /api/admin/backup/sheets``) and from
the admin-only Telegram ``/backup`` command. Unconfigured = silently off.

Safety notes:
- Server API URLs are NEVER written (they embed the Outline management
  secret); the Servers tab only records whether one is configured.
- Key access URLs ARE written — they are the product being backed up —
  so the spreadsheet must stay private to the owner.
"""

import json
import os
import time
import urllib.parse
from datetime import datetime

import requests

from bot_app.storage.kv import redis_get, redis_set
from bot_app.timeutil import myanmar_now

LAST_BACKUP_KEY = "sheets_backup:last"
_API_BASE = "https://sheets.googleapis.com/v4/spreadsheets"
_SCOPES = ["https://www.googleapis.com/auth/spreadsheets"]
_WRITE_CHUNK_ROWS = 1500

TAB_INFO = "Backup Info"
TAB_USERS = "Users"
TAB_PURCHASES = "Purchases"
TAB_TOPUPS = "Topups"
TAB_KEYS = "Keys"
TAB_PLANS = "Plans"
TAB_SERVERS = "Servers"
ALL_TABS = [TAB_INFO, TAB_USERS, TAB_PURCHASES, TAB_TOPUPS, TAB_KEYS,
            TAB_PLANS, TAB_SERVERS]


# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

def _spreadsheet_id() -> str:
    return (os.environ.get("GOOGLE_SHEETS_BACKUP_ID") or "").strip()


def _service_account_info():
    raw = (os.environ.get("GOOGLE_SERVICE_ACCOUNT_JSON") or "").strip()
    if not raw:
        return None
    try:
        info = json.loads(raw)
    except Exception:
        return None
    return info if isinstance(info, dict) and info.get("client_email") else None


def _script_url() -> str:
    return (os.environ.get("GOOGLE_SHEETS_BACKUP_SCRIPT_URL") or "").strip()


def _script_secret() -> str:
    return (os.environ.get("GOOGLE_SHEETS_BACKUP_SCRIPT_SECRET") or "").strip()


def _transport():
    """Which delivery path the env configures, if any."""
    if _script_url() and _script_secret():
        return "apps_script"
    if _spreadsheet_id() and _service_account_info():
        return "service_account"
    return None


def is_configured() -> bool:
    return _transport() is not None


def backup_status() -> dict:
    return {
        "configured": is_configured(),
        "transport": _transport(),
        "spreadsheet_id": _spreadsheet_id() or None,
        "last": redis_get(LAST_BACKUP_KEY),
    }


# ---------------------------------------------------------------------------
# Sheets REST client (thin wrapper; google-auth only builds the token)
# ---------------------------------------------------------------------------

class SheetsClient:
    def __init__(self, spreadsheet_id: str, credentials):
        self.spreadsheet_id = spreadsheet_id
        self._credentials = credentials

    def _headers(self) -> dict:
        from google.auth.transport.requests import Request as AuthRequest

        creds = self._credentials
        if not creds.valid:
            creds.refresh(AuthRequest())
        return {"Authorization": f"Bearer {creds.token}",
                "Content-Type": "application/json"}

    def _url(self, suffix: str) -> str:
        return f"{_API_BASE}/{self.spreadsheet_id}{suffix}"

    def list_tabs(self) -> list:
        resp = requests.get(self._url(""), headers=self._headers(), timeout=30)
        resp.raise_for_status()
        return [s.get("properties", {}).get("title", "")
                for s in resp.json().get("sheets", [])]

    def ensure_tabs(self, titles) -> None:
        existing = set(self.list_tabs())
        missing = [t for t in titles if t not in existing]
        if not missing:
            return
        body = {"requests": [{"addSheet": {"properties": {"title": t}}}
                             for t in missing]}
        resp = requests.post(self._url(":batchUpdate"),
                             headers=self._headers(), json=body, timeout=30)
        resp.raise_for_status()

    def write_tab(self, title: str, rows) -> None:
        quoted = urllib.parse.quote(f"'{title}'", safe="")
        resp = requests.post(self._url(f"/values/{quoted}:clear"),
                             headers=self._headers(), timeout=30)
        resp.raise_for_status()
        for start in range(0, max(len(rows), 1), _WRITE_CHUNK_ROWS):
            chunk = rows[start:start + _WRITE_CHUNK_ROWS]
            if not chunk:
                chunk = [[""]]
            rng = urllib.parse.quote(f"'{title}'!A{start + 1}", safe="")
            resp = requests.put(
                self._url(f"/values/{rng}?valueInputOption=RAW"),
                headers=self._headers(),
                json={"range": f"'{title}'!A{start + 1}",
                      "majorDimension": "ROWS", "values": chunk},
                timeout=60)
            resp.raise_for_status()


class AppsScriptClient:
    """Delivers every tab in ONE POST to the Apps Script web app bound to
    the backup spreadsheet (``docs/sheets_backup_webapp.gs``).

    Same interface as SheetsClient, except writes are buffered and only
    sent by ``finish()`` — the script creates/clears/writes tabs itself.
    """

    def __init__(self, url: str, secret: str):
        self._url = url
        self._secret = secret
        self._tabs = []

    def ensure_tabs(self, titles) -> None:
        pass  # the script creates missing tabs

    def write_tab(self, title: str, rows) -> None:
        self._tabs.append({"title": title, "rows": rows})

    def finish(self) -> None:
        resp = requests.post(
            self._url,
            json={"secret": self._secret, "tabs": self._tabs},
            timeout=120)
        resp.raise_for_status()
        payload = resp.json()
        if not payload.get("ok"):
            raise RuntimeError(
                f"apps script: {payload.get('error', 'unknown error')}")


def _build_client():
    if _transport() == "apps_script":
        return AppsScriptClient(_script_url(), _script_secret())
    from google.oauth2 import service_account

    info = _service_account_info()
    creds = service_account.Credentials.from_service_account_info(
        info, scopes=_SCOPES)
    return SheetsClient(_spreadsheet_id(), creds)


# ---------------------------------------------------------------------------
# Row builders (pure: live stores in, spreadsheet rows out)
# ---------------------------------------------------------------------------

def _cell(value):
    """Make a value safe for a RAW Sheets write: keep numbers numeric and
    stop text that Sheets would read as a formula."""
    if value is None:
        return ""
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return value
    text = str(value)
    if text[:1] in ("=", "@"):
        return "'" + text
    if text[:1] in ("+", "-") and len(text) > 1 and not text[1].isdigit():
        return "'" + text
    return text


def _rows(header, body):
    return [[_cell(c) for c in header]] + [[_cell(c) for c in row] for row in body]


def _users_rows():
    from bot_app.config import ADMIN_CHAT_IDS
    from bot_app.services.billing import load_all_wallets, load_expiring_credits
    from bot_app.services.orders import load_all_users
    from bot_app.services.points import load_all_points
    from bot_app.services.profiles import load_all_profiles
    from bot_app.services.slips import get_lifetime_topups_by_user

    profiles = load_all_profiles() or {}
    wallets = load_all_wallets() or {}
    points = load_all_points() or {}
    lifetime = get_lifetime_topups_by_user() or {}
    expiring = load_expiring_credits() or {}

    uids = {str(u) for u in (load_all_users() or [])}
    uids |= set(profiles) | set(wallets) | set(points) | set(lifetime)

    now = myanmar_now()

    def _bonus(uid: str) -> int:
        total = 0
        for grant in expiring.get(uid, []) or []:
            try:
                exp = datetime.strptime(grant["expire_at"], "%Y-%m-%d %H:%M:%S")
                if exp > now:
                    total += int(grant.get("remaining", 0) or 0)
            except Exception:
                continue
        return total

    def _as_int(value) -> int:
        try:
            return int(value or 0)
        except (TypeError, ValueError):
            return 0

    admins = {str(a) for a in ADMIN_CHAT_IDS}
    body = []
    for uid in sorted(uids, key=lambda x: int(x) if x.isdigit() else 0):
        profile = profiles.get(uid, {})
        main = _as_int(wallets.get(uid, 0))
        bonus = _bonus(uid)
        body.append([
            uid,
            profile.get("full_name", ""),
            profile.get("username", ""),
            main,
            bonus,
            main + bonus,
            _as_int((points.get(uid) or {}).get("points", 0)),
            _as_int(lifetime.get(uid, 0)),
            "Yes" if uid in admins else "",
        ])
    return _rows(
        ["Chat ID", "Name", "Username", "Wallet (Ks)", "Bonus (Ks)",
         "Total Balance (Ks)", "Points", "Lifetime Top-ups (Ks)", "Admin"],
        body)


def _purchases_rows():
    from bot_app.services.orders import get_purchase_history

    history = get_purchase_history(limit=100000)
    body = []
    for item in history.get("items", []):
        body.append([
            item.get("order_id", ""),
            item.get("time_str", "") or item.get("timestamp", ""),
            item.get("chat_id", ""),
            item.get("full_name", ""),
            item.get("username", ""),
            item.get("plan_name", ""),
            item.get("months", ""),
            item.get("disp_gb", ""),
            item.get("price", ""),
            item.get("server_name", "") or item.get("server", ""),
            item.get("expire_date", ""),
            item.get("kind", ""),
            item.get("vpn_key", ""),
        ])
    return _rows(
        ["Order ID", "Date", "Chat ID", "Name", "Username", "Plan", "Months",
         "Data", "Price (Ks)", "Server", "Expire Date", "Kind", "VPN Key"],
        body)


def _topups_rows():
    from bot_app.services.slips import get_slips_list

    body = []
    for slip in get_slips_list():
        body.append([
            slip.get("id", ""),
            slip.get("created_at", ""),
            slip.get("chat_id", ""),
            slip.get("username", ""),
            slip.get("amount", ""),
            slip.get("method", ""),
            slip.get("status", ""),
            slip.get("extracted_tx_id", ""),
            slip.get("reviewed_by", "") or "",
            slip.get("reviewed_at", "") or "",
        ])
    return _rows(
        ["Slip ID", "Date", "Chat ID", "Username", "Amount (Ks)", "Method",
         "Status", "Transaction ID", "Reviewed By", "Reviewed At"],
        body)


def _keys_rows():
    from bot_app.services.registry import load_persistent_keys

    registry = load_persistent_keys() or {}
    body = []
    entries = sorted(
        registry.values(),
        key=lambda e: (str(e.get("server", "")), str(e.get("name", ""))))
    for entry in entries:
        limit = entry.get("limit_bytes")
        limit_gb = ""
        if limit:
            try:
                limit_gb = round(int(limit) / 1000 ** 3, 2)
            except (TypeError, ValueError):
                limit_gb = ""
        body.append([
            entry.get("server", ""),
            entry.get("key_id", ""),
            entry.get("name", ""),
            entry.get("chat_id", ""),
            entry.get("order_id", ""),
            entry.get("expire_date", ""),
            limit_gb,
            entry.get("access_url", ""),
        ])
    return _rows(
        ["Server", "Key ID", "Name", "Chat ID", "Order ID", "Expire Date",
         "Limit (GB)", "Access URL"],
        body)


def _plans_rows():
    from bot_app.services.settings import get_system_settings

    settings = get_system_settings() or {}
    plans = settings.get("plans") or {}
    body = []
    for code, plan in plans.items():
        if not isinstance(plan, dict):
            continue
        body.append([
            code,
            plan.get("name", ""),
            plan.get("data", ""),
            plan.get("price", ""),
            plan.get("months", ""),
            "Yes" if plan.get("manual") else "",
        ])
    return _rows(["Code", "Plan", "Data", "Price (Ks)", "Months", "Manual"],
                 body)


def _servers_rows():
    from bot_app.services.settings import get_system_settings

    settings = get_system_settings() or {}
    servers = settings.get("servers") or []
    body = []
    for server in servers:
        if not isinstance(server, dict):
            continue
        body.append([
            server.get("id", ""),
            server.get("name", ""),
            # The API URL embeds the Outline management secret — never export it.
            "Yes" if server.get("api_url") else "No",
        ])
    return _rows(["Server ID", "Name", "API URL Configured"], body)


def _info_rows(counts: dict, when: datetime):
    lines = [
        ["H&E VPN — Bot Records Backup"],
        ["Last backup (Myanmar time)", when.strftime("%Y-%m-%d %H:%M:%S")],
        [],
        ["Tab", "Rows"],
    ]
    for tab in ALL_TABS[1:]:
        lines.append([tab, counts.get(tab, 0)])
    lines += [
        [],
        ["Note", "Automatic one-way backup of the bot's records "
                 "(Redis + Supabase). The bot never reads this sheet."],
        ["Warning", "The Keys tab contains live VPN access keys. "
                    "Keep this file private — do not share it."],
    ]
    return [[_cell(c) for c in row] for row in lines]


# ---------------------------------------------------------------------------
# Backup runner
# ---------------------------------------------------------------------------

def run_backup(client=None) -> dict:
    """Copy every record set into the spreadsheet.

    Never raises: returns ``{"ok": True, "counts": {...}}`` or
    ``{"ok": False, "reason": ...}`` so cron / command / API callers can
    all report the outcome the same way.
    """
    if not is_configured():
        return {"ok": False, "reason": "not_configured"}
    try:
        builders = [
            (TAB_USERS, _users_rows),
            (TAB_PURCHASES, _purchases_rows),
            (TAB_TOPUPS, _topups_rows),
            (TAB_KEYS, _keys_rows),
            (TAB_PLANS, _plans_rows),
            (TAB_SERVERS, _servers_rows),
        ]
        tabs = {title: build() for title, build in builders}

        client = client or _build_client()
        client.ensure_tabs(ALL_TABS)

        counts = {}
        for title, rows in tabs.items():
            client.write_tab(title, rows)
            counts[title] = max(0, len(rows) - 1)

        when = myanmar_now()
        client.write_tab(TAB_INFO, _info_rows(counts, when))
        finish = getattr(client, "finish", None)
        if finish is not None:
            finish()

        state = {"ts": time.time(),
                 "at": when.strftime("%Y-%m-%d %H:%M:%S"),
                 "counts": counts}
        redis_set(LAST_BACKUP_KEY, state)
        try:
            from bot_app.services.slips import record_audit_log

            record_audit_log("system", "SHEETS_BACKUP", "backup",
                             "google_sheets", {"counts": counts})
        except Exception:
            pass
        return {"ok": True, "counts": counts,
                "spreadsheet_id": _spreadsheet_id()}
    except Exception as exc:  # cron and the /backup command must never crash
        return {"ok": False,
                "reason": f"{type(exc).__name__}: {exc}"[:200]}


def maybe_run_daily_backup() -> dict:
    """Run the backup unless one succeeded in the last 20 hours.

    Called from the daily Vercel cron branch; the guard keeps cron
    retries or a manual run from rewriting the sheet twice a day.
    """
    if not is_configured():
        return {"ok": False, "reason": "not_configured"}
    last = redis_get(LAST_BACKUP_KEY) or {}
    try:
        last_ts = float(last.get("ts", 0))
    except (TypeError, ValueError):
        last_ts = 0
    if time.time() - last_ts < 20 * 3600:
        return {"ok": True, "skipped": True}
    return run_backup()
