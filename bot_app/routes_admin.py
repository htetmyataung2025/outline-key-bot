"""Admin REST API routes for Control Center and Telegram Mini App."""

import json
import queue
from datetime import datetime, timedelta

import requests
from flask import Blueprint, Response, g, jsonify, request, stream_with_context

from bot_app.config import TELEGRAM_TOKEN
from bot_app.helpers.auth import require_admin_api
from bot_app.helpers.sse import consume_ticket, issue_ticket
from bot_app.services.admin_telemetry import get_admin_overview_telemetry, reset_telemetry_cache
from bot_app.storage import versioning
from bot_app.storage.versioning import get_data_version
from bot_app.services.billing import load_all_wallets, update_user_balance
from bot_app.services.orders import (
    load_all_users,
    load_redeem_codes,
    save_redeem_codes,
)
from bot_app.services.registry import load_persistent_keys, save_persistent_key, delete_persistent_key
from bot_app.services.slips import get_slip_by_id, get_slips_list, load_audit_logs, record_audit_log, review_slip
from bot_app.timeutil import myanmar_now
from bot_app.utils import generate_random_redeem_code

admin_bp = Blueprint("admin_bp", __name__, url_prefix="/api/admin")

# Route that authenticates with a one-time stream ticket instead of headers
# (EventSource cannot attach custom headers). Checked by endpoint name below.
SSE_STREAM_ENDPOINT = "admin_bp.sse_events"


# Apply authentication to all admin routes in blueprint
@admin_bp.before_request
def authenticate_admin():
    if request.endpoint == SSE_STREAM_ENDPOINT:
        admin = consume_ticket(request.args.get("ticket", ""))
        if not admin:
            return jsonify({"error": "Invalid or expired stream ticket"}), 401
        g.admin_user = admin
        return None
    return require_admin_api(lambda: None)()


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
    slip = get_slip_by_id(slip_id)
    if not slip:
        return jsonify({"error": "Slip not found"}), 404
    return jsonify(slip), 200


@admin_bp.route("/slips/<slip_id>/image", methods=["GET"])
def slip_image(slip_id):
    """Stream the receipt photo stored as a Telegram ``file_id``.

    The dashboard cannot put auth headers on a plain ``<img src>``, so the
    image is proxied through this authenticated endpoint and consumed as a
    blob. Telegram download links expire after ~1h, hence the per-request
    ``get_file`` call; the response is cached privately for an hour.
    """
    slip = get_slip_by_id(slip_id)
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

    admin_id = g.admin_user.get("id") if hasattr(g, "admin_user") else "admin"
    result = review_slip(slip_id, action=action, reviewed_by=admin_id, reason=reason)

    if not result.get("success"):
        return jsonify(result), result.get("code", 400)

    return jsonify(result), 200


