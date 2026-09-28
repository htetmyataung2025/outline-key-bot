"""Admin REST API routes for Control Center and Telegram Mini App."""

import json
import queue
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta
from urllib.parse import unquote

import requests
from flask import Blueprint, Response, g, jsonify, request, stream_with_context

from bot_app.config import ADMIN_CHAT_IDS, TELEGRAM_TOKEN
from bot_app.helpers.auth import check_admin_credentials, current_admin_id, require_admin_api
from bot_app.helpers.rate_limit import (
    clear_login_attempts,
    client_ip_from_headers,
    login_rate_limit_window,
    register_login_attempt,
)
from bot_app.helpers.sse import consume_ticket, issue_ticket
from bot_app.services.admin_telemetry import get_admin_overview_telemetry, reset_telemetry_cache
from bot_app.storage import versioning
from bot_app.storage.versioning import get_data_version
from bot_app.services.billing import load_all_wallets, update_user_balance
from bot_app.services.orders import (
    is_code_expired,
    load_all_users,
    load_redeem_codes,
    save_redeem_codes,
)
from bot_app.services.registry import clean_key_label, load_persistent_keys, delete_persistent_key
from bot_app.services.slips import get_slip_by_id, get_slips_list, load_audit_logs, record_audit_log, review_slip
from bot_app.timeutil import myanmar_now
from bot_app.utils import generate_random_redeem_code

admin_bp = Blueprint("admin_bp", __name__, url_prefix="/api/admin")

# Route that authenticates with a one-time stream ticket instead of headers
# (EventSource cannot attach custom headers). Checked by endpoint name below.
SSE_STREAM_ENDPOINT = "admin_bp.sse_events"

# Live Outline sync in GET /keys is throttled: the probe costs 1-2 s, so
# page reloads reuse the cached registry and only re-sync every 30 s
# (or immediately with ?sync=force).
LIVE_SYNC_MIN_INTERVAL = 30.0
_last_live_sync = 0.0


# Apply authentication to all admin routes in blueprint
@admin_bp.before_request
def authenticate_admin():
    if request.endpoint == "admin_bp.admin_login":
        # The submitted Admin ID + password themselves authenticate this route.
        return None
    if request.endpoint == SSE_STREAM_ENDPOINT:
        admin = consume_ticket(request.args.get("ticket", ""))
        if not admin:
            return jsonify({"error": "Invalid or expired stream ticket"}), 401
        g.admin_user = admin
        return None
    return require_admin_api(lambda: None)()


