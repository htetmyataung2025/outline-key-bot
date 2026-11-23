"""Public API for the H&E VPN Android app (``/api/app/*``).

Auth model — possession of the key IS the credential
----------------------------------------------------
The ``ss://`` access key itself is a bearer secret: only the customer who
bought the key holds its password. ``POST /api/app/key-detail`` therefore
needs **no Telegram login** — it looks the key up by the password inside
the submitted access key and returns *only that one key's* plan data.
No admin data, no other customers' keys and no credentials are ever
returned, and the access URL / password is never echoed back.

Data sources (live data is Upstash Redis KV, NOT Supabase — see
``bot_app/storage/kv.py`` and ``bot_app/services/registry.py``):
- ``persistent_keys_registry`` — one entry per Outline key:
  ``{server, key_id, name, access_url (full ss://), limit_bytes,
  expire_date ("DD.MM.YYYY", parsed from the key name), order_id,
  chat_id}``. The Outline key name packs ``"<label> (<chat_id>)
  DD.MM.YYYY"``.
- Per-key *lifetime* usage comes live from the Outline server
  ``/metrics/transfer`` endpoint via ``get_usage_by_server()``
  (30 s cache); an unreachable server yields ``used_bytes: null``
  rather than a fabricated 0.
- Plans come from ``bot_app.config.PLANS`` (dynamic Settings store,
  hardcoded defaults as fallback).

Rate limiting: fixed-window per client IP (Redis INCR when configured,
in-memory fallback otherwise), following ``bot_app/helpers/rate_limit.py``.
"""

import base64
import binascii
import hashlib
import hmac
import os
import re
import threading
import time
from datetime import datetime

from flask import Blueprint, Response, jsonify, request

from bot_app.config import PLANS, TELEGRAM_TOKEN
from bot_app.helpers.rate_limit import client_ip_from_headers
from bot_app.services.outline import (
    _parse_expiry_from_name,
    get_server_display_name,
    get_usage_by_server,
)
from bot_app.services.registry import clean_key_label, load_persistent_keys
from bot_app.storage.kv import (
    redis_delete,
    redis_get,
    redis_increment_with_expiry,
    redis_set,
    redis_set_nx,
)
from bot_app.timeutil import myanmar_now

app_bp = Blueprint("app_bp", __name__, url_prefix="/api/app")

# --- rate limiting (per client IP, fixed window) ---------------------------
PLANS_RATE_LIMIT = 60      # requests / minute / IP
KEY_DETAIL_RATE_LIMIT = 30  # requests / minute / IP
_RATE_WINDOW_S = 60

_memory_rl_lock = threading.Lock()
_memory_rl: dict = {}


def _rate_limited(bucket: str, limit: int) -> bool:
    """True when the caller exceeded ``limit`` requests in the window."""
    key = f"app_api_rl:{bucket}"
    count = redis_increment_with_expiry(key, _RATE_WINDOW_S)
    if count is None:
        now = time.time()
        with _memory_rl_lock:
            hits, expires_at = _memory_rl.get(key, (0, 0.0))
            if now >= expires_at:
                hits, expires_at = 0, now + _RATE_WINDOW_S
            hits += 1
            _memory_rl[key] = (hits, expires_at)
        count = hits
    return count > limit


def _client_bucket(endpoint: str) -> str:
    ip = client_ip_from_headers(request.headers)
    digest = hashlib.sha256(ip.encode("utf-8")).hexdigest()[:32]
    return f"{endpoint}:{digest}"


def _rate_limit_response():
    return jsonify({
        "error": "rate_limited",
        "message": "Too many requests — please wait a minute and try again.",
    }), 429


# --- ss:// parsing ----------------------------------------------------------
def _b64url_decode(raw: str):
    """Base64url-decode with missing padding tolerated; None on failure."""
    try:
        padded = raw + "=" * (-len(raw) % 4)
        return base64.urlsafe_b64decode(padded.encode("ascii")).decode("utf-8")
    except (binascii.Error, UnicodeDecodeError, ValueError):
        return None


def parse_ss_key(access_key: str):
    """Parse an Outline ``ss://`` access key.

    Accepts every form the Outline client produces::

        ss://<base64(method:password@host:port)>[#tag]
        ss://<base64(method:password)>@host:port[#tag]
        ss://method:password@host:port[#tag]

    Returns ``{"method", "password", "host", "port", "tag"}`` or ``None``
    when the key is not a recognisable ``ss://`` URL. The password is
    returned only so the caller can match it against the registry — it is
    never written to a response.
    """
    if not access_key or not isinstance(access_key, str):
        return None
    raw = access_key.strip()
    if not raw.startswith("ss://"):
        return None
    rest = raw[len("ss://"):]
    tag = ""
    if "#" in rest:
        rest, tag = rest.split("#", 1)
    if "?" in rest:
        rest = rest.split("?", 1)[0]
    if not rest:
        return None

    userinfo = None
    hostport = None
    if "@" in rest:
        userinfo, hostport = rest.rsplit("@", 1)
    else:
        decoded = _b64url_decode(rest)
        if decoded is None or "@" not in decoded:
            return None
        userinfo, hostport = decoded.rsplit("@", 1)

    if userinfo is None or hostport is None:
        return None
    if ":" in userinfo:
        method, password = userinfo.split(":", 1)
    else:
        decoded = _b64url_decode(userinfo)
        if decoded is None or ":" not in decoded:
            return None
        method, password = decoded.split(":", 1)
    if not password:
        return None

    host = hostport.strip()
    port = None
    if host.startswith("[") and "]" in host:  # [ipv6]:port
        host, _, tail = host[1:].partition("]")
        tail = tail.lstrip(":")
        port = int(tail) if tail.isdigit() else None
    elif ":" in host:
        host, _, tail = host.rpartition(":")
        port = int(tail) if tail.isdigit() else None
    host = host.strip().lower()
    if not host:
        return None
    return {
        "method": method or "",
        "password": password,
        "host": host,
        "port": port,
        "tag": tag,
    }


# --- registry lookup ---------------------------------------------------------
def _entry_matches_password(entry: dict, password: str, host: str | None) -> bool:
    """True when a registry entry is the key carrying ``password``.

    Registry ``access_url`` values are full ``ss://`` URLs, so the same
    parser is applied to them. Synthesised history rows (``access_url``
    ``"N/A"``) never match.
    """
    parsed = parse_ss_key(str(entry.get("access_url") or ""))
    if parsed is None:
        return False
    if parsed["password"] != password:
        return False
    if host and parsed["host"] and parsed["host"] != host:
        return False
    return True


def _find_key_by_password(password: str, host: str | None):
    for entry in load_persistent_keys().values():
        if _entry_matches_password(entry, password, host):
            return entry
    return None


def _find_key_by_owner_and_name(owner_uid: str, key_name: str):
    """Fallback lookup: owner's keys, matched by display name.

    Only used when the caller supplies ``telegram_id`` + ``key_name``
    instead of an access key (e.g. a customer who lost the link but
    remembers the plan name). Matching is on the cleaned label so the
    packed ``(chat_id)`` / expiry suffix in the raw name is ignored.
    """
    wanted = (key_name or "").strip().lower()
    if not wanted:
        return None
    for entry in load_persistent_keys().values():
        if str(entry.get("chat_id") or "").strip() != str(owner_uid).strip():
            continue
        if clean_key_label(str(entry.get("name") or "")).lower() == wanted:
            return entry
    return None


