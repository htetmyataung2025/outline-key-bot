"""Outline VPN server client: keys, usage, search, renew/create."""

import os
import re
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta

import requests
from dateutil.relativedelta import relativedelta
from bot_app.timeutil import myanmar_now
from telebot.types import InlineKeyboardButton, InlineKeyboardMarkup

from bot_app import config as _config
from bot_app.config import ADMIN_CHAT_IDS
from bot_app.services.orders import load_key_orders, map_key_to_order
from bot_app.services.registry import (load_persistent_keys, save_persistent_key,
                                 sync_keys_to_persistent_registry,
                                 sync_legacy_redis_data_to_registry)
from bot_app.utils import bytes_to_gb, clean_ss_url, extract_chat_id_from_key_name


def _is_local_sandbox() -> bool:
    return os.environ.get("LOCAL_SANDBOX") == "1"


def get_configured_servers():
    """Return the servers that are actually usable (with a non-empty API URL).

    The dynamic settings store (Settings page / Supabase) is the source of
    truth; its defaults derive from the environment (.env). Rows saved without
    an API URL — mid-edit in Settings, or legacy rows — are filtered out so
    provisioning, telemetry and the dashboard filters never see a phantom
    server that isn't configured anywhere.
    """
    if _is_local_sandbox():
        return [
            {"id": "1", "name": "Server 1 (SG-1)", "api_url": "https://sandbox.local/s1"},
            {"id": "2", "name": "Server 2 (SG-2)", "api_url": "https://sandbox.local/s2"},
        ]
    from bot_app.services.settings import get_system_settings
    configured = get_system_settings().get("servers") or []
    return [srv for srv in configured if (srv.get("api_url") or "").strip()]


def get_server_api_url(server_id):
    """Resolve the Outline API URL for a given server id, or None if not found."""
    for srv in get_configured_servers():
        if str(srv.get("id")) == str(server_id):
            return srv.get("api_url", "") or None
    return None


_LEGACY_ENV_URL_SLOTS = {"1": "OUTLINE_API_URL_1", "2": "OUTLINE_API_URL_2", "3": "OUTLINE_API_URL_3"}


def _env_server_api_url(server_id):
    """Legacy .env slot (OUTLINE_API_URL_1/2/3) for a server id, read at call
    time so monkeypatched/late-injected config values are honoured."""
    attr = _LEGACY_ENV_URL_SLOTS.get(str(server_id))
    return (getattr(_config, attr, "") or "").rstrip("/") if attr else ""


def resolve_server_api_url(server_id):
    """Authoritative API URL for a server id ('' when it resolves to nothing).

    The dynamic settings store (Settings page) is the source of truth so
    servers added there (e.g. Server 4) are honoured on every code path.
    The legacy .env slots (ids 1-3) remain a fallback for env-only setups
    and for rows saved mid-edit without a URL.
    """
    return (get_server_api_url(server_id) or "").rstrip("/") or _env_server_api_url(server_id)


def server_num_for_api_url(api_url):
    """Reverse-map an Outline API URL back to its configured server id, or None."""
    needle = (api_url or "").rstrip("/")
    if not needle:
        return None
    for srv in get_configured_servers():
        if (srv.get("api_url") or "").rstrip("/") == needle:
            return str(srv.get("id"))
    for slot_id in _LEGACY_ENV_URL_SLOTS:
        if _env_server_api_url(slot_id) == needle:
            return slot_id
    return None


def clean_server_label(name):
    """Strip decoration emojis the admin may leave in a Settings server name."""
    cleaned = (name or "").replace("📡", "").replace("🇸🇬", "").replace("🇯🇵", "").replace("🇺🇸", "").replace("⚡", "")
    return " ".join(cleaned.split())


def get_server_display_name(server_id) -> str:
    """Human-readable name for a server id ("Server 1 (SG-1)" …).

    Reads the dynamic Settings store, so renames/removals there are reflected
    everywhere this is shown. Ids missing from the store (e.g. a server that
    was later deleted but still referenced by historical sales) fall back to
    "Server <id>".
    """
    sid = str(server_id)
    for srv in get_configured_servers():
        if str(srv.get("id")) == sid:
            return clean_server_label(srv.get("name", "")) or f"Server {sid}"
    return f"Server {sid}"


# Country flag per server id — the owner's fleet: 1/2 Singapore,
# 3 Japan, 4 United States. Unknown ids get no flag rather than a
# wrong one.
_SERVER_FLAGS = {"1": "🇸🇬", "2": "🇸🇬", "3": "🇯🇵", "4": "🇺🇸"}


def server_flag(server_id) -> str:
    """Country flag for a server id ('' when the id has no known flag)."""
    return _SERVER_FLAGS.get(str(server_id), "")


