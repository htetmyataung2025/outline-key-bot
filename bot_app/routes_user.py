import json
import os
import queue
import random
import re
import string
from datetime import timedelta
from urllib.parse import unquote

from flask import Blueprint, jsonify, request, g, Response, stream_with_context
from werkzeug.utils import secure_filename
from telebot.types import InlineKeyboardButton, InlineKeyboardMarkup

from bot_app.config import ADMIN_CHAT_IDS, PLANS, points_enabled, points_settings
from bot_app.extensions import bot
from bot_app.helpers.auth import authenticate_user, current_user_id, require_user_api
from bot_app.helpers.sse import consume_ticket, issue_ticket
from bot_app.storage import versioning
from bot_app.storage.versioning import get_data_version
from bot_app.services.billing import get_user_balance_breakdown, update_user_balance
from bot_app.services.orders import (
    get_user_combined_purchase_records,
    save_key_mapping,
    save_sale_transaction,
    save_user_purchase_record,
)
from bot_app.services.outline import (
    _parse_expiry_from_name,
    create_outline_key,
    get_configured_servers,
    get_server_display_name,
)
from bot_app.services.points import (
    claim_cooldown_remaining,
    effective_streak,
    format_cooldown_remaining,
    get_points,
    try_claim,
)
from bot_app.services.leaderboard import build_leaderboard
from bot_app.services.points import load_all_points
from bot_app.services.profiles import load_all_profiles
from bot_app.services.slips import load_all_slips, record_slip
from bot_app.timeutil import myanmar_now

user_bp = Blueprint("user_bp", __name__, url_prefix="/api/user")

SSE_USER_STREAM_ENDPOINT = "user_bp.sse_user_events"

# Protect all routes under /api/user/* with Telegram WebApp initData auth
@user_bp.before_request
def auth_user():
    if request.endpoint == SSE_USER_STREAM_ENDPOINT:
        user_ticket = consume_ticket(request.args.get("ticket", ""))
        if not user_ticket:
            return jsonify({"error": "Invalid or expired stream ticket"}), 401
        g.current_user = user_ticket
        g.user_id = str(user_ticket.get("id", ""))
        return None
    return authenticate_user()



def _format_user_key(rec: dict, idx: int = 1) -> dict:
    vpn_key = rec.get("vpn_key", "")
    server_num = str(rec.get("server", "1"))
    plan_name = rec.get("plan_name", "VPN")
    order_id = rec.get("order_id", f"k_{idx}")
    disp_gb = rec.get("disp_gb", "50 GB")
    expire_date_str = rec.get("expire_date", "")

    quota = 50.0
    m = re.search(r"(\d+)\s*GB", str(disp_gb), re.IGNORECASE)
    if m:
        try:
            quota = float(m.group(1))
        except ValueError:
            quota = 50.0

    exp_dt = _parse_expiry_from_name(expire_date_str)
    now = myanmar_now()
    if exp_dt:
        days_left = (exp_dt.date() - now.date()).days
        if days_left < 0:
            status = "expired"
            left_text = "Expired"
        elif days_left <= 5:
            status = "expiring"
            left_text = f"{days_left} days left"
        else:
            status = "active"
            left_text = f"{days_left} days left"
        expires_display = exp_dt.strftime("%Y-%m-%d")
    else:
        status = "active"
        left_text = "Active"
        expires_display = expire_date_str or "N/A"

    canonical_plan = "Basic"
    for p in ("Starter", "Basic", "VIP", "Standard", "Premium", "Pro", "Ultimate"):
        if p.lower() in plan_name.lower():
            canonical_plan = p
            break

    location = "Singapore"
    country = "SG"
    if "tokyo" in server_num.lower() or server_num == "2":
        location = "Tokyo"
        country = "JP"
    elif "frankfurt" in server_num.lower() or server_num == "4":
        location = "Frankfurt"
        country = "DE"

    return {
        "id": order_id if order_id and order_id != "N/A" else f"k_{idx}",
        "server": f"Server {server_num}",
        "location": location,
        "country": country,
        "plan": canonical_plan,
        "quota": quota,
        "used": 0.0,
        "expires": expires_display,
        "left": left_text,
        "status": status,
        "connected": (status != "expired"),
        "key": vpn_key,
    }