# --- plan detail assembly ------------------------------------------------------
def _parse_registry_expiry(entry: dict):
    """Expiry ``datetime`` from the registry's ``expire_date`` (DD.MM.YYYY),
    falling back to the trailing date packed in the Outline key name."""
    raw = str(entry.get("expire_date") or "").strip()
    for fmt in ("%d.%m.%Y", "%d.%m.%y"):
        try:
            return datetime.strptime(raw, fmt)
        except ValueError:
            continue
    return _parse_expiry_from_name(str(entry.get("name") or ""))


def build_key_detail(entry: dict, used_bytes):
    """Shape one registry entry (+ live usage) into the public payload.

    ``used_bytes`` may be ``None`` (Outline server unreachable) — the
    response then says so instead of pretending 0 were used.
    """
    server = str(entry.get("server") or "1")
    key_id = str(entry.get("key_id") or "")
    raw_name = str(entry.get("name") or "")
    key_name = clean_key_label(raw_name) or raw_name
    owner_uid = str(entry.get("chat_id") or "").strip() or None

    limit = entry.get("limit_bytes")
    try:
        limit = int(limit) if limit is not None else None
    except (TypeError, ValueError):
        limit = None
    if limit is not None and limit <= 0:
        limit = None  # 0 / negative = unlimited in the Outline model

    used = None
    if used_bytes is not None:
        try:
            used = max(0, int(used_bytes))
        except (TypeError, ValueError):
            used = None

    if limit is not None and used is not None:
        remaining = max(0, limit - used)
        used_percent = round(used / limit * 100, 1) if limit > 0 else None
    else:
        remaining = None
        used_percent = None

    exp_dt = _parse_registry_expiry(entry)
    now = myanmar_now()
    if exp_dt is not None:
        days_left = (exp_dt.date() - now.date()).days
        if days_left < 0:
            status = "expired"
        elif days_left <= 5:
            status = "expiring"
        else:
            status = "active"
        expires_at = exp_dt.strftime("%Y-%m-%d")
        expires_display = exp_dt.strftime("%d.%m.%Y")
    else:
        days_left = None
        status = "active"
        expires_at = None
        expires_display = str(entry.get("expire_date") or "") or None

    return {
        "key_name": key_name,
        "server_name": get_server_display_name(server),
        "server_id": server,
        "key_id": key_id,
        "owner_uid": owner_uid,
        "data_used_bytes": used,
        "data_limit_bytes": limit,
        "data_remaining_bytes": remaining,
        "used_percent": used_percent,
        "expires_at": expires_at,
        "expires_display": expires_display,
        "days_left": days_left,
        "status": status,
    }


def _live_used_bytes(server: str, key_id: str):
    """Live lifetime usage for one key from the Outline server.

    Returns ``int`` bytes, or ``None`` when the server cannot be reached
    (best-effort: a missing figure must never block the plan card).
    """
    try:
        usage = get_usage_by_server({str(server)})
        value = (usage or {}).get(str(server), {}).get(str(key_id))
        return int(value) if value is not None else None
    except Exception:
        return None


# --- endpoints ---------------------------------------------------------------
@app_bp.route("/plans", methods=["GET"])
def list_plans():
    """Public plan catalogue for the VPN app's Plans screen.

    No auth: plan names/prices are public shop information (the same data
    the customer Mini App bootstrap already serves).
    """
    if _rate_limited(_client_bucket("plans"), PLANS_RATE_LIMIT):
        return _rate_limit_response()

    plans = []
    for code, p in PLANS.items():
        months = 1
        try:
            months = int(p.get("months", 1) or 1)
        except (TypeError, ValueError):
            months = 1
        data_bytes = p.get("bytes", 0) or 0
        try:
            data_bytes = int(data_bytes)
        except (TypeError, ValueError):
            data_bytes = 0
        plans.append({
            "code": str(code),
            "name": str(p.get("name", code)),
            "data": str(p.get("data", "")),
            "data_limit_gb": (round(data_bytes / 1000 ** 3, 1)
                              if data_bytes > 0 else None),
            "valid_days": months * 30,
            "price_ks": int(p.get("price", 0) or 0),
            "manual": bool(p.get("manual", False)),
        })
    plans.sort(key=lambda item: item["price_ks"])
    return jsonify({"currency": "Ks", "plans": plans}), 200


@app_bp.route("/key-detail", methods=["POST"])
def key_detail():
    """Plan details for one key, looked up by the access key itself.

    Body (JSON)::

        {"access_key": "ss://..."}                      # preferred
        {"key_password": "<password>", "server_host": "<host>"}
        {"telegram_id": "1695353992", "key_name": "Hein Htet Oo"}

    ``telegram_id`` is optional: when supplied it MUST match the key's
    recorded owner, otherwise the request is rejected (403) — a key
    holder may not probe other customers' keys by guessing ids.
    """
    if _rate_limited(_client_bucket("key-detail"), KEY_DETAIL_RATE_LIMIT):
        return _rate_limit_response()

    data = request.get_json(silent=True) or {}
    if not isinstance(data, dict):
        return jsonify({"error": "invalid_body",
                        "message": "JSON body expected."}), 400

    telegram_id = data.get("telegram_id")
    if telegram_id is not None:
        telegram_id = str(telegram_id).strip()

    entry = None
    access_key = (data.get("access_key") or "").strip()
    key_password = (data.get("key_password") or "").strip()
    server_host = (data.get("server_host") or "").strip().lower() or None

    if access_key:
        parsed = parse_ss_key(access_key)
        if parsed is None:
            return jsonify({
                "error": "invalid_key",
                "message": "That does not look like an Outline access key (ss://...).",
            }), 400
        entry = _find_key_by_password(parsed["password"], parsed["host"])
    elif key_password:
        entry = _find_key_by_password(key_password, server_host)

    if entry is None and telegram_id and data.get("key_name"):
        entry = _find_key_by_owner_and_name(telegram_id, str(data.get("key_name")))

    if entry is None:
        if not access_key and not key_password and not (
                telegram_id and data.get("key_name")):
            return jsonify({
                "error": "invalid_body",
                "message": "Send access_key, or key_password, or "
                           "telegram_id + key_name.",
            }), 400
        return jsonify({
            "error": "key_not_found",
            "message": "No key matching that access key was found. "
                       "Check the key or contact support.",
        }), 404

    if telegram_id:
        owner = str(entry.get("chat_id") or "").strip()
        if owner and owner != telegram_id:
            return jsonify({
                "error": "forbidden",
                "message": "This key belongs to a different Telegram account.",
            }), 403

    used = _live_used_bytes(str(entry.get("server") or "1"),
                            str(entry.get("key_id") or ""))
    return jsonify(build_key_detail(entry, used)), 200