def get_server_label(server_id) -> str:
    """Customer-facing server label: display name + flag ('SG-1 🇸🇬').

    The single format used across the bot, the app-facing messages and
    admin summaries (owner's format, 2026-11-24) — never a hard-coded
    'Server N 🇸🇬' that would mislabel the Japan / US servers.
    """
    name = get_server_display_name(server_id)
    flag = server_flag(server_id)
    return f"{name} {flag}" if flag else name


def iter_configured_server_urls():
    """Yield API URLs for every configured server.

    When the dynamic settings store (Settings page) has servers, those are the
    sole source of truth — env-only .env slots are NOT mixed in, because a
    server saved to Settings may point at the same host under a different path
    than its legacy OUTLINE_API_URL_* env var, producing duplicate probes.

    Only when NO server is configured via Settings do we fall back to the
    legacy .env slots (OUTLINE_API_URL_1/2/3) so env-only setups keep working.
    """
    servers = get_configured_servers()
    if servers:
        seen = set()
        for srv in servers:
            url = (srv.get("api_url") or "").rstrip("/")
            if url and url not in seen:
                seen.add(url)
                yield url
        return
    seen = set()
    for slot_id in _LEGACY_ENV_URL_SLOTS:
        url = _env_server_api_url(slot_id)
        if url and url not in seen:
            seen.add(url)
            yield url


def refresh_registry_from_servers():
    """Fetch live access-keys from every configured server (in parallel) and sync
    them into the persistent registry. Best-effort: unreachable servers are skipped."""
    configured = get_configured_servers()

    def fetch(srv):
        server_num = str(srv.get("id"))
        api_url = srv.get("api_url", "")
        if not api_url:
            return server_num, None
        try:
            resp = requests.get(f"{api_url}/access-keys", verify=False, timeout=4)
            if resp.status_code == 200:
                return server_num, resp.json().get("accessKeys", [])
        except Exception:
            pass
        return server_num, None

    with ThreadPoolExecutor(max_workers=min(8, max(1, len(configured)))) as executor:
        results = list(executor.map(fetch, configured))

    for server_num, keys in results:
        if keys:
            sync_keys_to_persistent_registry(server_num, keys)


# Per-key data usage lives in a separate Outline endpoint (/metrics/transfer),
# not in /access-keys, so the key list joins it on read. The map is fetched per
# server and cached briefly: a dashboard reload within the window reuses it
# instead of re-probing every server (the metrics call costs ~1 s each).
USAGE_CACHE_TTL = 120.0
_usage_cache = {}  # {server_id(str): {"ts": monotonic, "data": {key_id(str): bytes}}}
_usage_cache_lock = threading.Lock()


def fetch_transfer_metrics(api_url, timeout=3):
    """Return one server's ``bytesTransferredByUserId`` map ``{key_id: bytes}``.

    Empty dict on any failure (unreachable server, non-200, malformed body) so
    callers degrade gracefully — a missing usage figure is never fatal. The
    figure is Outline's *lifetime* transfer for the key; it does not reset when
    a key is extended.
    """
    if not api_url or _is_local_sandbox():
        return {}
    try:
        resp = requests.get(f"{api_url}/metrics/transfer", verify=False, timeout=timeout)
        if resp.status_code == 200:
            return resp.json().get("bytesTransferredByUserId", {}) or {}
    except Exception:
        pass
    return {}


def get_usage_by_server(server_ids=None, force=False):
    """Return ``{server_id: {key_id: bytes}}`` for the requested configured servers.

    Fetches ``/metrics/transfer`` in parallel and caches each server's map for
    ``USAGE_CACHE_TTL`` seconds. ``server_ids`` limits the probe to the servers
    actually shown on the current page; ``force`` bypasses the cache.
    Unreachable servers resolve to ``{}`` and are simply omitted from usage
    display.
    """
    if _is_local_sandbox():
        result = {}
        for k_data in load_persistent_keys().values():
            sid = str(k_data.get("server", "1"))
            kid = str(k_data.get("key_id", ""))
            used_b = k_data.get("used_bytes", 0)
            if kid and used_b:
                result.setdefault(sid, {})[kid] = int(used_b)
        return result

    configured = get_configured_servers()
    if server_ids is not None:
        wanted = {str(s) for s in server_ids}
        configured = [srv for srv in configured if str(srv.get("id")) in wanted]

    now = time.monotonic()
    result = {}
    to_fetch = []
    with _usage_cache_lock:
        for srv in configured:
            sid = str(srv.get("id"))
            cached = _usage_cache.get(sid)
            if not force and cached and now - cached["ts"] < USAGE_CACHE_TTL:
                result[sid] = cached["data"]
            else:
                to_fetch.append(srv)

    if to_fetch:
        def fetch(srv):
            return str(srv.get("id")), fetch_transfer_metrics(srv.get("api_url", ""))

        with ThreadPoolExecutor(max_workers=min(8, max(1, len(to_fetch)))) as executor:
            fetched = list(executor.map(fetch, to_fetch))
        stamp = time.monotonic()
        with _usage_cache_lock:
            for sid, data in fetched:
                _usage_cache[sid] = {"ts": stamp, "data": data}
                result[sid] = data

    return result