@user_bp.route("/bootstrap", methods=["GET"])
def get_bootstrap():
    """Consolidated bootstrap payload for the Customer Mini App."""
    uid = current_user_id()
    user_info = getattr(g, "current_user", {}) or {}

    first_name = (user_info.get("first_name") or "").strip()
    last_name = (user_info.get("last_name") or "").strip()
    full_name = f"{first_name} {last_name}".strip() or user_info.get("username") or "Member"
    initials = "".join(part[0] for part in full_name.split()[:2] if part).upper() or "M"

    # Wallet & Balance
    main_bal, bonus_bal, total_bal = get_user_balance_breakdown(uid)

    # Points & Check-in
    points_rec = get_points(uid)
    cooldown = claim_cooldown_remaining(points_rec)
    cooldown_h = int(points_settings()["claim_cooldown_h"])
    points_val = int(points_rec.get("points", 0))
    streak_val = effective_streak(points_rec)
    can_claim = (cooldown == 0)
    claimed_today = (cooldown > 0)

    # Active & Expired Keys
    records = get_user_combined_purchase_records(uid)
    formatted_keys = [_format_user_key(rec, idx=i) for i, rec in enumerate(reversed(records), 1) if rec.get("vpn_key") and rec.get("vpn_key") != "N/A"]

    # Available Plans
    formatted_plans = []
    for code, p in PLANS.items():
        formatted_plans.append({
            "code": code,
            "name": p.get("name", code.capitalize()),
            "quota": p.get("data", "50 GB"),
            "price": p.get("price", 0),
            "description": f"{p.get('data')} / ၁ လစာ",
            "symbol": "zap" if "basic" in code else ("crown" if "vip" in code else "leaf"),
        })

    # Available Servers
    servers_list = []
    for srv in get_configured_servers():
        sid = str(srv.get("id"))
        servers_list.append({
            "id": sid,
            "name": get_server_display_name(sid),
            "location": "Singapore",
            "country": "SG",
            "flag": "🇸🇬",
        })

    # Payment Methods
    payment_methods = {
        "kbz": {
            "name": "KBZPay",
            "account_name": "Htet Myat Aung",
            "phone": "09699970092",
            "type": "QR / Direct Transfer"
        },
        "wave": {
            "name": "WavePay",
            "account_name": "Htet Myat Aung",
            "phone": "09699970092",
            "type": "QR / Direct Transfer"
        }
    }

    return jsonify({
        "user": {
            "id": uid,
            "name": full_name,
            "username": user_info.get("username", ""),
            "initials": initials,
        },
        "wallet": {
            "balance": total_bal,
            "main_balance": main_bal,
            "bonus_balance": bonus_bal,
            "points": points_val,
            "claimed_today": claimed_today,
            "can_claim": can_claim,
            "streak_days": streak_val,
            "cooldown_remaining": max(0, cooldown),
            "cooldown_hours": cooldown_h,
        },
        "keys": formatted_keys,
        "plans": formatted_plans,
        "servers": servers_list,
        "payment_methods": payment_methods,
    })


@user_bp.route("/events/ticket", methods=["POST"])
def user_sse_ticket():
    """Exchange authenticated Telegram initData session for an EventSource ticket."""
    return jsonify({"ticket": issue_ticket(getattr(g, "current_user", {}))}), 200


@user_bp.route("/events", methods=["GET"])
def sse_user_events():
    """Server-Sent Events stream for real-time customer data synchronization."""
    def stream():
        q = versioning.subscribe()
        try:
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


@user_bp.route("/version", methods=["GET"])
def get_user_version():
    """Lightweight data-version endpoint for cheap change detection."""
    return jsonify({"version": get_data_version()}), 200