# --- app account linking + wallet / history (Phase 1) -----------------------
# The native app links a Telegram account once via a one-time deep-link
# code: the app opens https://t.me/<bot>?start=link_<code>, the bot's
# /start handler stores app_link:<code> -> {chat_id, name, username, exp}
# in Redis (10 min), and the app exchanges the code here for a long-lived
# HMAC token bound to that chat_id. Wallet / points / purchase reads are
# then served per linked account. Read-only: no money moves in Phase 1.
import hmac as _hmac
import os as _os

from bot_app.services.billing import get_user_balance_breakdown
from bot_app.services.orders import get_user_combined_purchase_records
from bot_app.services.points import get_points
from bot_app.services.profiles import get_user_profile

_LINK_CODE_RE = re.compile(r"^[A-Za-z0-9\-_]{8,64}$")
_APP_TOKEN_MAX_AGE_S = 180 * 24 * 3600  # 180 days


def _app_secret() -> str:
    return _os.environ.get("APP_API_SECRET") or TELEGRAM_TOKEN or ""


def _make_app_token(chat_id) -> str:
    payload = f"{chat_id}.{int(time.time())}"
    sig = _hmac.new(_app_secret().encode("utf-8"), payload.encode("utf-8"),
                    hashlib.sha256).hexdigest()
    return f"{payload}.{sig}"


def _verify_app_token(token):
    """chat_id for a valid app token, else None."""
    if not token or not _app_secret():
        return None
    parts = token.split(".")
    if len(parts) != 3:
        return None
    chat_id, issued, sig = parts
    payload = f"{chat_id}.{issued}"
    expect = _hmac.new(_app_secret().encode("utf-8"), payload.encode("utf-8"),
                       hashlib.sha256).hexdigest()
    if not _hmac.compare_digest(expect, sig):
        return None
    try:
        issued_i = int(issued)
    except ValueError:
        return None
    if int(time.time()) - issued_i > _APP_TOKEN_MAX_AGE_S:
        return None
    return chat_id


def _bearer_chat_id():
    auth = request.headers.get("Authorization") or ""
    if auth.startswith("Bearer "):
        chat_id = _verify_app_token(auth[len("Bearer "):].strip())
        if chat_id:
            # Bot update #17: remember which app version this customer
            # runs (header sent by the app) for the /appstats overview.
            # Best-effort telemetry — never break the request over it.
            version = (request.headers.get("X-App-Version") or "").strip()
            if version:
                try:
                    from bot_app.services import app_stats

                    app_stats.record_seen(chat_id, version)
                except Exception:
                    pass
        return chat_id
    return None


@app_bp.route("/auth/poll", methods=["POST"])
def auth_poll():
    """Exchange a link code for an app token once the bot recorded it."""
    if _rate_limited(_client_bucket("auth_poll"), 60):
        return _rate_limit_response()
    body = request.get_json(silent=True) or {}
    code = str(body.get("code") or "").strip()
    if not _LINK_CODE_RE.match(code):
        return jsonify({"status": "invalid"}), 400
    rec = redis_get(f"app_link:{code}")
    if not isinstance(rec, dict):
        return jsonify({"status": "pending"})
    if int(rec.get("exp") or 0) < int(time.time()):
        redis_delete(f"app_link:{code}")
        return jsonify({"status": "expired"})
    chat_id = str(rec.get("chat_id") or "").strip()
    if not chat_id:
        return jsonify({"status": "pending"})
    redis_delete(f"app_link:{code}")  # one-time use
    return jsonify({
        "status": "linked",
        "token": _make_app_token(chat_id),
        "telegram_id": chat_id,
        "name": rec.get("name") or "",
        "username": rec.get("username") or "",
    })


@app_bp.route("/account", methods=["GET"])
def app_account():
    """Linked account summary: wallet balances + loyalty points."""
    if _rate_limited(_client_bucket("account"), 60):
        return _rate_limit_response()
    chat_id = _bearer_chat_id()
    if not chat_id:
        return jsonify({"error": "unauthorized"}), 401
    main_bal, bonus_bal, total_bal = get_user_balance_breakdown(chat_id)
    pts = get_points(chat_id)
    try:
        profile = get_user_profile(chat_id) or {}
    except Exception:
        profile = {}
    return jsonify({
        "telegram_id": chat_id,
        "name": profile.get("full_name") or "",
        "username": profile.get("username") or "",
        "balance_main_ks": main_bal,
        "balance_bonus_ks": bonus_bal,
        "balance_total_ks": total_bal,
        "points": pts.get("points", 0),
        "points_next_claim_in_s": claim_cooldown_remaining(pts),
        "points_has_topped_up": bool(pts.get("has_topped_up")),
        "points_redeem_cost": _starter_cost(),
        "points_streak_days": pts.get("streak_days", 0),
        "points_lifetime_earned": pts.get("lifetime_earned", 0),
    })


def _starter_cost() -> int:
    try:
        from bot_app.config import points_settings
        return int(points_settings()["starter_cost"])
    except Exception:
        return 5000


@app_bp.route("/purchases", methods=["GET"])
def app_purchases():
    """Linked account's purchase history (newest first).

    Includes each purchase's own ``vpn_key``: the token proves the caller
    is the account owner, and the app's History screen lets them copy the
    key or re-add it to My Keys (e.g. after reinstalling the app).
    """
    if _rate_limited(_client_bucket("purchases"), 60):
        return _rate_limit_response()
    chat_id = _bearer_chat_id()
    if not chat_id:
        return jsonify({"error": "unauthorized"}), 401
    records = get_user_combined_purchase_records(chat_id)
    out = []
    for r in reversed(records[-50:]):
        out.append({
            "timestamp": r.get("timestamp"),
            "order_id": r.get("order_id"),
            "plan_name": r.get("plan_name"),
            "data": r.get("disp_gb"),
            "months": r.get("months"),
            "price": r.get("price_str"),
            "server": r.get("server"),
            "expire_date": r.get("expire_date"),
            "vpn_key": r.get("vpn_key"),
        })
    return jsonify({"purchases": out})


# --- app commerce (Phase 2) --------------------------------------------------
# Money-moving endpoints for the native app. Each one mirrors the exact
# service calls the Telegram bot / Mini App already use, so wallet
# semantics (bonus-credit day conversion, refund on key-creation failure,
# purchase records, audit trails) stay identical across channels:
# - POST /topup          -> same slip queue + admin Approve/Reject buttons
#                           as POST /api/user/topup-slip.
# - POST /buy            -> same purchase core as the buywallet_ callback
#                           (incl. Ultimate renew-or-new choice); the new
#                           key is returned so the app can save it at once.
# - POST /points/claim   -> services.points.try_claim (atomic, locked).
# - POST /keys/replace   -> same admin-review request as the Mini App.
# - GET  /notifications  -> services.app_notify inbox (top-up verdicts are
#                           pushed from services.slips.review_slip).
import random as _random
import string as _string

from telebot.types import InlineKeyboardButton, InlineKeyboardMarkup