# Live access-key IDs per server, fetched from /access-keys and cached
# briefly like the usage map. Needed to tell "key still exists on the
# server" apart from "key was deleted on the server" — the metrics endpoint
# cannot distinguish a deleted key from one that simply has no traffic yet.
LIVE_KEYS_CACHE_TTL = 60.0
_live_keys_cache = {}  # {server_id(str): {"ts": monotonic, "data": [accessKey, ...]}}
_live_keys_cache_lock = threading.Lock()


def fetch_access_keys_detailed(api_url, timeout=4):
    """Fetch one server's live ``accessKeys`` list with an error report.

    Returns ``(keys, None)`` on success and ``(None, error)`` on failure,
    where ``error`` is a short string (exception class name or HTTP status)
    that never contains the API URL — the URL embeds a secret path.
    """
    api_url = (api_url or "").rstrip("/")
    if not api_url:
        return None, "no api_url"
    if _is_local_sandbox():
        return None, "local sandbox"
    try:
        resp = requests.get(f"{api_url}/access-keys", verify=False, timeout=timeout)
    except Exception as exc:
        return None, type(exc).__name__
    if resp.status_code != 200:
        return None, f"HTTP {resp.status_code}"
    try:
        keys = resp.json().get("accessKeys", [])
    except Exception:
        return None, "bad json"
    if not isinstance(keys, list):
        return None, "bad payload"
    return keys, None


def fetch_access_keys(api_url, timeout=4):
    """Return one server's live ``accessKeys`` list, or ``None`` on any failure.

    ``None`` (unreachable server, non-200, malformed body) is deliberately
    different from an empty list: callers must fail open on ``None`` and only
    treat a key as deleted when the server actually answered successfully.
    """
    keys, _error = fetch_access_keys_detailed(api_url, timeout=timeout)
    return keys


def get_live_keys_by_server(server_ids=None, force=False):
    """Return ``{server_id: [accessKey, ...]}`` with each server's live keys.

    Only servers whose ``/access-keys`` fetch succeeded appear in the result;
    a missing server id means "unknown — fail open", never "all keys gone".
    Results are cached for ``LIVE_KEYS_CACHE_TTL`` seconds per server;
    failed probes are not cached, so a recovered server is retried next time.
    """
    if _is_local_sandbox():
        result = {}
        for k_data in load_persistent_keys().values():
            sid = str(k_data.get("server", "1"))
            kid = str(k_data.get("key_id", ""))
            if kid:
                result.setdefault(sid, []).append(
                    {"id": kid, "accessUrl": k_data.get("access_url", "")}
                )
        return result

    configured = get_configured_servers()
    if server_ids is not None:
        wanted = {str(s) for s in server_ids}
        configured = [srv for srv in configured if str(srv.get("id")) in wanted]

    now = time.monotonic()
    result = {}
    to_fetch = []
    with _live_keys_cache_lock:
        for srv in configured:
            sid = str(srv.get("id"))
            cached = _live_keys_cache.get(sid)
            if not force and cached and now - cached["ts"] < LIVE_KEYS_CACHE_TTL:
                result[sid] = cached["data"]
            else:
                to_fetch.append(srv)

    if to_fetch:
        def fetch(srv):
            sid = str(srv.get("id"))
            # Resolve the URL exactly like every other server call (settings
            # store, trailing slash stripped, legacy env fallback) — the raw
            # stored value may carry a trailing slash or be blank mid-edit.
            api_url = resolve_server_api_url(sid) or (srv.get("api_url") or "")
            return sid, fetch_access_keys(api_url)

        with ThreadPoolExecutor(max_workers=min(8, max(1, len(to_fetch)))) as executor:
            fetched = list(executor.map(fetch, to_fetch))
        stamp = time.monotonic()
        with _live_keys_cache_lock:
            for sid, keys in fetched:
                if keys is None:
                    continue  # unreachable — stay fail-open, do not cache
                _live_keys_cache[sid] = {"ts": stamp, "data": keys}
                result[sid] = keys

    return result


def get_live_key_ids_by_server(server_ids=None, force=False):
    """Return ``{server_id: {key_id, ...}}`` of keys that exist on each server.

    Derived from :func:`get_live_keys_by_server`; same fail-open semantics —
    a server missing from the result was unreachable, not emptied.
    """
    return {
        sid: {str(k.get("id")) for k in keys
              if isinstance(k, dict) and k.get("id") is not None}
        for sid, keys in get_live_keys_by_server(server_ids, force=force).items()
    }