# ---------------------------------------------------------------------------
# 0. Dashboard login (Admin ID + password)
# ---------------------------------------------------------------------------
@admin_bp.route("/login", methods=["POST"])
def admin_login():
    """Validate the Control Center login form.

    The dashboard (browser AND Telegram Mini App) posts the Admin's Telegram
    ID plus the shared secret password here before storing the pair for its
    authenticated API calls. Brute-force guard: every attempt counts against
    a per-IP fixed-window counter (Upstash INCR, in-memory fallback); once
    over the limit the request is answered 429 before the password is even
    compared, and a successful login clears the counter. Returns 403 for an
    unregistered ID, 401 for a wrong password.
    """
    data = request.get_json(silent=True) or {}
    admin_id = str(data.get("admin_id", "")).strip()
    password = str(data.get("password", ""))
    if not admin_id or not password:
        return jsonify({"error": "admin_id and password are required"}), 400

    ip = client_ip_from_headers(request.headers)
    _count, exceeded = register_login_attempt(ip)
    if exceeded:
        minutes = max(1, login_rate_limit_window() // 60)
        resp = jsonify({
            "error": f"Too many login attempts. Try again in about {minutes} minute(s)."
        })
        resp.headers["Retry-After"] = str(login_rate_limit_window())
        return resp, 429

    failure = check_admin_credentials(admin_id, password)
    if failure:
        return jsonify({"error": failure[1]}), failure[0]
    clear_login_attempts(ip)
    return jsonify({"ok": True, "admin": {"id": admin_id}}), 200


# ---------------------------------------------------------------------------
# 1. System Telemetry & Overview
# ---------------------------------------------------------------------------
@admin_bp.route("/overview", methods=["GET"])
def get_overview():
    force_refresh = request.args.get("refresh") in ("1", "true", "yes")
    telemetry = get_admin_overview_telemetry(force_refresh=force_refresh)
    return jsonify(telemetry), 200


# ---------------------------------------------------------------------------
# 1b. Live change push (SSE) + version fallback
# ---------------------------------------------------------------------------
@admin_bp.route("/sse-ticket", methods=["POST"])
def create_sse_ticket():
    """Exchange the authenticated session for a one-time stream ticket.

    EventSource cannot send auth headers, so the client calls this first
    (with its normal headers) and opens ``GET /events?ticket=...`` with the
    short-lived random token it returns.
    """
    return jsonify({"ticket": issue_ticket(g.admin_user)}), 200


@admin_bp.route("/events", methods=["GET"])
def sse_events():
    """Server-Sent Events stream of data-version changes.

    Push-based live sync for the dashboard: the connection stays open and
    every shared-state write anywhere in this process (Telegram handler
    thread or another dashboard request) emits the new version instantly —
    no client-side polling in the normal path. A comment heartbeat keeps
    intermediaries from closing an idle connection.
    """
    def stream():
        q = versioning.subscribe()
        try:
            # Baseline lets a reconnecting client detect writes it missed
            # while disconnected: if the current version is ahead of the one
            # it last saw, it refreshes once on arrival.
            yield f"data: {json.dumps({'version': get_data_version()})}\n\n"
            while True:
                try:
                    version = q.get(timeout=20)
                    yield f"data: {json.dumps({'version': version})}\n\n"
                except queue.Empty:
                    yield ": ping\n\n"
        finally:
            versioning.unsubscribe(q)

    resp = Response(stream_with_context(stream()), mimetype="text/event-stream")
    resp.headers["Cache-Control"] = "no-cache"
    resp.headers["X-Accel-Buffering"] = "no"
    return resp


@admin_bp.route("/version", methods=["GET"])
def get_version():
    """Cheap fallback for environments where SSE cannot stream (Vercel).

    The dashboard only uses this while its push channel is down: it asks
    "did the version move?" and re-fetches real data solely on change.
    """
    return jsonify({"version": get_data_version()}), 200


# ---------------------------------------------------------------------------
# 2. Slips & Payment Verification Queue
# ---------------------------------------------------------------------------
@admin_bp.route("/slips", methods=["GET"])
def list_slips():
    status = request.args.get("status", "PENDING")
    if status.upper() == "ALL":
        status = None
    slips = get_slips_list(status=status)
    return jsonify(slips), 200


@admin_bp.route("/slips/<slip_id>", methods=["GET"])
def get_slip(slip_id):
    slip = get_slip_by_id(_real_slip_id(slip_id))
    if not slip:
        return jsonify({"error": "Slip not found"}), 404
    return jsonify(slip), 200


def _real_slip_id(raw: str) -> str:
    """Undo any residual percent-encoding of '#' in the path parameter.

    Slip ids look like '#082412'; browsers send '%23', and some runtimes
    (Vercel) hand the encoded segment to Flask untouched.
    """
    return unquote(raw or "")


@admin_bp.route("/slips/<slip_id>/image", methods=["GET"])
def slip_image(slip_id):
    """Stream the receipt photo stored as a Telegram ``file_id``.

    The dashboard cannot put auth headers on a plain ``<img src>``, so the
    image is proxied through this authenticated endpoint and consumed as a
    blob. Telegram download links expire after ~1h, hence the per-request
    ``get_file`` call; the response is cached privately for an hour.
    """
    slip = get_slip_by_id(_real_slip_id(slip_id))
    if not slip:
        return jsonify({"error": "Slip not found"}), 404

    file_id = (slip.get("file_id") or "").strip()
    if not file_id:
        return jsonify({"error": "This slip has no stored receipt image"}), 404

    try:
        from bot_app.extensions import bot
        tg_file = bot.get_file(file_id)
        file_url = f"https://api.telegram.org/file/bot{TELEGRAM_TOKEN}/{tg_file.file_path}"
        resp = requests.get(file_url, timeout=15)
    except Exception as e:
        return jsonify({"error": f"Could not fetch receipt from Telegram: {e}"}), 502

    if resp.status_code != 200 or not resp.content:
        return jsonify({"error": f"Telegram refused the file download (HTTP {resp.status_code})"}), 502

    ext = str(tg_file.file_path or "").rsplit(".", 1)[-1].lower()
    mime = {"png": "image/png", "jpg": "image/jpeg", "jpeg": "image/jpeg",
            "webp": "image/webp", "gif": "image/gif"}.get(ext, "image/jpeg")

    out = Response(resp.content, mimetype=mime)
    out.headers["Cache-Control"] = "private, max-age=3600"
    return out


@admin_bp.route("/slips/<slip_id>/review", methods=["POST"])
def review_slip_endpoint(slip_id):
    data = request.get_json(silent=True) or {}
    action = data.get("action", "")
    reason = data.get("reason", "")

    if not action or action.upper() not in ("APPROVE", "REJECT"):
        return jsonify({"error": "Action must be 'APPROVE' or 'REJECT'"}), 400

    admin_id = current_admin_id()
    result = review_slip(_real_slip_id(slip_id), action=action, reviewed_by=admin_id, reason=reason)

    if not result.get("success"):
        return jsonify(result), result.get("code", 400)

    return jsonify(result), 200


# ---------------------------------------------------------------------------
# 3. Outline Access Keys Management
# ---------------------------------------------------------------------------
@admin_bp.route("/keys", methods=["GET"])
def list_keys():
    global _last_live_sync

    server_id = request.args.get("server_id")
    search = request.args.get("search", "").strip().lower()
    page = int(request.args.get("page", 1))
    page_size = int(request.args.get("page_size", 50))

    # Pull live keys from the Outline servers into the registry so the list shows
    # every key on the servers, not only the ones created through the dashboard.
    # Throttled: page visits within 30s reuse the cached registry (?sync=force
    # bypasses, e.g. after manual server changes).
    sync_mode = request.args.get("sync", "1")
    if sync_mode != "0":
        now = time.monotonic()
        if sync_mode == "force" or now - _last_live_sync >= LIVE_SYNC_MIN_INTERVAL:
            try:
                from bot_app.services.outline import refresh_registry_from_servers
                refresh_registry_from_servers()
                _last_live_sync = time.monotonic()
            except Exception:
                pass

    registry = load_persistent_keys()
    items = list(registry.values())

    if server_id:
        items = [k for k in items if str(k.get("server")) == str(server_id)]

    if search:
        items = [
            k for k in items
            if search in str(k.get("name", "")).lower()
            or search in str(k.get("chat_id", "")).lower()
            or search in str(k.get("key_id", "")).lower()
        ]

    total = len(items)
    start = (page - 1) * page_size
    paged_items = items[start : start + page_size]

    # Live per-key data usage (lifetime bytes transferred) lives in a separate
    # Outline endpoint, so join it here for only the keys on this page. Skipped
    # when sync=0 (hermetic reads); best-effort otherwise — an unreachable
    # server just leaves bytes_used as None and the dashboard shows "—".
    usage = {}
    if sync_mode != "0":
        try:
            from bot_app.services.outline import get_usage_by_server
            usage = get_usage_by_server({str(k.get("server")) for k in paged_items})
        except Exception:
            usage = {}

    # Attach a clean display label (raw packed name kept intact for recovery)
    # plus the joined usage figure.
    for k in paged_items:
        k["label"] = clean_key_label(k.get("name", ""))
        used = usage.get(str(k.get("server")), {}).get(str(k.get("key_id")))
        k["bytes_used"] = int(used) if used is not None else None

    return jsonify({"total": total, "page": page, "page_size": page_size, "items": paged_items}), 200


@admin_bp.route("/keys", methods=["POST"])
def create_key_endpoint():
    data = request.get_json(silent=True) or {}
    server_id = str(data.get("server_id", "1"))
    name = data.get("name", "Custom VIP Key")
    data_limit_gb = data.get("data_limit_gb", 0)
    valid_days = int(data.get("valid_days", 30))
    assign_to_user_id = data.get("assign_to_user_id")

    from bot_app.services.outline import create_outline_key

    result = create_outline_key(
        server_num=server_id,
        user_name=name,
        custom_gb=data_limit_gb if data_limit_gb else None,
        target_chat_id=assign_to_user_id,
        custom_days=valid_days,
    )

    if not result:
        return jsonify({"error": "Failed to create Outline key on server"}), 500

    admin_id = current_admin_id()
    record_audit_log(
        admin_id=admin_id,
        action="KEY_CREATE",
        target_type="key",
        target_id=name,
        details={"server": server_id, "days": valid_days, "gb": data_limit_gb},
    )

    return jsonify({"success": True, "key": result}), 201


def _persist_expiry_on_server(server_num, key_id, new_dt, entry):
    """Best-effort: rewrite the key's expiry date in its name on the Outline server
    so a manual extend survives the live re-sync in list_keys. Silent on failure."""
    import re
    import requests
    from bot_app.services.outline import get_server_api_url

    api_url = get_server_api_url(server_num)
    if not api_url:
        return

    dotted = new_dt.strftime("%d.%m.%Y")
    try:
        resp = requests.get(f"{api_url}/access-keys", verify=False, timeout=4)
        if resp.status_code != 200:
            return
        for k in resp.json().get("accessKeys", []):
            if str(k.get("id")) == str(key_id):
                name = k.get("name", "") or entry.get("name", "")
                new_name = re.sub(r"\d{1,2}\.\d{1,2}\.(\d{4}|\d{2})", dotted, name)
                if new_name == name and dotted not in name:
                    new_name = f"{name} {dotted}".strip()
                requests.put(
                    f"{api_url}/access-keys/{key_id}/name",
                    data={"name": new_name},
                    verify=False,
                    timeout=6,
                )
                entry["name"] = new_name
                break
    except Exception:
        pass


@admin_bp.route("/keys/<key_id>/extend", methods=["POST"])
def extend_key_endpoint(key_id):
    data = request.get_json(silent=True) or {}
    add_days = int(data.get("add_days", 30))

    registry = load_persistent_keys()
    matched_entry = None
    matched_key = None

    for r_k, r_v in registry.items():
        if str(r_v.get("key_id")) == str(key_id) or r_k == str(key_id):
            matched_key = r_k
            matched_entry = r_v
            break

    if not matched_entry:
        return jsonify({"error": "Key not found in registry"}), 404

    # Calculate new expiration date
    current_exp = matched_entry.get("expire_date")
    now = myanmar_now()
    try:
        if current_exp and "/" in current_exp:
            base_date = datetime.strptime(current_exp, "%d/%m/%Y")
            if base_date < now:
                base_date = now
        elif current_exp and "." in current_exp:
            base_date = datetime.strptime(current_exp, "%d.%m.%Y")
            if base_date < now:
                base_date = now
        else:
            base_date = now
    except Exception:
        base_date = now

    new_dt = base_date + timedelta(days=add_days)
    new_exp_date = new_dt.strftime("%d/%m/%Y")

    # Write the new expiry onto the Outline server key name so the extend is not
    # reverted the next time list_keys re-syncs live server data.
    server_num = str(matched_entry.get("server", "1"))
    _persist_expiry_on_server(server_num, key_id, new_dt, matched_entry)

    matched_entry["expire_date"] = new_exp_date
    registry[matched_key] = matched_entry

    import json
    from bot_app.storage.kv import redis_set
    from bot_app.storage.paths import PERSISTENT_KEYS_FILE

    redis_set("persistent_keys_registry", registry)
    try:
        with open(PERSISTENT_KEYS_FILE, "w") as f:
            json.dump(registry, f, indent=2)
    except Exception:
        pass


    admin_id = current_admin_id()
    record_audit_log(
        admin_id=admin_id,
        action="KEY_EXTEND",
        target_type="key",
        target_id=str(key_id),
        details={"add_days": add_days, "new_expire_date": new_exp_date},
    )

    return jsonify({"success": True, "new_expire_date": new_exp_date, "key": matched_entry}), 200


@admin_bp.route("/keys/<server_id>/<key_id>", methods=["DELETE"])
def delete_key_endpoint(server_id, key_id):
    import requests
    from bot_app.services.outline import get_server_api_url

    api_url = get_server_api_url(server_id)
    if not api_url:
        return jsonify({"error": f"Server {server_id} is not configured"}), 400

    # Delete the key on the Outline server. HTTP 404 means it is already gone,
    # which we treat as success so the stale registry entry can be cleaned up.
    try:
        resp = requests.delete(f"{api_url}/access-keys/{key_id}", verify=False, timeout=8)
    except Exception as e:
        return jsonify({"error": f"Could not reach server {server_id}: {e}"}), 502

    if resp.status_code not in (200, 204, 404):
        return jsonify({"error": f"Server refused deletion (HTTP {resp.status_code})"}), 502

    delete_persistent_key(server_id, key_id)

    admin_id = current_admin_id()
    record_audit_log(
        admin_id=admin_id,
        action="KEY_DELETE",
        target_type="key",
        target_id=str(key_id),
        details={"server": str(server_id), "server_status": resp.status_code},
    )

    return jsonify({"success": True, "server_id": str(server_id), "key_id": str(key_id)}), 200


# ---------------------------------------------------------------------------
# 4. Redeem Code Management
# ---------------------------------------------------------------------------
@admin_bp.route("/redeems", methods=["GET"])
def list_redeems():
    codes = load_redeem_codes()
    items = []
    for code, info in codes.items():
        item = dict(info)
        item["code"] = code
        # Derived fields so the dashboard can show pool/claim/expiry state
        # without duplicating the redemption rules client-side.
        item["remaining"] = int(info.get("remaining", info.get("amount", 0) or 0))
        item["claimed_count"] = len(info.get("claimed_users", []) or [])
        item["expired"] = is_code_expired(info)
        items.append(item)
    return jsonify(items), 200


@admin_bp.route("/redeems/<code>", methods=["DELETE"])
def delete_redeem_code(code):
    codes = load_redeem_codes()
    info = codes.pop(code, None)
    if info is None:
        return jsonify({"error": "Redeem code not found"}), 404
    save_redeem_codes(codes)

    admin_id = current_admin_id()
    record_audit_log(
        admin_id=admin_id,
        action="REDEEM_DELETE",
        target_type="redeem",
        target_id=code,
        details={
            "amount": info.get("amount"),
            "mode": info.get("mode"),
            "remaining": info.get("remaining", info.get("amount")),
            "claimed_count": len(info.get("claimed_users", []) or []),
        },
    )
    return jsonify({"success": True, "deleted": code}), 200


@admin_bp.route("/redeems/delete", methods=["POST"])
def delete_redeem_batch():
    data = request.get_json(silent=True) or {}
    targets = data.get("codes")
    if not isinstance(targets, list) or not targets:
        return jsonify({"error": "codes must be a non-empty list"}), 400

    codes = load_redeem_codes()
    admin_id = current_admin_id()
    deleted, not_found = [], []
    for code in targets:
        info = codes.pop(str(code), None)
        if info is None:
            not_found.append(str(code))
            continue
        deleted.append(str(code))
        record_audit_log(
            admin_id=admin_id,
            action="REDEEM_DELETE",
            target_type="redeem",
            target_id=str(code),
            details={
                "amount": info.get("amount"),
                "mode": info.get("mode"),
                "remaining": info.get("remaining", info.get("amount")),
                "claimed_count": len(info.get("claimed_users", []) or []),
                "bulk": True,
            },
        )
    if deleted:
        save_redeem_codes(codes)
    return jsonify({"success": True, "deleted": len(deleted), "not_found": not_found}), 200


@admin_bp.route("/redeems/batch", methods=["POST"])
def generate_redeem_batch():
    data = request.get_json(silent=True) or {}
    amount_ks = int(data.get("amount_ks", 1000))
    mode = data.get("mode", "single")  # single or shared
    valid_days = int(data.get("valid_days", 30))
    count = int(data.get("count", 1))

    if count < 1 or count > 50:
        return jsonify({"error": "Count must be between 1 and 50"}), 400

    codes_data = load_redeem_codes()
    created_codes = []
    now = myanmar_now()
    exp_date = (now + timedelta(days=valid_days)).strftime("%d/%m/%Y %I:%M %p")

    for _ in range(count):
        code = f"RD-{generate_random_redeem_code().upper()}"
        # Same record shape the Telegram redemption flow (menu.py) reads:
        # validity_days/remaining/claimed_users are required for shared
        # codes to be claimable and for single codes to keep their validity.
        codes_data[code] = {
            "type": "wallet",
            "amount": amount_ks,
            "mode": mode,
            "remaining": amount_ks,
            "validity_days": valid_days,
            "claimed_users": [],
            "valid_days": valid_days,
            "expires_at": exp_date,
            "created_at": now.strftime("%Y-%m-%d %H:%M:%S"),
            "is_active": True,
        }
        created_codes.append(code)

    save_redeem_codes(codes_data)

    admin_id = current_admin_id()
    record_audit_log(
        admin_id=admin_id,
        action="REDEEM_BATCH_CREATE",
        target_type="redeem",
        target_id=str(len(created_codes)),
        details={"amount": amount_ks, "mode": mode, "count": count},
    )

    return jsonify({"created_count": len(created_codes), "codes": created_codes}), 201


# ---------------------------------------------------------------------------
# 5. Customers & Wallets
# ---------------------------------------------------------------------------
@admin_bp.route("/customers", methods=["GET"])
def list_customers():
    from bot_app.services.profiles import backfill_profiles_from_history
    from bot_app.services.slips import get_lifetime_topups_by_user
    from bot_app.services.points import load_all_points

    # The six reads are independent; together they dominate the endpoint's
    # latency (sequential KV round-trips). Run them concurrently.
    with ThreadPoolExecutor(max_workers=6) as executor:
        f_profiles = executor.submit(backfill_profiles_from_history)
        f_wallets = executor.submit(load_all_wallets)
        f_users = executor.submit(load_all_users)
        f_keys = executor.submit(load_persistent_keys)
        f_topups = executor.submit(get_lifetime_topups_by_user)
        f_points = executor.submit(load_all_points)
        profiles = f_profiles.result()
        wallets = f_wallets.result()
        all_users_list = f_users.result()
        registry = f_keys.result()
        topups = f_topups.result()
        points_data = f_points.result()

    all_users = set(all_users_list)
    for uid in wallets.keys():
        all_users.add(str(uid))
    for uid in profiles.keys():
        all_users.add(str(uid))
    for uid in points_data.keys():
        all_users.add(str(uid))

    # Count Outline keys per user from the cached registry (no live server sync).
    # Users who only own a key (no wallet / no profile yet) are pulled in too.
    keys_by_user = {}
    for k in registry.values():
        cid = str(k.get("chat_id") or "").strip()
        if cid:
            keys_by_user[cid] = keys_by_user.get(cid, 0) + 1
            all_users.add(cid)

    customers = []
    for uid in sorted(all_users):
        profile = profiles.get(uid, {})
        customers.append({
            "chat_id": uid,
            "wallet_balance": wallets.get(uid, 0),
            "username": profile.get("username", ""),
            "full_name": profile.get("full_name", ""),
            "first_seen": profile.get("first_seen", ""),
            "last_seen": profile.get("last_seen", ""),
            "keys_count": keys_by_user.get(uid, 0),
            # Lifetime paid-in (sum of APPROVED slips), a.k.a "Total Spent".
            "total_topup": topups.get(uid, 0),
            # Loyalty points balance (0 when the user has none yet).
            "points": int((points_data.get(uid) or {}).get("points", 0)),
        })

    return jsonify({"total": len(customers), "customers": customers}), 200


@admin_bp.route("/customers/<chat_id>", methods=["GET"])
def get_customer_detail(chat_id):
    """Full profile bundle for the customer detail page: identity, wallet
    breakdown, and the five record collections (keys, purchases, slips,
    redeems, audit) rendered in the right-hand tabs."""
    from bot_app.services.billing import get_user_balance_breakdown
    from bot_app.services.orders import get_user_combined_purchase_records, load_redeem_codes
    from bot_app.services.profiles import backfill_profiles_from_history, get_user_profile
    from bot_app.services.points import get_points

    uid = str(chat_id)
    backfill_profiles_from_history()
    profile = get_user_profile(uid)
    points_rec = get_points(uid)

    main_bal, bonus_bal, total_bal = get_user_balance_breakdown(uid)

    # Access keys (from cached registry, filtered to this user)
    keys = [
        {**k, "label": clean_key_label(k.get("name", ""))}
        for k in load_persistent_keys().values()
        if str(k.get("chat_id") or "").strip() == uid
    ]

    # Purchase / plan history
    try:
        purchases = get_user_combined_purchase_records(uid)
    except Exception:
        purchases = []

    # Payment slips submitted by this user (newest first)
    slips = [s for s in get_slips_list() if str(s.get("chat_id")) == uid]

    # Lifetime "Total Spent" = sum of this user's APPROVED slips (real paid-in).
    total_topup = sum(
        int(s.get("amount", 0) or 0) for s in slips if s.get("status") == "APPROVED"
    )

    # Shared redeem codes this user has claimed (single-use codes are deleted on
    # claim, so only shared codes leave a per-user trail).
    redeems = []
    for code, info in load_redeem_codes().items():
        if uid in [str(u) for u in info.get("claimed_users", [])]:
            redeems.append({
                "code": code,
                "amount": info.get("amount", 0),
                "mode": info.get("mode", "shared"),
                "valid_days": info.get("validity_days", info.get("valid_days", 0)),
                "expires_at": info.get("expires_at", ""),
            })

    # Admin audit entries that targeted this user or their slips
    slip_ids = {str(s.get("id")) for s in slips}
    audit = []
    points_ledger = []
    for log in load_audit_logs():
        target_type = log.get("target_type")
        target_id = str(log.get("target_id", ""))
        details = log.get("details", {}) or {}
        # Loyalty-points events form their own ledger tab (claims, top-up grants,
        # redemptions, admin adjustments), keyed by the customer as target.
        if target_type == "points" and target_id == uid:
            points_ledger.append(log)
            continue
        if (
            (target_type == "user" and target_id == uid)
            or str(details.get("chat_id", "")) == uid
            or (target_type == "slip" and target_id in slip_ids)
        ):
            audit.append(log)
    audit.sort(key=lambda x: x.get("timestamp", ""), reverse=True)
    points_ledger.sort(key=lambda x: x.get("timestamp", ""), reverse=True)

    return jsonify({
        "profile": {
            "chat_id": uid,
            "username": profile.get("username", ""),
            "full_name": profile.get("full_name", ""),
            "first_seen": profile.get("first_seen", ""),
            "last_seen": profile.get("last_seen", ""),
            "wallet_balance": total_bal,
            "main_balance": main_bal,
            "bonus_balance": bonus_bal,
            "keys_count": len(keys),
            "total_topup": total_topup,
            # Loyalty points snapshot
            "points": int(points_rec.get("points", 0)),
            "points_streak": int(points_rec.get("streak_days", 0)),
            "points_redeemed_count": int(points_rec.get("redeemed_count", 0)),
            "points_lifetime_earned": int(points_rec.get("lifetime_earned", 0)),
            "points_has_topped_up": bool(points_rec.get("has_topped_up", False)),
        },
        "keys": keys,
        "purchases": purchases,
        "slips": slips,
        "redeems": redeems,
        "audit": audit,
        "points_ledger": points_ledger,
    }), 200


@admin_bp.route("/customers/<chat_id>/balance", methods=["POST"])
def adjust_customer_balance(chat_id):
    data = request.get_json(silent=True) or {}
    adj_type = data.get("adjustment_type", "TOPUP").upper()
    amount = int(data.get("amount_ks", 0))
    reason = data.get("reason", "Admin manual balance adjustment")

    if amount <= 0:
        return jsonify({"error": "Amount must be greater than 0"}), 400

    from bot_app.helpers.payment_text import (
        build_admin_deduct_notice,
        build_admin_topup_notice,
    )

    if adj_type == "TOPUP":
        new_balance, _ = update_user_balance(chat_id, amount)
        notice = build_admin_topup_notice(amount, new_balance, reason)
        # Manual admin credits grant points only when the owner explicitly
        # enables it in Settings (default OFF — comps are not customer
        # payments). Best-effort: a points failure must not fail the top-up.
        try:
            from bot_app.config import points_enabled, points_settings
            if points_enabled() and points_settings()["on_admin_topup"]:
                from bot_app.services.points import credit_points, topup_points_for
                credit_points(chat_id, topup_points_for(amount), "topup")
        except Exception:
            pass
    elif adj_type == "DEDUCT":
        from bot_app.services.billing import (
            admin_deduct_specific_funds,
            get_user_balance_breakdown,
        )

        # Guard against overdrawing: refuse to deduct more than the customer
        # currently holds instead of silently taking only what is available.
        _, _, current_total = get_user_balance_breakdown(chat_id)
        if amount > current_total:
            return jsonify({
                "error": f"လက်ကျန်ငွေ ({current_total:,} Ks) ထက် ပို၍ နှုတ်ယူ၍ မရပါ။"
            }), 400

        deducted, m_bal, b_bal, total_bal = admin_deduct_specific_funds(chat_id, amount, "all")
        new_balance = total_bal
        notice = build_admin_deduct_notice(amount, new_balance, reason)
    else:
        return jsonify({"error": "Invalid adjustment_type. Must be 'TOPUP' or 'DEDUCT'"}), 400

    # Notify the customer on Telegram. Skipped for admin targets (their balance
    # is a hardcoded sentinel, not a real wallet). Best-effort: a delivery
    # failure must not fail the adjustment the admin already committed.
    notified = False
    if str(chat_id) not in [str(aid) for aid in ADMIN_CHAT_IDS]:
        try:
            from bot_app.extensions import bot
            bot.send_message(chat_id, notice, parse_mode="HTML")
            notified = True
        except Exception:
            notified = False

    admin_id = current_admin_id()
    record_audit_log(
        admin_id=admin_id,
        action=f"BALANCE_{adj_type}",
        target_type="user",
        target_id=str(chat_id),
        details={"amount": amount, "new_balance": new_balance, "reason": reason},
    )

    return jsonify({
        "success": True,
        "chat_id": str(chat_id),
        "new_balance": new_balance,
        "notified": notified,
    }), 200


@admin_bp.route("/customers/<chat_id>/points", methods=["POST"])
def adjust_customer_points(chat_id):
    """Admin manual loyalty-points grant/deduct.

    Mirrors the balance-adjust contract: ``adjustment_type`` GRANT/DEDUCT +
    ``amount``. Grants respect the 20,000 cap (overflow discarded); deducts are
    floored at 0 and refuse to overdraw. Audited with the acting admin as actor.
    """
    from bot_app.services.points import admin_adjust_points, get_points

    data = request.get_json(silent=True) or {}
    adj_type = data.get("adjustment_type", "GRANT").upper()
    amount = int(data.get("amount", 0) or 0)
    reason = data.get("reason", "Admin manual points adjustment")

    if amount <= 0:
        return jsonify({"error": "Amount must be greater than 0"}), 400
    if adj_type not in ("GRANT", "DEDUCT"):
        return jsonify({"error": "Invalid adjustment_type. Must be 'GRANT' or 'DEDUCT'"}), 400

    if adj_type == "DEDUCT":
        current = int(get_points(chat_id).get("points", 0))
        if amount > current:
            return jsonify({
                "error": f"Points လက်ကျန် ({current:,}) ထက် ပို၍ နှုတ်ယူ၍ မရပါ။"
            }), 400

    delta = amount if adj_type == "GRANT" else -amount
    result = admin_adjust_points(chat_id, delta, admin_id=current_admin_id(), reason=reason)
    applied = int(result["applied"])

    # Notify the customer on Telegram, just like a wallet top-up/deduct. Skipped
    # for admin targets and no-op adjustments. Best-effort: a delivery failure
    # must not fail the adjustment the admin already committed.
    notified = False
    reason_line = f"\n📝 အကြောင်းအရာ: {reason}" if reason and reason != "Admin manual points adjustment" else ""
    if applied > 0:
        notice = (
            f"🎁 <b>Points ရရှိပါပြီ!</b>\n\n"
            f"Admin မှ လူကြီးမင်း၏ account သို့ Points ထည့်သွင်းပေးလိုက်ပါသည်။\n\n"
            f"➕ ရရှိသော Points: <b>+{applied:,}</b>\n"
            f"💎 လက်ရှိ Points: <b>{result['new_balance']:,}</b>{reason_line}\n\n"
            f"'🎁 Daily Reward' Menu မှ Points များ စစ်ဆေး၍ Starter Plan လဲယူနိုင်ပါသည်ခင်ဗျာ!"
        )
    elif applied < 0:
        notice = (
            f"⚠️ <b>Points ပြင်ဆင်မှု အသိပေးချက်</b>\n\n"
            f"Admin မှ လူကြီးမင်း၏ Points မှ ပြန်လည် နှုတ်ယူလိုက်ပါသည်။\n\n"
            f"➖ နှုတ်ယူ Points: <b>{abs(applied):,}</b>\n"
            f"💎 လက်ရှိ Points: <b>{result['new_balance']:,}</b>{reason_line}"
        )
    else:
        notice = ""

    if notice and str(chat_id) not in [str(aid) for aid in ADMIN_CHAT_IDS]:
        try:
            from bot_app.extensions import bot
            bot.send_message(chat_id, notice, parse_mode="HTML")
            notified = True
        except Exception:
            notified = False

    return jsonify({
        "success": True,
        "chat_id": str(chat_id),
        "new_balance": result["new_balance"],
        "applied": applied,
        "discarded": result["discarded"],
        "notified": notified,
    }), 200



# ---------------------------------------------------------------------------
# 6. Dynamic System Settings (Supabase-backed)
# ---------------------------------------------------------------------------
@admin_bp.route("/servers", methods=["GET"])
def list_servers():
    """Configured Outline servers (id + name only) for dashboard filters/forms.

    Mirrors exactly what the bot can use — servers whose API URL is configured
    in Settings (Supabase) or .env — so UI dropdowns can never offer a server
    that does not exist.
    """
    from bot_app.services.outline import get_configured_servers
    servers = [
        {"id": srv.get("id"), "name": srv.get("name") or f"Server {srv.get('id')}"}
        for srv in get_configured_servers()
    ]
    return jsonify({"servers": servers}), 200


@admin_bp.route("/settings", methods=["GET"])
def get_settings_endpoint():
    from bot_app.services.settings import get_system_settings
    return jsonify(get_system_settings()), 200


def _validate_points_settings(raw, current=None):
    """Strict guardrails for the dynamic Points economy block.

    Merges ``raw`` over ``current`` so partial updates keep prior values, then
    validates every field plus the cross-field rules (starter_cost ≤ cap,
    reward-table ranges within cap, etc). Returns ``(ok, error, normalized)``;
    on failure ``normalized`` is ``None``.
    """
    if not isinstance(raw, dict):
        return False, "points must be an object", None

    merged = {}
    if isinstance(current, dict):
        merged.update(current)
    merged.update(raw)

    def _get_int(key):
        try:
            return int(merged.get(key))
        except (TypeError, ValueError):
            return None

    cooldown = _get_int("claim_cooldown_h")
    if cooldown is None or not (1 <= cooldown <= 24):
        return False, "claim_cooldown_h must be an integer 1–24", None

    cap = _get_int("balance_cap")
    if cap is None or cap < 1:
        return False, "balance_cap must be an integer ≥ 1", None

    topup_rate = _get_int("topup_rate")
    if topup_rate is None or topup_rate < 1:
        return False, "topup_rate must be an integer ≥ 1", None

    topup_cap = _get_int("topup_cap")
    if topup_cap is None or topup_cap < 0:
        return False, "topup_cap must be an integer ≥ 0", None

    starter_cost = _get_int("starter_cost")
    if starter_cost is None or starter_cost < 1:
        return False, "starter_cost must be an integer ≥ 1", None
    if starter_cost > cap:
        return False, "starter_cost must be ≤ balance_cap", None

    streak_target = _get_int("streak_target_days")
    if streak_target is None or not (1 <= streak_target <= 30):
        return False, "streak_target_days must be an integer 1–30", None

    band = merged.get("streak_reward")
    if not (isinstance(band, (list, tuple)) and len(band) == 2):
        return False, "streak_reward must be [low, high]", None
    try:
        band_low, band_high = int(band[0]), int(band[1])
    except (TypeError, ValueError):
        return False, "streak_reward values must be integers", None
    if not (1 <= band_low <= band_high <= cap):
        return False, "streak_reward must satisfy 1 ≤ low ≤ high ≤ balance_cap", None

    table = merged.get("reward_table")
    if not (isinstance(table, list) and table):
        return False, "reward_table must be a non-empty list", None
    norm_table = []
    for row in table:
        if not (isinstance(row, (list, tuple)) and len(row) == 3):
            return False, "each reward_table row must be [low, high, weight]", None
        try:
            lo, hi, w = int(row[0]), int(row[1]), int(row[2])
        except (TypeError, ValueError):
            return False, "reward_table values must be integers", None
        if not (1 <= lo <= hi <= cap):
            return False, "reward_table row must satisfy 1 ≤ low ≤ high ≤ balance_cap", None
        if w <= 0:
            return False, "reward_table weight must be > 0", None
        norm_table.append([lo, hi, w])

    normalized = {
        "enabled": bool(merged.get("enabled", True)),
        "claim_cooldown_h": cooldown,
        "balance_cap": cap,
        "topup_rate": topup_rate,
        "topup_cap": topup_cap,
        "starter_cost": starter_cost,
        "streak_target_days": streak_target,
        "streak_reward": [band_low, band_high],
        "on_admin_topup": bool(merged.get("on_admin_topup", False)),
        "reward_table": norm_table,
    }
    return True, None, normalized


@admin_bp.route("/settings", methods=["POST"])
def update_settings_endpoint():
    from bot_app.services.settings import save_system_settings
    data = request.get_json(silent=True) or {}
    admin_id = current_admin_id()

    # Strict guardrails on the Points economy block before it reaches storage.
    if "points" in data:
        from bot_app.services.settings import get_system_settings
        current_points = get_system_settings().get("points") or {}
        ok, err, normalized = _validate_points_settings(data["points"], current_points)
        if not ok:
            return jsonify({"error": f"Invalid points settings: {err}"}), 400
        data = {**data, "points": normalized}

    updated = save_system_settings(data, updated_by=admin_id)
    # Server list / names may have changed — drop cached telemetry so the next
    # overview reflects the new configuration immediately.
    reset_telemetry_cache()
    record_audit_log(
        admin_id=admin_id,
        action="SETTINGS_UPDATE",
        target_type="system",
        target_id="settings",
        details={"updated_keys": list(data.keys())},
    )

    return jsonify({"success": True, "settings": updated}), 200


@admin_bp.route("/settings/test-server", methods=["POST"])
def test_server_endpoint():
    from bot_app.services.settings import test_outline_server
    data = request.get_json(silent=True) or {}
    url = data.get("api_url", "")
    result = test_outline_server(url)
    return jsonify(result), 200