# ---------------------------------------------------------------------------
# 3. Outline Access Keys Management
# ---------------------------------------------------------------------------
@admin_bp.route("/keys", methods=["GET"])
def list_keys():
    server_id = request.args.get("server_id")
    search = request.args.get("search", "").strip().lower()
    page = int(request.args.get("page", 1))
    page_size = int(request.args.get("page_size", 50))

    # Pull live keys from the Outline servers into the registry so the list shows
    # every key on the servers, not only the ones created through the dashboard.
    if request.args.get("sync", "1") != "0":
        try:
            from bot_app.services.outline import refresh_registry_from_servers
            refresh_registry_from_servers()
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

    admin_id = g.admin_user.get("id") if hasattr(g, "admin_user") else "admin"
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


    admin_id = g.admin_user.get("id") if hasattr(g, "admin_user") else "admin"
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

    admin_id = g.admin_user.get("id") if hasattr(g, "admin_user") else "admin"
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
        items.append(item)
    return jsonify(items), 200


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
        codes_data[code] = {
            "amount": amount_ks,
            "mode": mode,
            "valid_days": valid_days,
            "expires_at": exp_date,
            "created_at": now.strftime("%Y-%m-%d %H:%M:%S"),
            "is_active": True,
        }
        created_codes.append(code)

    save_redeem_codes(codes_data)

    admin_id = g.admin_user.get("id") if hasattr(g, "admin_user") else "admin"
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

    profiles = backfill_profiles_from_history()
    wallets = load_all_wallets()

    all_users = set(load_all_users())
    for uid in wallets.keys():
        all_users.add(str(uid))
    for uid in profiles.keys():
        all_users.add(str(uid))

    # Count Outline keys per user from the cached registry (no live server sync).
    keys_by_user = {}
    for k in load_persistent_keys().values():
        cid = str(k.get("chat_id") or "").strip()
        if cid:
            keys_by_user[cid] = keys_by_user.get(cid, 0) + 1

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

    uid = str(chat_id)
    backfill_profiles_from_history()
    profile = get_user_profile(uid)

    main_bal, bonus_bal, total_bal = get_user_balance_breakdown(uid)

    # Access keys (from cached registry, filtered to this user)
    keys = [
        k for k in load_persistent_keys().values()
        if str(k.get("chat_id") or "").strip() == uid
    ]

    # Purchase / plan history
    try:
        purchases = get_user_combined_purchase_records(uid)
    except Exception:
        purchases = []

    # Payment slips submitted by this user (newest first)
    slips = [s for s in get_slips_list() if str(s.get("chat_id")) == uid]

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
    for log in load_audit_logs():
        target_type = log.get("target_type")
        target_id = str(log.get("target_id", ""))
        details = log.get("details", {}) or {}
        if (
            (target_type == "user" and target_id == uid)
            or str(details.get("chat_id", "")) == uid
            or (target_type == "slip" and target_id in slip_ids)
        ):
            audit.append(log)
    audit.sort(key=lambda x: x.get("timestamp", ""), reverse=True)

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
        },
        "keys": keys,
        "purchases": purchases,
        "slips": slips,
        "redeems": redeems,
        "audit": audit,
    }), 200


@admin_bp.route("/customers/<chat_id>/balance", methods=["POST"])
def adjust_customer_balance(chat_id):
    data = request.get_json(silent=True) or {}
    adj_type = data.get("adjustment_type", "TOPUP").upper()
    amount = int(data.get("amount_ks", 0))
    reason = data.get("reason", "Admin manual balance adjustment")

    if amount <= 0:
        return jsonify({"error": "Amount must be greater than 0"}), 400

    if adj_type == "TOPUP":
        new_balance, _ = update_user_balance(chat_id, amount)
    elif adj_type == "DEDUCT":
        from bot_app.services.billing import admin_deduct_specific_funds
        deducted, m_bal, b_bal, total_bal = admin_deduct_specific_funds(chat_id, amount, "all")
        new_balance = total_bal
    else:
        return jsonify({"error": "Invalid adjustment_type. Must be 'TOPUP' or 'DEDUCT'"}), 400


    admin_id = g.admin_user.get("id") if hasattr(g, "admin_user") else "admin"
    record_audit_log(
        admin_id=admin_id,
        action=f"BALANCE_{adj_type}",
        target_type="user",
        target_id=str(chat_id),
        details={"amount": amount, "new_balance": new_balance, "reason": reason},
    )

    return jsonify({"success": True, "chat_id": str(chat_id), "new_balance": new_balance}), 200


# ---------------------------------------------------------------------------
# 6. Dynamic System Settings (Supabase-backed)
# ---------------------------------------------------------------------------
@admin_bp.route("/settings", methods=["GET"])
def get_settings_endpoint():
    from bot_app.services.settings import get_system_settings
    return jsonify(get_system_settings()), 200


@admin_bp.route("/settings", methods=["POST"])
def update_settings_endpoint():
    from bot_app.services.settings import save_system_settings
    data = request.get_json(silent=True) or {}
    admin_id = g.admin_user.get("id") if hasattr(g, "admin_user") else "admin"

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