def probe_live_servers():
    """Diagnostic snapshot of every configured server's ``/access-keys`` probe.

    Returns ``{server_id: {"ok": bool, "count": int | None, "error": str | None}}``.
    Successful probes refresh the live-keys cache, so a following
    :func:`get_live_keys_by_server` call reuses them instead of refetching.
    Errors are short and never contain the API URL (it embeds a secret path).
    """
    if _is_local_sandbox():
        return {
            sid: {"ok": True, "count": len(keys), "error": None}
            for sid, keys in get_live_keys_by_server().items()
        }
    report = {}
    configured = get_configured_servers()
    if not configured:
        return report

    def probe(srv):
        sid = str(srv.get("id"))
        api_url = resolve_server_api_url(sid) or (srv.get("api_url") or "")
        keys, error = fetch_access_keys_detailed(api_url)
        return sid, keys, error

    with ThreadPoolExecutor(max_workers=min(8, len(configured))) as executor:
        results = list(executor.map(probe, configured))
    stamp = time.monotonic()
    with _live_keys_cache_lock:
        for sid, keys, error in results:
            if keys is None:
                report[sid] = {"ok": False, "count": None,
                               "error": error or "unreachable"}
            else:
                _live_keys_cache[sid] = {"ts": stamp, "data": keys}
                report[sid] = {"ok": True, "count": len(keys), "error": None}
    return report


def get_servers_total_usage():
    def get_server_stats(api_url):
        total_keys = 0
        total_bytes = 0

        try:
            keys_resp = requests.get(f"{api_url}/access-keys", verify=False, timeout=6)
            metrics_resp = requests.get(f"{api_url}/metrics/transfer", verify=False, timeout=6)

            if keys_resp.status_code == 200:
                keys_data = keys_resp.json().get("accessKeys", [])
                total_keys = len(keys_data)

            if metrics_resp.status_code == 200:
                bytes_dict = metrics_resp.json().get("bytesTransferredByUserId", {})
                total_bytes = sum(bytes_dict.values())
        except:
            pass

        return total_keys, total_bytes

    servers = get_configured_servers()
    per_server = []
    for srv in servers:
        sid = str(srv.get("id"))
        s_total, s_bytes = get_server_stats(srv.get("api_url", ""))
        per_server.append((sid, s_total, s_bytes))

    if not servers:
        # Legacy env-only setup: fall back to the hard .env slots.
        env_urls = list(iter_configured_server_urls())
        per_server = [(str(i + 1),) + get_server_stats(u)
                      for i, u in enumerate(env_urls)]

    report_lines = []
    overall_bytes = 0
    for sid, s_total, s_bytes in per_server:
        s_gb = bytes_to_gb(s_bytes)
        overall_bytes += s_bytes
        report_lines.append(
            f"📡 <b>{get_server_label(sid)}</b>\n🔑 Total Keys: <b>{s_total}</b>\n🧰 Total Usage: <b>{s_gb} GB</b>\n"
        )

    overall_gb = bytes_to_gb(overall_bytes)
    overall_tb = round(overall_gb / 1000, 2)

    report = (
        "📊 <b>SERVER DATA STATS REPORT</b>\n\n"
        + "\n".join(report_lines)
        + "━━━━━━━━━━━━━━━━━\n"
        f"🌟 <b>Overall Total Usage:</b> <b>{overall_gb} GB (~{overall_tb} TB)</b>"
    )
    return report

def get_customer_summary_stats():
    per_server_users = {}
    total_unique_users = set()

    for srv in get_configured_servers():
        sid = str(srv.get("id"))
        try:
            res = requests.get(f"{srv.get('api_url')}/access-keys", verify=False, timeout=4)
            if res.status_code == 200:
                keys = res.json().get("accessKeys", [])
                for k in keys:
                    k_name = k.get("name", "").strip()
                    cid_match = re.search(r'\((\d+)\)', k_name)
                    identifier = cid_match.group(1) if cid_match else k_name.lower()
                    if identifier:
                        per_server_users.setdefault(sid, set()).add(identifier)
                        total_unique_users.add(identifier)
        except Exception:
            pass

    try:
        sync_legacy_redis_data_to_registry()
    except Exception:
        pass

    persistent_registry = load_persistent_keys()
    for k_data in persistent_registry.values():
        cid = k_data.get("chat_id")
        k_name = k_data.get("name", "").strip()
        srv = str(k_data.get("server", "1"))
        identifier = cid if cid else k_name.lower()
        if identifier:
            per_server_users.setdefault(srv, set()).add(identifier)
            total_unique_users.add(identifier)

    servers = get_configured_servers()
    if servers:
        server_lines = "\n".join(
            f"📡 {get_server_label(srv.get('id'))} : <b>{len(per_server_users.get(str(srv.get('id')), set()))}</b> ယောက်\n"
            for srv in servers
        )
    else:
        server_lines = (
            f"📡 {get_server_label('1')} : <b>{len(per_server_users.get('1', set()))}</b> ယောက်\n"
            f"📡 {get_server_label('2')} : <b>{len(per_server_users.get('2', set()))}</b> ယောက်\n"
            f"📡 {get_server_label('3')} : <b>{len(per_server_users.get('3', set()))}</b> ယောက်\n"
        )

    summary_text = (
        f"👥 <b>လက်ရှိ Customer စာရင်း အကျဉ်းချုပ်</b>\n\n"
        f"{server_lines}"
        f"━━━━━━━━━━━━━━━━━\n"
        f"🌟 <b>စုစုပေါင်း Customer ဦးရေ:</b> <b>{len(total_unique_users)}</b> ယောက်\n\n"
        f"👇 ရှာဖွေလိုသော <b>Cus နာမည်အစ စာလုံး (ဥပမာ - H, T, A) သို့မဟုတ် Chat ID / Order ID</b> ကို ဒီ Chat ထဲသို့ ရိုက်ပို့ပေးပါခင်ဗျာ:"
    )
    return summary_text