from bot_app.config import ADMIN_CHAT_IDS
from bot_app.extensions import bot as _bot
from bot_app.helpers.deeplink import get_key_delivery_markup
from bot_app.services.app_notify import (
    list_app_notifications,
    mark_app_notifications_read,
    push_app_notification,
)
from bot_app.services.billing import get_user_balance, update_user_balance
from bot_app.services.orders import (
    save_key_mapping,
    save_sale_transaction,
    save_user_purchase_record,
)
from bot_app.services.outline import (
    create_outline_key,
    get_configured_servers,
    get_user_ultimate_keys,
    renew_specific_unlimited_key,
)
from bot_app.services.points import (
    claim_cooldown_remaining,
    redeem_starter,
    refund_starter,
    try_claim,
)
from bot_app.services.ocr import NOT_A_SLIP_MESSAGE, extract_amount_and_tx_from_bytes, resolve_slip_amount
from bot_app.services.slips import load_all_slips, record_slip
from bot_app.timeutil import myanmar_now as _mm_now


def _is_admin(chat_id) -> bool:
    return str(chat_id) in [str(a) for a in ADMIN_CHAT_IDS]


@app_bp.route("/topup", methods=["POST"])
def app_topup():
    """Submit a payment slip from the app into the admin review queue."""
    if _rate_limited(_client_bucket("topup"), 10):
        return _rate_limit_response()
    chat_id = _bearer_chat_id()
    if not chat_id:
        return jsonify({"error": "unauthorized"}), 401
    body = request.get_json(silent=True) or {}
    try:
        amount = int(re.sub(r"[^\d]", "", str(body.get("amount") or "0")) or 0)
    except (TypeError, ValueError):
        amount = 0
    if amount < 500:
        return jsonify({"success": False, "error": "Minimum top-up amount is 500 Ks"}), 400
    method = str(body.get("method") or "KBZ").strip().upper()[:16] or "KBZ"

    file_bytes = None
    image_b64 = body.get("image_base64")
    if isinstance(image_b64, str) and image_b64:
        try:
            file_bytes = base64.b64decode(image_b64, validate=True)
        except (binascii.Error, ValueError):
            return jsonify({"success": False, "error": "Invalid image data"}), 400
        if len(file_bytes) > 3_500_000:
            return jsonify({"success": False, "error": "Image too large (max ~3.5 MB)"}), 400

    try:
        profile = get_user_profile(chat_id) or {}
    except Exception:
        profile = {}
    username = profile.get("username") or profile.get("full_name") or "AppUser"

    # Bot Update #20: read the amount off the slip photo itself — when OCR
    # finds one it replaces the amount the customer picked in the app, so a
    # wrong selection is never what gets recorded.
    tx_ref = ""
    ocr_amount = None
    probable = True
    if file_bytes:
        tx_ref, ocr_amount, probable = extract_amount_and_tx_from_bytes(file_bytes)
    # Bot Update #21: a photo with NO sign of a payment slip is bounced
    # before it reaches the review queue, unless the caller explicitly
    # vouches for it (force_slip) — then it is recorded flagged.
    force_slip = bool(body.get("force_slip"))
    if file_bytes and not probable and not force_slip:
        return jsonify({
            "success": False,
            "error": "not_a_slip",
            "message": NOT_A_SLIP_MESSAGE,
        }), 400
    unverified = bool(file_bytes and not probable and force_slip)
    selected_amount = amount
    amount, amount_status = resolve_slip_amount(amount, ocr_amount)
    amount_note = ""
    if unverified:
        amount_note = (
            "\n⚠️ <b>စစ်ဆေးရန် လိုသည်:</b> Customer က 'ပြေစာ အစစ်ပါ' ဟု အတည်ပြု၍ ပို့လာသော slip ဖြစ်သည် — "
            "OCR ဖြင့် ပြေစာ လက္ခဏာ မတွေ့ခဲ့ပါ။ ပုံကို သေချာ စစ်ပြီးမှ Approve လုပ်ပါ။"
        )
    elif amount_status == "ocr" and ocr_amount != selected_amount:
        amount_note = (
            f"\n🤖 <b>OCR ပြင်ထည့်ထားသည်:</b> Customer ရွေးခဲ့သော {selected_amount:,} Ks → "
            f"ပြေစာပါ ပမာဏ <b>{amount:,} Ks</b>"
        )
    elif file_bytes and amount_status == "selected":
        amount_note = (
            "\n⚠️ <i>OCR ဖြင့် ပမာဏ ဖတ်မရပါ — Customer ရွေးသော ပမာဏဖြင့် မှတ်ထားသည်။ "
            "ပုံကို သေချာ စစ်ပေးပါ။</i>"
        )

    slip_id = "".join(_random.choices(_string.ascii_uppercase + _string.digits, k=8))
    if tx_ref:
        # Bot Update #20.1: like the Telegram-bot flow, prefer the id
        # derived from the slip's transaction reference so the admin can
        # match the alert to the receipt at a glance. The random id stays
        # when the derived one is already taken — a record is never
        # overwritten.
        candidate = f"#{tx_ref}"
        if candidate not in load_all_slips():
            slip_id = candidate
    admin_alert_text = (
        f"📥 <b>H&E VPN App Top-Up Slip အသစ် ရောက်ရှိပါသည်!</b>\n\n"
        f"🧾 <b>Top-Up ID:</b> <code>{slip_id}</code>\n"
        f"👤 <b>Customer:</b> @{username} (<code>{chat_id}</code>)\n"
        f"💵 <b>ပမာဏ:</b> <code>{amount:,} Ks</code>{amount_note}\n\n"
        f"<i>စစ်ဆေးပြီးပါက အောက်ပါ Approve / Reject ခလုတ်များဖြင့် သတ်မှတ်ပေးပါခင်ဗျာ။</i>"
    )
    markup = InlineKeyboardMarkup()
    markup.add(InlineKeyboardButton(
        f"✅ Approve (+{amount:,} MMK)",
        callback_data=f"approve_topup_{chat_id}_{amount}_{slip_id}"))
    markup.add(InlineKeyboardButton("❌ Reject", callback_data=f"reject_topup_{slip_id}"))

    admin_messages = []
    captured_file_id = ""
    for aid in ADMIN_CHAT_IDS:
        sent = None
        try:
            if file_bytes:
                sent = _bot.send_photo(aid, file_bytes, caption=admin_alert_text,
                                       parse_mode="HTML", reply_markup=markup)
            else:
                sent = _bot.send_message(aid, admin_alert_text,
                                         parse_mode="HTML", reply_markup=markup)
        except Exception:
            try:
                sent = _bot.send_message(aid, admin_alert_text,
                                         parse_mode="HTML", reply_markup=markup)
            except Exception:
                pass
        if sent is not None:
            admin_messages.append({"chat_id": sent.chat.id, "message_id": sent.message_id})
            if not captured_file_id and getattr(sent, "photo", None):
                captured_file_id = sent.photo[-1].file_id

    record_slip(
        slip_id=slip_id,
        chat_id=chat_id,
        amount=amount,
        username=username,
        image_url="app_upload",
        file_id=captured_file_id,
        extracted_tx_id=tx_ref,
        admin_messages=admin_messages,
        admin_caption=admin_alert_text,
        method=method,
        ocr_amount=ocr_amount,
        selected_amount=selected_amount,
        unverified_photo=unverified,
    )
    return jsonify({
        "success": True,
        "slip_id": slip_id,
        "status": "PENDING",
        "amount": amount,
        "method": method,
        "ocr_amount": ocr_amount,
        "unverified": unverified,
        "amount_corrected": amount_status == "ocr" and ocr_amount != selected_amount,
        "message": "ပြေစာ လက်ခံရရှိပြီးဖြစ်ပါသည်ခင်ဗျာ။ Admin မှ မကြာမီ စစ်ဆေးအတည်ပြုပေးပါမည်။",
    })