@user_bp.route("/claim", methods=["POST"])
@user_bp.route("/claim-daily", methods=["POST"])
def claim_daily():
    """Reward point claim with dynamic cooldown hours configured by Admin."""
    if not points_enabled():
        return jsonify({"success": False, "error": "Daily Reward system is disabled"}), 400

    uid = current_user_id()
    res = try_claim(uid)
    cooldown_h = int(points_settings()["claim_cooldown_h"])

    if not res.get("ok"):
        err_type = res.get("error", "cooldown")
        next_in_s = res.get("next_in_s", 0)
        if err_type == "cooldown":
            time_str = format_cooldown_remaining(next_in_s)
            msg = f"⏳ နောက် Claim ရရှိရန် {time_str} ကျန်ပါသေးသည်။"
        else:
            msg = "⏳ ခဏစောင့်ပြီး ထပ်ကြိုးစားပေးပါ။"
        return jsonify({
            "success": False,
            "error": err_type,
            "next_in_s": next_in_s,
            "cooldown_hours": cooldown_h,
            "message": msg,
        }), 400

    awarded = res.get("awarded", 10)
    is_bonus = res.get("is_streak_bonus", False)
    streak_days = res.get("streak_days", 1)
    next_in_s = res.get("next_in_s", 0)

    if is_bonus:
        msg = f"🎉 +{awarded:,} Points ရရှိပါသည်! ({streak_days} ရက် ဆက်တိုက် Streak Bonus! 🔥)"
    else:
        msg = f"🎉 +{awarded:,} Points ရရှိပါသည်! ({cooldown_h} နာရီပြည့်ပါက ထပ်မံ Claim နိုင်ပါသည်)"

    return jsonify({
        "success": True,
        "awarded": awarded,
        "new_balance": res.get("new_balance", 0),
        "streak_days": streak_days,
        "is_streak_bonus": is_bonus,
        "next_in_s": next_in_s,
        "cooldown_hours": cooldown_h,
        "message": msg,
    })


@user_bp.route("/purchase", methods=["POST"])
def purchase_plan():
    """1-Click VPN Plan purchase using wallet balance."""
    uid = current_user_id()
    data = request.get_json(silent=True) or {}
    plan_code = (data.get("plan_code") or data.get("plan_name") or "").strip().lower()
    server_num = str(data.get("server_id") or "1").strip()

    plan = PLANS.get(plan_code)
    if not plan:
        for k, p in PLANS.items():
            if p.get("name", "").lower() == plan_code or k == plan_code:
                plan = p
                plan_code = k
                break

    if not plan:
        return jsonify({"success": False, "error": "Invalid plan selected"}), 400

    amount = plan["price"]
    is_admin_user = str(uid) in [str(aid) for aid in ADMIN_CHAT_IDS]

    _, _, total_bal = get_user_balance_breakdown(uid)
    if not is_admin_user and total_bal < amount:
        return jsonify({
            "success": False,
            "error": "insufficient_balance",
            "message": f"လက်ကျန်ငွေ မလုံလောက်ပါ။ ထပ်ဖြည့်ရန်: {amount - total_bal:,} Ks",
            "required": amount,
            "current": total_bal,
        }), 400

    order_id = "#" + "".join(random.choices(string.ascii_uppercase + string.digits, k=6))
    new_bal, used_bonus_days = update_user_balance(uid, -amount)

    user_info = getattr(g, "current_user", {}) or {}
    user_name = user_info.get("name") or user_info.get("first_name") or "HMA Customer"

    apply_days = None if is_admin_user else used_bonus_days
    disp_gb = plan["data"]

    try:
        vpn_key, key_name, expire_date = create_outline_key(
            server_num,
            user_name,
            plan_info=plan,
            target_chat_id=uid,
            months_count=1,
            custom_days=apply_days,
            is_giveaway=False,
            order_id=order_id,
        )
    except Exception as e:
        vpn_key = None

    if not vpn_key:
        # Automatic fail-safe refund
        update_user_balance(uid, amount)
        return jsonify({
            "success": False,
            "error": "server_unavailable",
            "message": "ဆာဗာလိုင်း မရရှိသဖြင့် ဝယ်ယူမှု မအောင်မြင်ပါ။ ငွေကို အလိုအလျောက် ပြန်လည် ထည့်သွင်းပေးထားပါသည်။",
        }), 502

    save_sale_transaction(server_num, uid, plan_code, plan['name'], 1, amount, order_id=order_id)
    save_user_purchase_record(
        chat_id=uid,
        order_id=order_id,
        plan_name=plan['name'],
        disp_gb=disp_gb,
        months_count=1,
        price_str=f"{amount:,} Ks",
        server_num=server_num,
        expire_date=expire_date,
        vpn_key=vpn_key,
    )
    save_key_mapping(user_name.strip().lower(), uid)

    return jsonify({
        "success": True,
        "order_id": order_id,
        "plan_name": plan['name'],
        "server": get_server_display_name(server_num),
        "disp_gb": disp_gb,
        "expire_date": expire_date,
        "vpn_key": vpn_key,
        "new_balance": new_bal,
        "message": "ဝယ်ယူမှု အောင်မြင်ပါသည်ခင်ဗျာ!",
    })