def search_users_by_query(query):
    query_clean = query.strip().lower()
    markup = InlineKeyboardMarkup()
    found_matches = []
    seen_identifiers = set()
    key_orders_map = load_key_orders()

    try:
        sync_legacy_redis_data_to_registry()
    except:
        pass

    for srv in get_configured_servers():
        server_num = str(srv.get("id"))
        api_url = srv.get("api_url", "")
        try:
            res = requests.get(f"{api_url}/access-keys", verify=False, timeout=4)
            if res.status_code == 200:
                keys = res.json().get("accessKeys", [])
                sync_keys_to_persistent_registry(server_num, keys)
                for k in keys:
                    k_name = k.get("name", "").strip()
                    k_name_lower = k_name.lower()
                    assigned_ord = key_orders_map.get(k_name_lower, "").lower()
                    k_id = str(k.get("id"))
                    uid = f"{server_num}_{k_id}"

                    if len(query_clean) == 1:
                        if k_name_lower.startswith(query_clean):
                            found_matches.append((server_num, k_id, k_name))
                            seen_identifiers.add(uid)
                    else:
                        if query_clean in k_name_lower or (assigned_ord and query_clean in assigned_ord):
                            found_matches.append((server_num, k_id, k_name))
                            seen_identifiers.add(uid)
        except Exception:
            pass

    persistent_registry = load_persistent_keys()
    for uid, k_data in persistent_registry.items():
        if uid in seen_identifiers:
            continue
            
        k_name = k_data.get("name", "")
        k_name_lower = k_name.lower()
        k_ord = k_data.get("order_id", "").lower()
        srv_num = k_data.get("server", "1")
        k_id = k_data.get("key_id", "0")
        k_cid = k_data.get("chat_id", "").lower()

        if len(query_clean) == 1:
            if k_name_lower.startswith(query_clean):
                found_matches.append((srv_num, k_id, k_name))
                seen_identifiers.add(uid)
        else:
            if query_clean in k_name_lower or (k_ord and query_clean in k_ord) or (k_cid and query_clean in k_cid):
                found_matches.append((srv_num, k_id, k_name))
                seen_identifiers.add(uid)

    for server_num, key_id, k_name in found_matches[:30]:
        srv_icon = f"📡 S{server_num}{server_flag(server_num)}" if server_num != "VIP" else "⚡ VIP 🇸🇬"
        btn_text = f"{srv_icon} | {k_name}"
        markup.add(InlineKeyboardButton(btn_text, callback_data=f"viewkey_{server_num}_{key_id}"))

    return found_matches, markup

# 🔙 Back to Main Menu Callback Handler

def get_user_next_key_number(user_name, target_chat_id=None):
    max_num = 0
    found_any = False
    clean_user = user_name.strip().lower()

    persistent_registry = load_persistent_keys()
    for k_data in persistent_registry.values():
        k_name = k_data.get("name", "")
        if (target_chat_id and f"({target_chat_id})" in k_name) or (clean_user in k_name.lower()):
            found_any = True
            num_match = re.search(r'\((\d+)\)\s*\d{1,2}\.\d{1,2}\.', k_name)
            if not num_match:
                num_match = re.search(r'\((\d+)\)', k_name)

            if num_match:
                try:
                    val = int(num_match.group(1))
                    if str(val) != str(target_chat_id) and val > max_num:
                        max_num = val
                except:
                    pass

    for api_url in ([] if _is_local_sandbox() else iter_configured_server_urls()):
        try:
            res = requests.get(f"{api_url}/access-keys", verify=False, timeout=4)
            if res.status_code == 200:
                keys = res.json().get("accessKeys", [])
                for k in keys:
                    k_name = k.get("name", "")
                    if (target_chat_id and f"({target_chat_id})" in k_name) or (clean_user in k_name.lower()):
                        found_any = True
                        num_match = re.search(r'\((\d+)\)\s*\d{1,2}\.\d{1,2}\.', k_name)
                        if not num_match:
                            num_match = re.search(r'\((\d+)\)', k_name)

                        if num_match:
                            try:
                                val = int(num_match.group(1))
                                if str(val) != str(target_chat_id) and val > max_num:
                                    max_num = val
                            except:
                                pass
        except:
            pass

    if not found_any:
        return 0, 1
    elif max_num == 0:
        return 1, 2
    else:
        return max_num, max_num + 1