@app_bp.route("/topups", methods=["GET"])
def app_topups():
    """The linked user's own top-up slips with review status."""
    if _rate_limited(_client_bucket("topups"), 60):
        return _rate_limit_response()
    chat_id = _bearer_chat_id()
    if not chat_id:
        return jsonify({"error": "unauthorized"}), 401
    slips = load_all_slips()
    mine = [s for s in slips.values() if str(s.get("chat_id")) == str(chat_id)]
    mine.sort(key=lambda s: str(s.get("created_at") or ""), reverse=True)
    out = [{
        "slip_id": s.get("id"),
        "amount": s.get("amount"),
        "status": s.get("status"),
        "method": s.get("method"),
        "created_at": s.get("created_at"),
        "reviewed_at": s.get("reviewed_at"),
        "review_reason": s.get("review_reason"),
    } for s in mine[:20]]
    return jsonify({"topups": out})


@app_bp.route("/buy", methods=["POST"])
def app_buy():
    """Buy a plan with the wallet; returns the new key for instant saving."""
    if _rate_limited(_client_bucket("buy"), 30):
        return _rate_limit_response()
    chat_id = _bearer_chat_id()
    if not chat_id:
        return jsonify({"error": "unauthorized"}), 401
    body = request.get_json(silent=True) or {}
    plan_code = str(body.get("plan_code") or "").strip().lower()
    server_num = str(body.get("server") or "1").strip()
    renew_key_id = body.get("renew_key_id")
    idem = str(body.get("idempotency_key") or "").strip()
    if not idem or len(idem) > 64:
        return jsonify({"error": "idempotency_key required"}), 400

    plan = PLANS.get(plan_code)
    if not plan:
        return jsonify({"error": "unknown_plan"}), 404
    if plan.get("manual"):
        return jsonify({
            "error": "manual_plan",
            "message": "ဤ Plan ကို Admin မှတစ်ဆင့် သီးသန့် ဆောင်ရွက်ပေးပါသည်။ Customer Service သို့ ဆက်သွယ်ပါ။",
        }), 400

    # Idempotent replay: a retried request returns the original result.
    prior = redis_get(f"app_buy:{chat_id}:{idem}")
    if isinstance(prior, dict) and prior.get("status") == "ok":
        return jsonify(prior)

    lock = redis_set_nx(f"app_buy_lock:{chat_id}", 120)
    if lock is False:
        return jsonify({"error": "purchase_in_progress"}), 409
    try:
        is_admin = _is_admin(chat_id)
        amount = int(plan["price"])
        balance = get_user_balance(chat_id)
        if not is_admin and balance < amount:
            return jsonify({
                "error": "insufficient_balance",
                "balance": balance,
                "required": amount,
                "message": "လက်ကျန်ငွေ မလုံလောက်ပါ။ ငွေအရင်ဖြည့်ပေးပါ။",
            }), 402

        main_bal, bonus_bal, _total = get_user_balance_breakdown(chat_id)
        if bonus_bal > 0 and not is_admin and server_num != "1":
            return jsonify({
                "error": "redeem_credit_server",
                "message": "Redeem/Bonus လက်ကျန်ငွေ ပါရှိသဖြင့် Server 1 မှသာ ဝယ်ယူနိုင်ပါသည်။",
            }), 400

        # Ultimate owners choose: renew an existing key or mint a new one.
        if plan_code == "ultimate" and renew_key_id is None:
            try:
                existing = get_user_ultimate_keys(chat_id, server_num)
            except Exception:
                existing = []
            if existing:
                return jsonify({
                    "status": "choose",
                    "keys": [{"id": str(k.get("id")), "name": str(k.get("name") or "")}
                             for k in existing],
                })

        order_id = "#" + "".join(_random.choices(_string.ascii_uppercase + _string.digits, k=6))
        new_bal, used_bonus_days = update_user_balance(chat_id, -amount)
        try:
            profile = get_user_profile(chat_id) or {}
        except Exception:
            profile = {}
        user_name = (profile.get("full_name") or "Customer").strip()
        apply_days = None if is_admin else used_bonus_days

        if renew_key_id and str(renew_key_id) != "new":
            vpn_key, key_name, expire_date = renew_specific_unlimited_key(
                server_num, str(renew_key_id), months_count=1,
                custom_days=apply_days, order_id=order_id)
        else:
            vpn_key, key_name, expire_date = create_outline_key(
                server_num, user_name, plan_info=plan, target_chat_id=chat_id,
                months_count=1, custom_days=apply_days, is_giveaway=False,
                order_id=order_id)

        if not vpn_key:
            update_user_balance(chat_id, amount)  # refund, as the bot does
            return jsonify({
                "error": "key_creation_failed",
                "message": "ဆာဗာလိုင်းမရသဖြင့် မဆောင်ရွက်နိုင်ပါ။ ငွေအား ပြန်လည်ထည့်သွင်းပေးထားပါသည်။",
            }), 502

        save_sale_transaction(server_num, chat_id, plan_code, plan["name"], 1,
                              amount, order_id=order_id)
        save_user_purchase_record(
            chat_id=chat_id, order_id=order_id, plan_name=plan["name"],
            disp_gb=plan["data"], months_count=1, price_str=f"{amount:,} Ks",
            server_num=server_num, expire_date=expire_date, vpn_key=vpn_key)
        save_key_mapping(user_name.strip().lower(), chat_id)

        result = {
            "status": "ok",
            "order_id": order_id,
            "access_key": vpn_key,
            "key_name": key_name,
            "expire_date": expire_date,
            "plan_name": plan["name"],
            "plan_code": plan_code,
            "server": server_num,
            "new_balance": new_bal,
        }
        redis_set(f"app_buy:{chat_id}:{idem}", result)
        push_app_notification(
            chat_id, "purchase", "ဝယ်ယူမှု အောင်မြင်ပါပြီ 🎉",
            f"{plan['name']} · {order_id} · Expire {expire_date}")
        # Mirror the bot purchase: deliver the key in Telegram too.
        try:
            _bot.send_message(
                chat_id,
                f"🎉 <b>ဝယ်ယူမှု အောင်မြင်ပါသည်ခင်ဗျာ!</b>\n\n"
                f"🧾 <b>Order ID:</b> <code>{order_id}</code>\n\n"
                f"🛍️ <b>Plan:</b> {plan['name']} ({plan['data']})\n\n"
                f"📡 <b>Server:</b> {get_server_display_name(server_num)}\n\n"
                f"⏰ <b>သက်တမ်းကုန်ဆုံးရက်:</b> {expire_date}\n\n"
                f"🔑 <b>လူကြီးမင်း၏ VPN Key:</b>\n\n<code>{vpn_key}</code>",
                parse_mode="HTML", reply_markup=get_key_delivery_markup(vpn_key))
        except Exception:
            pass
        # Admin sale alert, mirroring the bot and Mini App purchase alerts
        # (this was missing: app purchases never reached the admins).
        for aid in ADMIN_CHAT_IDS:
            try:
                _bot.send_message(
                    aid,
                    f"🛍️ <b>H&E VPN App မှ ကီးဝယ်ယူမှု:</b>\n\n"
                    f"🧾 Order ID: <code>{order_id}</code>\n"
                    f"👤 Customer: {user_name} (ID: <code>{chat_id}</code>)\n"
                    f"🛍️ Plan: {plan['name']}\n"
                    f"📡 Server: {get_server_display_name(server_num)}\n"
                    f"💵 ရရှိငွေ: {amount:,} MMK\n"
                    f"⏰ သက်တမ်း: {expire_date} ({f'Redeem ငွေဖြင့် {apply_days} ရက်' if apply_days else '၁လစာ'})",
                    parse_mode="HTML",
                )
            except Exception:
                pass
        return jsonify(result)
    finally:
        if lock is True:
            redis_delete(f"app_buy_lock:{chat_id}")