@user_bp.route("/topup-slip", methods=["POST"])
def upload_topup_slip():
    """Submit payment screenshot slip for verification."""
    uid = current_user_id()
    amount_str = request.form.get("amount") or (request.get_json(silent=True) or {}).get("amount", "0")
    try:
        amount = int(re.sub(r"[^\d]", "", str(amount_str)))
    except (ValueError, TypeError):
        amount = 0

    if amount < 500:
        return jsonify({"success": False, "error": "Minimum top-up amount is 500 Ks"}), 400

    slip_id = "".join(random.choices(string.ascii_uppercase + string.digits, k=8))
    user_info = getattr(g, "current_user", {}) or {}
    username = user_info.get("username") or user_info.get("name") or "MiniAppUser"

    # Image upload handling
    image_url = ""
    file = request.files.get("file") or request.files.get("receipt")
    file_bytes = None
    if file and file.filename:
        filename = secure_filename(file.filename)
        image_url = f"upload_{filename}"
        try:
            file_bytes = file.read()
        except Exception:
            file_bytes = None

    admin_alert_text = (
        f"📥 <b>Mini App Top-Up Slip အသစ် ရောက်ရှိပါသည်!</b>\n\n"
        f"🧾 <b>Top-Up ID:</b> <code>{slip_id}</code>\n"
        f"👤 <b>Customer:</b> @{username} (<code>{uid}</code>)\n"
        f"💵 <b>ပမာဏ:</b> <code>{amount:,} Ks</code>\n\n"
        f"<i>စစ်ဆေးပြီးပါက အောက်ပါ Approve / Reject ခလုတ်များဖြင့် သတ်မှတ်ပေးပါခင်ဗျာ။</i>"
    )

    markup = InlineKeyboardMarkup()
    markup.add(InlineKeyboardButton(f"✅ Approve (+{amount:,} MMK)", callback_data=f"approve_topup_{uid}_{amount}_{slip_id}"))
    markup.add(InlineKeyboardButton("❌ Reject", callback_data=f"reject_topup_{slip_id}"))

    admin_messages = []
    captured_file_id = ""

    # Notify admins on Telegram with photo and inline approve/reject buttons
    for aid in ADMIN_CHAT_IDS:
        sent = None
        try:
            if file_bytes:
                sent = bot.send_photo(
                    aid,
                    file_bytes,
                    caption=admin_alert_text,
                    parse_mode="HTML",
                    reply_markup=markup,
                )
            else:
                sent = bot.send_message(
                    aid,
                    admin_alert_text,
                    parse_mode="HTML",
                    reply_markup=markup,
                )
        except Exception:
            try:
                sent = bot.send_message(
                    aid,
                    admin_alert_text,
                    parse_mode="HTML",
                    reply_markup=markup,
                )
            except Exception:
                pass

        if sent is not None:
            admin_messages.append({"chat_id": sent.chat.id, "message_id": sent.message_id})
            if not captured_file_id and getattr(sent, "photo", None):
                captured_file_id = sent.photo[-1].file_id

    method = (request.form.get("method") or (request.get_json(silent=True) or {}).get("method") or "kbz").strip().upper()

    slip_record = record_slip(
        slip_id=slip_id,
        chat_id=uid,
        amount=amount,
        username=username,
        image_url=image_url,
        file_id=captured_file_id,
        admin_messages=admin_messages,
        admin_caption=admin_alert_text,
        method=method,
    )

    return jsonify({
        "success": True,
        "slip_id": slip_id,
        "status": "PENDING",
        "amount": amount,
        "method": method,
        "message": "ပြေစာ လက်ခံရရှိပြီးဖြစ်ပါသည်ခင်ဗျာ။ Admin မှ မကြာမီ စစ်ဆေးအတည်ပြုပေးပါမည်။",
    })