def get_user_ultimate_keys(chat_id, server_num="1"):
    api_url = resolve_server_api_url(server_num)
    if not api_url:
        return []
    user_keys = []
    try:
        res = requests.get(f"{api_url}/access-keys", verify=False, timeout=6)
        if res.status_code == 200:
            keys_data = res.json().get("accessKeys", [])
            for k in keys_data:
                k_name = k.get("name", "")
                extracted_cid = extract_chat_id_from_key_name(k_name)
                if (extracted_cid and str(extracted_cid) == str(chat_id)) or (f"({chat_id})" in k_name):
                    if not "[gw]" in k_name.lower():
                        user_keys.append({
                            "id": k.get("id"),
                            "name": k_name,
                            "server": str(server_num)
                        })
    except:
        pass
    return user_keys

def _parse_expiry_from_name(key_name):
    """Return the trailing ``dd.mm.yyyy`` (or ``dd.mm.yy``) expiry carried in a
    key name as a ``datetime``, or ``None`` when the name has no readable date."""
    m = re.search(r'(\d{1,2})\.(\d{1,2})\.(\d{4}|\d{2})$', (key_name or "").strip())
    if not m:
        return None
    day, month, year_str = int(m.group(1)), int(m.group(2)), m.group(3)
    year = int("20" + year_str) if len(year_str) == 2 else int(year_str)
    try:
        return datetime(year, month, day)
    except ValueError:
        return None


def _carry_over_expiry(key_name, today, months_count=1, custom_days=None):
    """Renewed expiry string, carrying over any validity the key hasn't used.

    The new term is added on top of the key's current expiry rather than
    today's date, so a customer who renews early keeps the days they already
    paid for. A key that has already lapsed — or whose name carries no readable
    date — starts fresh from today. Mirrors the carry-over rule applied by
    ``routes_admin.extend_key_endpoint``.
    """
    base = _parse_expiry_from_name(key_name)
    if base is None or base < today:
        base = today
    if custom_days:
        return (base + timedelta(days=custom_days)).strftime("%d.%m.%Y")
    return (base + relativedelta(months=months_count)).strftime("%d.%m.%Y")


def renew_specific_unlimited_key(server_num, key_id, months_count=1, custom_days=None, order_id=None):
    api_url = resolve_server_api_url(server_num)
    if not api_url:
        return None, None, None
    today = myanmar_now()
    add_bytes = (500 * months_count) * 1000**3
    
    try:
        keys_resp = requests.get(f"{api_url}/access-keys", verify=False, timeout=8)
        metrics_resp = requests.get(f"{api_url}/metrics/transfer", verify=False, timeout=8)
        
        if keys_resp.status_code == 200:
            keys_data = keys_resp.json().get("accessKeys", [])
            bytes_transferred = metrics_resp.json().get("bytesTransferredByUserId", {}) if metrics_resp.status_code == 200 else {}
            
            target_key = None
            for k in keys_data:
                if str(k.get("id")) == str(key_id):
                    target_key = k
                    break
            
            if target_key:
                target_key_name = target_key.get("name", "")
                used_bytes = bytes_transferred.get(str(key_id), 0)
                new_fup_limit = used_bytes + add_bytes
                new_expire_date = _carry_over_expiry(target_key_name, today, months_count, custom_days)

                updated_name = re.sub(r'\d{1,2}\.\d{1,2}\.(\d{4}|\d{2})$', new_expire_date, target_key_name)
                if updated_name == target_key_name:
                    updated_name = f"{target_key_name.split('(')[0].strip()} {new_expire_date}"
                
                requests.put(f"{api_url}/access-keys/{key_id}/name", data={"name": updated_name}, verify=False, timeout=8)
                requests.put(f"{api_url}/access-keys/{key_id}/data-limit", json={"limit": {"bytes": new_fup_limit}}, verify=False, timeout=8)
                
                if order_id:
                    map_key_to_order(updated_name, order_id)

                raw_access_url = target_key.get("accessUrl", "")
                final_key = f"{raw_access_url}#{updated_name}"
                save_persistent_key(server_num, key_id, updated_name, final_key, new_fup_limit, order_id)
                return final_key, updated_name, new_expire_date
    except Exception as e:
        print("Specific Unlimited Renewal Error:", e)
    return None, None, None