@app_bp.route("/points/claim", methods=["POST"])
def app_points_claim():
    """Daily-points claim; identical rules to the bot's Claim button."""
    if _rate_limited(_client_bucket("points_claim"), 30):
        return _rate_limit_response()
    chat_id = _bearer_chat_id()
    if not chat_id:
        return jsonify({"error": "unauthorized"}), 401
    try:
        from bot_app.config import points_enabled
        if not points_enabled():
            return jsonify({"ok": False, "error": "disabled"}), 400
    except Exception:
        pass
    return jsonify(try_claim(chat_id))


@app_bp.route("/points/redeem", methods=["POST"])
def app_points_redeem():
    """Redeem points for a Starter key (Server 1), exactly as the bot does.

    Mirrors ``handlers/points.py``: deduct via ``redeem_starter`` (gate:
    topped up at least once + balance >= cost), mint on Server 1 with
    30-day validity, refund via ``refund_starter`` if minting fails, save
    the purchase record + key mapping, DM the key, and return it so the
    app can save it straight into My Keys.
    """
    if _rate_limited(_client_bucket("points_redeem"), 10):
        return _rate_limit_response()
    chat_id = _bearer_chat_id()
    if not chat_id:
        return jsonify({"error": "unauthorized"}), 401
    try:
        from bot_app.config import points_enabled
        if not points_enabled():
            return jsonify({"ok": False, "error": "disabled"}), 400
    except Exception:
        pass

    lock = redis_set_nx(f"app_redeem_lock:{chat_id}", 120)
    if lock is False:
        return jsonify({"error": "redeem_in_progress"}), 409
    try:
        res = redeem_starter(chat_id)
        if not res.get("ok"):
            messages = {
                "needs_topup": "လဲယူရန် အနည်းဆုံး တစ်ကြိမ် ငွေဖြည့်ဖူးရန် လိုအပ်ပါသည်။",
                "insufficient_points": "Points မလုံလောက်ပါ။",
            }
            return jsonify({
                "ok": False,
                "error": res.get("error") or "cannot_redeem",
                "message": messages.get(res.get("error"), "လဲယူ၍ မရနိုင်သေးပါ။"),
                "points": res.get("points", 0),
            }), 400

        order_id = "PTS-" + "".join(
            _random.choices(_string.ascii_uppercase + _string.digits, k=6))
        try:
            profile = get_user_profile(chat_id) or {}
        except Exception:
            profile = {}
        user_name = (profile.get("full_name") or "Customer").strip()
        plan = PLANS.get("starter") or {
            "name": "Starter Plan", "data": "25 GB", "bytes": 25 * 1000 ** 3}
        try:
            vpn_key, key_name, expire_date = create_outline_key(
                "1", user_name, plan_info=plan, target_chat_id=chat_id,
                custom_days=30, is_giveaway=True, order_id=order_id)
        except Exception:
            vpn_key = key_name = expire_date = None

        if not vpn_key:
            refund = refund_starter(chat_id)
            return jsonify({
                "ok": False,
                "error": "key_creation_failed",
                "message": "ဆာဗာလိုင်းမရသဖြင့် Key ထုတ်မရပါ။ Points ပြန်ထည့်ပေးထားပါသည်။",
                "points": refund.get("new_balance", res.get("new_balance", 0)),
            }), 502

        save_user_purchase_record(
            chat_id=chat_id, order_id=order_id,
            plan_name=f"{plan['name']} (Points Reward)",
            disp_gb=plan.get("data", "25 GB"), months_count=1,
            price_str="0 Ks (Points)", server_num="1",
            expire_date=expire_date, vpn_key=vpn_key)
        save_key_mapping(user_name.strip().lower(), chat_id)
        push_app_notification(
            chat_id, "points_redeem", "Points လဲယူမှု အောင်မြင်ပါပြီ 🎉",
            f"Starter Plan · {order_id} · Expire {expire_date}")
        try:
            _bot.send_message(
                chat_id,
                f"🎉 <b>Points ဖြင့် Starter Plan လဲယူမှု အောင်မြင်ပါသည်!</b>\n\n"
                f"🧾 <b>Order ID:</b> <code>{order_id}</code>\n\n"
                f"🛍️ <b>Plan:</b> {plan['name']} ({plan.get('data', '25 GB')})\n\n"
                f"📡 <b>Server:</b> {get_server_display_name('1')}\n\n"
                f"⏰ <b>သက်တမ်းကုန်ဆုံးရက်:</b> {expire_date}\n\n"
                f"💎 <b>ကျန်ရှိ Points:</b> {res.get('new_balance', 0):,}\n\n"
                f"🔑 <b>လူကြီးမင်း၏ VPN Key:</b>\n\n<code>{vpn_key}</code>",
                parse_mode="HTML", reply_markup=get_key_delivery_markup(vpn_key))
        except Exception:
            pass
        return jsonify({
            "status": "ok",
            "order_id": order_id,
            "access_key": vpn_key,
            "key_name": key_name,
            "expire_date": expire_date,
            "plan_name": plan["name"],
            "server": "1",
            "new_points": res.get("new_balance", 0),
        })
    finally:
        if lock is True:
            redis_delete(f"app_redeem_lock:{chat_id}")