@user_bp.route("/keys/<path:key_id>/replace", methods=["POST"])
def replace_key(key_id):
    """Submit key replacement request to admin review queue."""
    uid = current_user_id()
    key_id = unquote(key_id).strip()
    records = get_user_combined_purchase_records(uid)
    matched_rec = None
    for rec in records:
        if rec.get("order_id") == key_id or rec.get("vpn_key") == key_id or key_id in str(rec.get("order_id", "")):
            matched_rec = rec
            break

    if not matched_rec:
        return jsonify({"success": False, "error": "VPN key record not found"}), 404

    # Check expiry
    exp_date_str = matched_rec.get("expire_date", "")
    exp_dt = _parse_expiry_from_name(exp_date_str)
    if exp_dt and exp_dt.date() < myanmar_now().date():
        return jsonify({
            "success": False,
            "error": "expired",
            "message": "သက်တမ်းကုန်ဆုံးသွားသော Key အား လဲလှယ်၍ မရနိုင်ပါ။ Plan အသစ် ဝယ်ယူပေးပါရန်။"
        }), 400

    # Notify admins
    for aid in ADMIN_CHAT_IDS:
        try:
            bot.send_message(
                aid,
                f"♻️ <b>Mini App မှ Key အစားထိုး လဲလှယ်မှု တောင်းဆိုချက်:</b>\n\n"
                f"👤 <b>Customer ID:</b> <code>{uid}</code>\n"
                f"🧾 <b>Order ID:</b> <code>{matched_rec.get('order_id')}</code>\n"
                f"📡 <b>Server:</b> Server {matched_rec.get('server')}\n"
                f"⏰ <b>Expiry:</b> {exp_date_str}\n"
                f"🔑 <b>Key:</b> <code>{matched_rec.get('vpn_key')}</code>",
                parse_mode="HTML"
            )
        except Exception:
            pass

    return jsonify({
        "success": True,
        "message": "Key အစားထိုး လဲလှယ်ရန် Admin ထံ တောင်းဆိုမှု ပို့ဆောင်ပြီးပါပြီခင်ဗျာ။",
    })


@user_bp.route("/history", methods=["GET"])
def get_history():
    """Retrieve customer purchase and top-up slip history."""
    uid = current_user_id()
    records = get_user_combined_purchase_records(uid)
    all_slips = load_all_slips()
    user_slips = [s for s in all_slips.values() if str(s.get("chat_id")) == str(uid)]

    formatted_purchases = []
    for rec in reversed(records):
        formatted_purchases.append({
            "order_id": rec.get("order_id") or "N/A",
            "plan_name": rec.get("plan_name") or "VPN Plan",
            "disp_gb": rec.get("disp_gb") or "",
            "price": rec.get("price_str") or f"{rec.get('price', 0):,} Ks",
            "date": rec.get("timestamp") or rec.get("date") or "Recent",
            "status": "Active" if rec.get("status") != "expired" else "Expired",
        })

    formatted_slips = []
    for s in reversed(user_slips):
        formatted_slips.append({
            "slip_id": s.get("id") or s.get("slip_id") or "",
            "amount": int(s.get("amount") or 0),
            "method": str(s.get("method") or "KBZ").upper(),
            "status": str(s.get("status") or "PENDING").upper(),
            "submitted_at": s.get("created_at") or s.get("submitted_at") or "Recent",
        })

    return jsonify({
        "purchases": formatted_purchases,
        "slips": formatted_slips,
    })


@user_bp.route("/leaderboard", methods=["GET"])
def get_leaderboard():
    """Retrieve customer points leaderboard."""
    uid = current_user_id()
    board = build_leaderboard(load_all_points(), load_all_profiles(), "7d", uid, myanmar_now())

    formatted_rows = []
    for r in board.get("rows", []):
        formatted_rows.append({
            "rank": r.get("rank"),
            "name": r.get("name"),
            "points": r.get("score", 0),
            "is_you": bool(r.get("is_me")),
        })

    me_info = board.get("me")
    formatted_me = None
    if me_info:
        formatted_me = {
            "rank": me_info.get("rank"),
            "name": me_info.get("name"),
            "points": me_info.get("score", 0),
        }

    return jsonify({
        "rows": formatted_rows,
        "me": formatted_me,
        "mode": board.get("mode", "7d"),
    })