def renew_or_create_unlimited_key(server_num, user_name, target_chat_id, months_count=1, custom_days=None, order_id=None):
    api_url = resolve_server_api_url(server_num)
    if not api_url:
        return None, None, None, False
    today = myanmar_now()
    add_bytes = (500 * months_count) * 1000**3

    if _is_local_sandbox():
        vpn_key, key_name, expire_date = create_outline_key(
            server_num, user_name, plan_info={"bytes": add_bytes},
            target_chat_id=target_chat_id, months_count=months_count,
            custom_days=custom_days, is_giveaway=False, order_id=order_id,
        )
        return vpn_key, key_name, expire_date, False
    
    try:
        keys_resp = requests.get(f"{api_url}/access-keys", verify=False, timeout=8)
        metrics_resp = requests.get(f"{api_url}/metrics/transfer", verify=False, timeout=8)
        
        if keys_resp.status_code == 200:
            keys_data = keys_resp.json().get("accessKeys", [])
            bytes_transferred = metrics_resp.json().get("bytesTransferredByUserId", {}) if metrics_resp.status_code == 200 else {}
            
            target_key_id = None
            target_key_name = None
            target_access_url = None
            
            for k in keys_data:
                k_name = k.get("name", "")
                extracted_cid = extract_chat_id_from_key_name(k_name)
                if (extracted_cid and str(extracted_cid) == str(target_chat_id)) or (f"({target_chat_id})" in k_name):
                    if not "[gw]" in k_name.lower():
                        target_key_id = k.get("id")
                        target_key_name = k_name
                        target_access_url = k.get("accessUrl", "")
                        break
            
            if target_key_id:
                used_bytes = bytes_transferred.get(str(target_key_id), 0)
                new_fup_limit = used_bytes + add_bytes
                new_expire_date = _carry_over_expiry(target_key_name, today, months_count, custom_days)

                updated_name = re.sub(r'\d{1,2}\.\d{1,2}\.(\d{4}|\d{2})$', new_expire_date, target_key_name)
                if updated_name == target_key_name:
                    updated_name = f"{target_key_name.split('(')[0].strip()} ({target_chat_id}) {new_expire_date}"
                
                requests.put(f"{api_url}/access-keys/{target_key_id}/name", data={"name": updated_name}, verify=False, timeout=8)
                requests.put(f"{api_url}/access-keys/{target_key_id}/data-limit", json={"limit": {"bytes": new_fup_limit}}, verify=False, timeout=8)
                
                if order_id:
                    map_key_to_order(updated_name, order_id)

                raw_access_url = target_access_url
                final_key = f"{raw_access_url}#{updated_name}"
                save_persistent_key(server_num, target_key_id, updated_name, final_key, new_fup_limit, order_id, target_chat_id)
                return final_key, updated_name, new_expire_date, True
    except Exception as e:
        print("Unlimited Renewal Error:", e)

    vpn_key, key_name, expire_date = create_outline_key(server_num, user_name, plan_info={"bytes": add_bytes}, target_chat_id=target_chat_id, months_count=months_count, custom_days=custom_days, is_giveaway=False, order_id=order_id)
    return vpn_key, key_name, expire_date, False