@app_bp.route("/keys/replace", methods=["POST"])
def app_key_replace():
    """Key replacement request to the admin queue (as in the Mini App)."""
    if _rate_limited(_client_bucket("key_replace"), 10):
        return _rate_limit_response()
    chat_id = _bearer_chat_id()
    if not chat_id:
        return jsonify({"error": "unauthorized"}), 401
    body = request.get_json(silent=True) or {}
    order_id = str(body.get("order_id") or "").strip()
    if not order_id:
        return jsonify({"success": False, "error": "order_id required"}), 400

    matched = None
    for rec in get_user_combined_purchase_records(chat_id):
        if str(rec.get("order_id") or "") == order_id:
            matched = rec
            break
    if not matched:
        return jsonify({"success": False, "error": "VPN key record not found"}), 404

    exp_dt = _parse_expiry_from_name(str(matched.get("expire_date") or ""))
    if exp_dt and exp_dt.date() < _mm_now().date():
        return jsonify({
            "success": False,
            "error": "expired",
            "message": "သက်တမ်းကုန်ဆုံးသွားသော Key အား လဲလှယ်၍ မရနိုင်ပါ။ Plan အသစ် ဝယ်ယူပေးပါရန်။",
        }), 400

    # Build the SAME actionable admin message the bot's own replacement
    # flow sends (handlers/menu.py): one button per target server, whose
    # callback (handlers/keys.py) deletes the old key and mints the
    # replacement with the same remaining data + expiry. A plain text
    # message left the admin with no way to complete the request.
    alert_text = (
        f"♻️ <b>KEY REPLACEMENT REQUEST</b> (H&E VPN App)\n\n"
        f"👤 <b>Customer ID:</b> <code>{chat_id}</code>\n"
        f"🧾 <b>Order ID:</b> <code>{matched.get('order_id')}</code>\n"
        f"📡 <b>Server:</b> Server {matched.get('server')}\n"
        f"⏰ <b>Expiry:</b> {matched.get('expire_date')}\n"
        f"🔑 <b>Key:</b> <code>{matched.get('vpn_key')}</code>"
    )
    markup = None
    entry = None
    parsed_key = parse_ss_key(str(matched.get("vpn_key") or ""))
    if parsed_key:
        entry = _find_key_by_password(parsed_key["password"], parsed_key["host"])
    if entry is not None:
        try:
            old_server_num = str(entry.get("server") or matched.get("server") or "1")
            key_id = str(entry.get("key_id") or "")
            exp_dt = _parse_registry_expiry(entry)
            exp_str = exp_dt.strftime("%d.%m.%Y") if exp_dt else str(matched.get("expire_date") or "")
            limit = entry.get("limit_bytes")
            total_gb = (int(limit) / 1_000_000_000) if limit else 500
            used = _live_used_bytes(old_server_num, key_id)
            used_gb = (used / 1_000_000_000) if used is not None else 0
            rem_gb = max(0, round(total_gb - used_gb, 2))
            try:
                profile = get_user_profile(chat_id) or {}
            except Exception:
                profile = {}
            buyer = profile.get("full_name") or "Customer"
            alert_text = (
                f"♻️ <b>KEY REPLACEMENT REQUEST</b> (H&E VPN App)\n\n"
                f"👤 ဝယ်ယူသူ: {buyer}\n"
                f"🆔 Chat ID: <code>{chat_id}</code>\n"
                f"📡 Server: Server {old_server_num}\n"
                f"🔑 Key အဟောင်း: {entry.get('name') or ''}\n"
                f"🧰 ကျန်ရှိ Data: <b>{rem_gb} GB</b> / {total_gb} GB\n"
                f"⏰ သက်တမ်းကုန်ရက်: <b>{exp_str}</b>"
            )
            markup = InlineKeyboardMarkup()
            for srv in get_configured_servers():
                sid = str(srv.get("id"))
                markup.add(InlineKeyboardButton(
                    f"📡 {get_server_display_name(sid)} သို့",
                    callback_data=f"replace_srv{sid}_{old_server_num}_{key_id}_{chat_id}_{rem_gb}_{exp_str}"))
            markup.row(InlineKeyboardButton(
                "❌ Reject", callback_data=f"replace_reject_{chat_id}_{key_id}"))
        except Exception:
            markup = None

    for aid in ADMIN_CHAT_IDS:
        try:
            _bot.send_message(aid, alert_text, parse_mode="HTML",
                              reply_markup=markup)
        except Exception:
            pass
    return jsonify({
        "success": True,
        "message": "Key အစားထိုး လဲလှယ်ရန် Admin ထံ တောင်းဆိုမှု ပို့ဆောင်ပြီးပါပြီခင်ဗျာ။",
    })


@app_bp.route("/notifications", methods=["GET"])
def app_notifications():
    if _rate_limited(_client_bucket("notifications"), 60):
        return _rate_limit_response()
    chat_id = _bearer_chat_id()
    if not chat_id:
        return jsonify({"error": "unauthorized"}), 401
    items, unread = list_app_notifications(chat_id)
    return jsonify({"notifications": items, "unread": unread})


@app_bp.route("/notifications/read", methods=["POST"])
def app_notifications_read():
    if _rate_limited(_client_bucket("notifications_read"), 60):
        return _rate_limit_response()
    chat_id = _bearer_chat_id()
    if not chat_id:
        return jsonify({"error": "unauthorized"}), 401
    mark_app_notifications_read(chat_id)
    return jsonify({"success": True})


# --- Support Chat -------------------------------------------------------------
# Customer side: the in-app chat screen (bearer-token auth, same as the
# rest of /api/app). Agent side: the Muse support agent (secret header).

def _support_display_name(chat_id) -> str:
    try:
        from bot_app.services.profiles import load_all_profiles
        profile = (load_all_profiles() or {}).get(str(chat_id)) or {}
        name = profile.get("full_name") or profile.get("username") or ""
        return str(name).strip()
    except Exception:
        return ""


@app_bp.route("/support/messages", methods=["GET"])
def app_support_messages():
    if _rate_limited(_client_bucket("support_messages"), 60):
        return _rate_limit_response()
    chat_id = _bearer_chat_id()
    if not chat_id:
        return jsonify({"error": "unauthorized"}), 401
    from bot_app.services.support_chat import agent_typing, load_thread
    return jsonify({"messages": load_thread(chat_id),
                    "agent_typing": agent_typing(chat_id)})


@app_bp.route("/support/send", methods=["POST"])
def app_support_send():
    if _rate_limited(_client_bucket("support_send"), 30):
        return _rate_limit_response()
    chat_id = _bearer_chat_id()
    if not chat_id:
        return jsonify({"error": "unauthorized"}), 401
    data = request.get_json(silent=True) or {}
    text = str(data.get("text") or "").strip()
    if not text:
        return jsonify({"error": "empty_message"}), 400
    if len(text) > 1000:
        return jsonify({"error": "message_too_long"}), 400
    from bot_app.services.support_chat import customer_say
    name = _support_display_name(chat_id) or f"User {chat_id}"
    msg = customer_say(chat_id, name, text)
    return jsonify({"success": True, "message": msg})


@app_bp.route("/support/clear", methods=["POST"])
def app_support_clear():
    if _rate_limited(_client_bucket("support_clear"), 10):
        return _rate_limit_response()
    chat_id = _bearer_chat_id()
    if not chat_id:
        return jsonify({"error": "unauthorized"}), 401
    from bot_app.services.support_chat import clear_thread
    clear_thread(chat_id)
    return jsonify({"success": True})


@app_bp.route("/support/send-photo", methods=["POST"])
def app_support_send_photo():
    if _rate_limited(_client_bucket("support_send_photo"), 10):
        return _rate_limit_response()
    chat_id = _bearer_chat_id()
    if not chat_id:
        return jsonify({"error": "unauthorized"}), 401
    data = request.get_json(silent=True) or {}
    caption = str(data.get("caption") or "").strip()
    if len(caption) > 1000:
        return jsonify({"error": "message_too_long"}), 400
    try:
        image = base64.b64decode(str(data.get("image_b64") or ""), validate=True)
    except Exception:
        return jsonify({"error": "bad_image"}), 400
    if not image or len(image) > 3_500_000:
        return jsonify({"error": "bad_image"}), 400
    from bot_app.services.support_chat import customer_say_photo
    name = _support_display_name(chat_id) or f"User {chat_id}"
    msg = customer_say_photo(chat_id, name, image, caption)
    if msg is None:
        return jsonify({"error": "photo_delivery_failed"}), 502
    return jsonify({"success": True, "message": msg})