def create_outline_key(server_num, user_name, plan_info=None, custom_gb=None, target_chat_id=None, custom_days=None, months_count=1, is_giveaway=False, custom_expire_date=None, order_id=None):
    today = myanmar_now()
    if custom_expire_date:
        expire_date = custom_expire_date
    elif custom_days:
        expire_date = (today + timedelta(days=custom_days)).strftime("%d.%m.%Y")
    else:
        expire_date = (today + relativedelta(months=months_count)).strftime("%d.%m.%Y")
    
    curr_max, next_number = get_user_next_key_number(user_name, target_chat_id)
    id_str = f" ({target_chat_id})" if target_chat_id else ""
    gw_str = " [GW]" if is_giveaway else ""
    crown_str = " 👑" if str(target_chat_id) in [str(aid) for aid in ADMIN_CHAT_IDS] else ""
    
    if curr_max == 0:
        key_name = f"{user_name}{crown_str}{id_str}{gw_str} {expire_date}"
    else:
        key_name = f"{user_name}{crown_str}{id_str}{gw_str} ({next_number}) {expire_date}"
    
    api_url = resolve_server_api_url(server_num)
    if not api_url:
        print(f"Key Generation Error: Server {server_num} is not configured — no API URL resolved.")
        return None, None, None

    if _is_local_sandbox():
        key_id = str(int(time.time() * 1000) % 100000)
        limit_bytes = None
        if custom_gb:
            limit_bytes = int(custom_gb * 1000**3)
        elif plan_info:
            limit_bytes = plan_info.get("bytes", 0) * months_count
        if order_id:
            map_key_to_order(key_name, order_id)
        final_key = f"ss://Y2hhY2hhMjA6c2FuZGJveEtleUAxMjcuMC4wLjE6MTA4MA==#{key_name}"
        save_persistent_key(server_num, key_id, key_name, final_key, limit_bytes, order_id, target_chat_id)
        return final_key, key_name, expire_date
    
    try:
        res = requests.post(f"{api_url}/access-keys", verify=False, timeout=10)
        if res.status_code in [200, 201]:
            key_data = res.json()
            key_id = key_data.get("id")
            
            requests.put(f"{api_url}/access-keys/{key_id}/name", data={"name": key_name}, verify=False, timeout=8)
            
            limit_bytes = None
            if custom_gb:
                limit_bytes = int(custom_gb * 1000**3)
            elif plan_info:
                limit_bytes = plan_info.get("bytes", 0) * months_count

            if limit_bytes and limit_bytes > 0:
                requests.put(f"{api_url}/access-keys/{key_id}/data-limit", json={"limit": {"bytes": limit_bytes}}, verify=False, timeout=8)
            
            if order_id:
                map_key_to_order(key_name, order_id)

            raw_access_url = key_data.get("accessUrl", "")
            final_key = f"{raw_access_url}#{key_name}"
            
            save_persistent_key(server_num, key_id, key_name, final_key, limit_bytes, order_id, target_chat_id)
            return final_key, key_name, expire_date
    except Exception as e:
        print("Key Generation Error:", e)
    return None, None, None

# ----------------- FORCE JOIN CHANNEL CALLBACK HANDLER -----------------

# ⚡️ Fetch Key From Server
def fetch_key_from_server(api_url, input_value):
    if not api_url or "dummyKey" in api_url:
        return None, None, None
        
    api_url = api_url.rstrip('/')
    server_num = server_num_for_api_url(api_url) or "1"
    
    try:
        keys_resp = requests.get(f"{api_url}/access-keys", verify=False, timeout=5)
        bytes_transferred = {}
        try:
            metrics_resp = requests.get(f"{api_url}/metrics/transfer", verify=False, timeout=4)
            if metrics_resp.status_code == 200:
                bytes_transferred = metrics_resp.json().get("bytesTransferredByUserId", {})
        except:
            bytes_transferred = {}
        
        if keys_resp.status_code == 200:
            keys_data = keys_resp.json().get("accessKeys", [])
            sync_keys_to_persistent_registry(server_num, keys_data)
            
            target_key = None
            input_raw = input_value.strip()

            if re.search(r'^\d+$', input_raw):
                for key in keys_data:
                    if str(key.get("id")) == input_raw:
                        target_key = key
                        break

            if not target_key and "#" in input_raw:
                raw_hash_name = input_raw.split("#")[-1].strip().lower()
                for key in keys_data:
                    k_name = key.get("name", "").strip().lower()
                    if raw_hash_name and (raw_hash_name in k_name or k_name in raw_hash_name):
                        target_key = key
                        break

            if not target_key and input_raw.startswith("ss://"):
                clean_input = input_raw.replace("ss://", "").split("?")[0].split("#")[0].strip()
                for key in keys_data:
                    server_url = key.get("accessUrl", "").replace("ss://", "").split("?")[0].split("#")[0].strip()
                    if clean_input and (clean_input in server_url or server_url in clean_input):
                        target_key = key
                        break
                    try:
                        input_secret = clean_input.split("@")[0]
                        server_secret = server_url.split("@")[0]
                        if input_secret == server_secret:
                            target_key = key
                            break
                    except:
                        pass

            if not target_key:
                for key in keys_data:
                    k_name = key.get("name", "").strip().lower()
                    if input_raw.lower() in k_name:
                        target_key = key
                        break

            if target_key:
                return target_key, bytes_transferred, server_num
    except Exception as e:
        print(f"Fetch Key Error on {api_url}:", e)
        
    persistent_registry = load_persistent_keys()
    input_raw = input_value.strip().lower()
    for uid, k_data in persistent_registry.items():
        if k_data.get("server") == server_num:
            k_name = k_data.get("name", "").lower()
            acc_url = k_data.get("access_url", "").lower()
            if (input_raw.startswith("ss://") and clean_ss_url(input_raw) in clean_ss_url(acc_url)) or (input_raw in k_name):
                dummy_key = {
                    "id": k_data.get("key_id"),
                    "name": k_data.get("name"),
                    "accessUrl": k_data.get("access_url", "").split("#")[0],
                    "dataLimit": {"bytes": k_data.get("limit_bytes")} if k_data.get("limit_bytes") else {}
                }
                return dummy_key, {}, server_num

    return None, None, None

# 🔄 Admin Key Replacement Approval Callback Handler