def _support_photo_response(file_id):
    from bot_app.services.support_chat import fetch_photo_bytes
    data = fetch_photo_bytes(file_id or "")
    if not data:
        return jsonify({"error": "not_found"}), 404
    return Response(
        data,
        mimetype="image/jpeg",
        headers={"Cache-Control": "private, max-age=3600"},
    )


@app_bp.route("/support/photo", methods=["GET"])
def app_support_photo():
    if not _bearer_chat_id():
        return jsonify({"error": "unauthorized"}), 401
    return _support_photo_response(request.args.get("file_id"))


@app_bp.route("/support/agent/photo", methods=["GET"])
def app_support_agent_photo():
    if not _agent_authorized():
        return jsonify({"error": "unauthorized"}), 401
    return _support_photo_response(request.args.get("file_id"))


def _agent_authorized() -> bool:
    secret = os.environ.get("SUPPORT_AGENT_SECRET") or ""
    if not secret:
        return False
    given = request.headers.get("X-Support-Agent-Secret") or ""
    return hmac.compare_digest(given, secret)


@app_bp.route("/support/agent/pending", methods=["GET"])
def app_support_agent_pending():
    if not _agent_authorized():
        return jsonify({"error": "unauthorized"}), 401
    from bot_app.services.support_chat import owner_present, pending_threads
    return jsonify({"owner_present": owner_present(), "threads": pending_threads()})


@app_bp.route("/support/agent/reply", methods=["POST"])
def app_support_agent_reply():
    if not _agent_authorized():
        return jsonify({"error": "unauthorized"}), 401
    data = request.get_json(silent=True) or {}
    chat_id = str(data.get("chat_id") or "").strip()
    text = str(data.get("text") or "").strip()
    if not chat_id or not text:
        return jsonify({"error": "chat_id and text are required"}), 400
    if len(text) > 2000:
        return jsonify({"error": "message_too_long"}), 400
    from bot_app.services.support_chat import agent_reply
    status, msg = agent_reply(chat_id, text)
    if status == "owner_present":
        return jsonify({"error": "owner_present"}), 409
    return jsonify({"success": True, "message": msg})


@app_bp.route("/support/agent/presence", methods=["POST"])
def app_support_agent_presence():
    if not _agent_authorized():
        return jsonify({"error": "unauthorized"}), 401
    data = request.get_json(silent=True) or {}
    from bot_app.services.support_chat import set_owner_present
    present = set_owner_present(bool(data.get("present")))
    return jsonify({"success": True, "owner_present": present})


@app_bp.route("/support/agent/typing", methods=["POST"])
def app_support_agent_typing():
    if not _agent_authorized():
        return jsonify({"error": "unauthorized"}), 401
    data = request.get_json(silent=True) or {}
    chat_id = str(data.get("chat_id") or "").strip()
    if not chat_id:
        return jsonify({"error": "chat_id is required"}), 400
    from bot_app.services.support_chat import agent_typing, set_agent_typing
    set_agent_typing(chat_id, bool(data.get("typing")))
    return jsonify({"success": True, "agent_typing": agent_typing(chat_id)})


@app_bp.route("/support/agent/escalate", methods=["POST"])
def app_support_agent_escalate():
    if not _agent_authorized():
        return jsonify({"error": "unauthorized"}), 401
    data = request.get_json(silent=True) or {}
    chat_id = str(data.get("chat_id") or "").strip()
    summary = str(data.get("summary") or "").strip()
    if not chat_id or not summary:
        return jsonify({"error": "chat_id and summary are required"}), 400
    from bot_app.services.support_chat import escalate
    escalate(chat_id, summary)
    return jsonify({"success": True})


@app_bp.route("/support/agent/promo-key", methods=["POST"])
def app_support_agent_promo_key():
    """Bot Update #18: issue the Facebook promo key (agent-only).

    Body: {"chat_id", "code", "name"?}. The code must match the live
    promo code; the service enforces one claim per account and the
    total cap, creates a 10 GB / 5-day key on Server 2 named after
    the customer, and returns the ss:// key for the agent to paste
    into the Support Chat thread.
    """
    if not _agent_authorized():
        return jsonify({"error": "unauthorized"}), 401
    data = request.get_json(silent=True) or {}
    chat_id = str(data.get("chat_id") or "").strip()
    code = str(data.get("code") or "").strip()
    name = str(data.get("name") or "").strip()
    if not chat_id:
        return jsonify({"error": "chat_id is required"}), 400
    from bot_app.services.promo import PROMO_CODE, claim_promo_key
    if code.upper() != PROMO_CODE:
        return jsonify({"ok": False, "error": "bad_code"}), 400
    res = claim_promo_key(chat_id, fallback_name=name)
    if res.get("ok"):
        return jsonify(res)
    status = {
        "already_claimed": 409,
        "cap_reached": 409,
        "busy": 409,
        "key_creation_failed": 502,
    }.get(res.get("error"), 400)
    return jsonify(res), status


# --- slip auto-review agent (Bot Update #19) --------------------------------
# Mirrors the Support Chat presence model: while the owner is present
# he reviews slips himself and the agent stays out (the review
# endpoint refuses with 409); while he is away the agent may approve
# a pending slip through the same review_slip choke point the
# Telegram button and the dashboard use, recorded as "H&E Agent".

@app_bp.route("/agent/slips/pending", methods=["GET"])
def app_agent_slips_pending():
    if not _agent_authorized():
        return jsonify({"error": "unauthorized"}), 401
    from bot_app.services.slips import pending_slips_for_agent
    from bot_app.services.support_chat import owner_present
    return jsonify({
        "owner_present": owner_present(),
        "slips": pending_slips_for_agent(),
    })


@app_bp.route("/agent/slips/photo", methods=["GET"])
def app_agent_slips_photo():
    if not _agent_authorized():
        return jsonify({"error": "unauthorized"}), 401
    return _support_photo_response(request.args.get("file_id"))


@app_bp.route("/agent/slips/review", methods=["POST"])
def app_agent_slips_review():
    if not _agent_authorized():
        return jsonify({"error": "unauthorized"}), 401
    from bot_app.services.support_chat import owner_present
    if owner_present():
        return jsonify({"error": "owner_present"}), 409
    data = request.get_json(silent=True) or {}
    slip_id = str(data.get("slip_id") or "").strip()
    action = str(data.get("action") or "").strip().upper()
    reason = str(data.get("reason") or "").strip()
    if not slip_id or action not in ("APPROVE", "REJECT"):
        return jsonify({"error": "slip_id and a valid action are required"}), 400
    from bot_app.services.slips import review_slip
    res = review_slip(slip_id, action, reviewed_by="H&E Agent",
                      reason=reason)
    if not res.get("success"):
        return jsonify(res), res.get("code", 400)
    return jsonify(res)
