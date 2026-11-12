import json
import queue
import random
import re
import string
from urllib.parse import unquote

from flask import Blueprint, jsonify, request, g, Response, stream_with_context
from werkzeug.utils import secure_filename
from telebot.types import InlineKeyboardButton, InlineKeyboardMarkup

from bot_app.config import ADMIN_CHAT_IDS, PLANS, points_enabled, points_settings
from bot_app.extensions import bot
from bot_app.helpers.auth import authenticate_user, current_user_id
from bot_app.helpers.sse import consume_ticket, issue_ticket
from bot_app.storage import versioning
from bot_app.storage.versioning import get_data_version
from bot_app.services.billing import (
    add_expiring_bonus_to_wallet,
    get_user_balance_breakdown,
    update_user_balance,
)
from bot_app.services.orders import (
    get_user_combined_purchase_records,
    is_code_expired,
    load_redeem_codes,
    save_key_mapping,
    save_redeem_codes,
    save_sale_transaction,
    save_user_purchase_record,
)
from bot_app.services.outline import (
    _parse_expiry_from_name,
    create_outline_key,
    get_configured_servers,
    get_server_display_name,
    get_usage_by_server,
    renew_or_create_unlimited_key,
)
from bot_app.services.points import (
    claim_cooldown_remaining,
    effective_streak,
    format_cooldown_remaining,
    get_points,
    redeem_starter,
    refund_starter,
    try_claim,
)
from bot_app.services.registry import load_persistent_keys
from bot_app.utils import bytes_to_gb, clean_ss_url
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



def _format_user_key(rec: dict, idx: int = 1, usage_by_server: dict = None, url_to_key: dict = None) -> dict:
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

    used_gb = 0.0
    if usage_by_server and vpn_key:
        k_clean = clean_ss_url(vpn_key)
        target_sid = server_num
        target_kid = str(rec.get("key_id") or "")
        if (not target_kid or target_kid == "N/A") and url_to_key and k_clean in url_to_key:
            target_sid, target_kid = url_to_key[k_clean]
        if target_kid and target_sid in usage_by_server:
            b_val = usage_by_server[target_sid].get(target_kid, 0)
            if b_val:
                used_gb = bytes_to_gb(b_val)

    return {
        "id": order_id if order_id and order_id != "N/A" else f"k_{idx}",
        "server": f"Server {server_num}",
        "location": location,
        "country": country,
        "plan": canonical_plan,
        "quota": quota,
        "used": used_gb,
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

    # Fetch user data concurrently in parallel threads
    import concurrent.futures

    with concurrent.futures.ThreadPoolExecutor(max_workers=4) as executor:
        fut_balance = executor.submit(get_user_balance_breakdown, uid)
        fut_points = executor.submit(get_points, uid)
        fut_records = executor.submit(get_user_combined_purchase_records, uid)
        fut_servers = executor.submit(get_configured_servers)

        main_bal, bonus_bal, total_bal = fut_balance.result()
        points_rec = fut_points.result()
        records = fut_records.result()
        configured_servers = fut_servers.result()

    # Points & Check-in
    cooldown = claim_cooldown_remaining(points_rec)
    cooldown_h = int(points_settings()["claim_cooldown_h"])
    points_val = int(points_rec.get("points", 0))
    streak_val = effective_streak(points_rec)
    can_claim = (cooldown == 0)
    claimed_today = (cooldown > 0)
    starter_cost = int(points_settings()["starter_cost"])
    has_topped_up = bool(points_rec.get("has_topped_up"))
    can_redeem_points = bool(has_topped_up and points_val >= starter_cost)

    # Active & Expired Keys with real Outline usage
    persistent_reg = load_persistent_keys()
    url_to_key = {}
    servers_needed = set()
    for k_val in persistent_reg.values():
        k_url = clean_ss_url(k_val.get("access_url", ""))
        if k_url:
            s_num = str(k_val.get("server", "1"))
            kid = str(k_val.get("key_id", ""))
            url_to_key[k_url] = (s_num, kid)

    for rec in records:
        k_url = clean_ss_url(rec.get("vpn_key", ""))
        if k_url in url_to_key:
            servers_needed.add(url_to_key[k_url][0])
        elif rec.get("server"):
            servers_needed.add(str(rec.get("server")))

    usage_data = {}
    if servers_needed:
        try:
            if request.args.get("refresh") == "1":
                usage_data = get_usage_by_server(servers_needed, force=True)
            else:
                usage_data = get_usage_by_server(servers_needed)
        except TypeError:
            usage_data = get_usage_by_server(servers_needed)
        except Exception:
            usage_data = {}

    formatted_keys = [
        _format_user_key(rec, idx=i, usage_by_server=usage_data, url_to_key=url_to_key)
        for i, rec in enumerate(reversed(records), 1)
        if rec.get("vpn_key") and rec.get("vpn_key") != "N/A"
    ]

    # Available Plans
    formatted_plans = []
    for code, p in PLANS.items():
        months = int(p.get("months", 1) or 1)
        formatted_plans.append({
            "code": code,
            "name": p.get("name", code.capitalize()),
            "quota": p.get("data", "50 GB"),
            "price": p.get("price", 0),
            "description": f"{p.get('data')} / {months} လစာ",
            "symbol": "zap" if "basic" in code else ("crown" if "vip" in code else "leaf"),
            "manual": bool(p.get("manual", False)),
            "months": months,
        })

    # Available Servers
    servers_list = []
    for srv in configured_servers:
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
            "starter_cost": starter_cost,
            "has_topped_up": has_topped_up,
            "can_redeem_points": can_redeem_points,
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

    main_bal, bonus_bal, total_bal = get_user_balance_breakdown(uid)
    if not is_admin_user and total_bal < amount:
        return jsonify({
            "success": False,
            "error": "insufficient_balance",
            "message": f"လက်ကျန်ငွေ မလုံလောက်ပါ။ ထပ်ဖြည့်ရန်: {amount - total_bal:,} Ks",
            "required": amount,
            "current": total_bal,
        }), 400

    # If customer has expiring redeem credit, force server 1 (SG-1) like bot
    has_redeem_credit = (bonus_bal > 0) and not is_admin_user
    if has_redeem_credit:
        server_num = "1"

    order_id = "#" + "".join(random.choices(string.ascii_uppercase + string.digits, k=6))
    new_bal, used_bonus_days = update_user_balance(uid, -amount)

    user_info = getattr(g, "current_user", {}) or {}
    user_name = user_info.get("name") or user_info.get("first_name") or "HMA Customer"

    apply_days = None if is_admin_user else used_bonus_days
    disp_gb = plan.get("data", "50 GB")

    # Handle manual plan (e.g. 5-device custom plan)
    if plan.get("manual"):
        save_sale_transaction("VIP", uid, plan_code, plan["name"], plan.get("months", 1), amount, order_id=order_id)
        admin_alert = (
            f"⚡ <b>စိတ်ကြိုက်သုံး 5 Device Plan အော်ဒါအသစ် (Mini App - ငွေပေးချေပြီး)</b>\n\n"
            f"🧾 Order ID: <code>{order_id}</code>\n"
            f"👤 ဝယ်ယူသူ: {user_name}\n"
            f"🆔 Chat ID: <code>{uid}</code>\n"
            f"🛍️ Plan: <b>{plan['name']}</b>\n"
            f"💵 ဖြတ်တောက်ပြီးငွေ: <b>{amount:,} MMK</b>\n\n"
            f"👇 အောက်ပါခလုတ်ကိုနှိပ်၍ Key အား ပေးပို့ပေးပါခင်ဗျာ:"
        )
        markup = InlineKeyboardMarkup()
        markup.add(InlineKeyboardButton("🔑 Send Key to Customer", callback_data=f"ask_send_key_{uid}_{order_id}"))

        for aid in ADMIN_CHAT_IDS:
            try:
                bot.send_message(aid, admin_alert, parse_mode="HTML", reply_markup=markup)
            except Exception:
                pass

        user_disp_bal = "♾️" if is_admin_user else f"{new_bal:,} MMK"
        user_msg = (
            f"🎉 <b>အော်ဒါမှာယူမှု အောင်မြင်ပါသည်! (Mini App)</b>\n\n"
            f"🧾 <b>Order ID:</b> <code>{order_id}</code>\n\n"
            f"🛍️ <b>Plan:</b> {plan['name']}\n"
            f"💵 <b>ကျသင့်ငွေ:</b> -{amount:,} MMK\n"
            f"💳 <b>လက်ကျန်ငွေ:</b> {user_disp_bal}\n\n"
            f"💡 <i>ဤ Plan သည် စိတ်ကြိုက်သုံး 5 Device Plan ဖြစ်သဖြင့် Admin မှ ခေတ္တအတွင်း Key အား ပြင်ဆင်၍ ပို့ပေးပါမည်ခင်ဗျာ။</i>"
        )
        try:
            bot.send_message(uid, user_msg, parse_mode="HTML")
        except Exception:
            pass

        return jsonify({
            "success": True,
            "order_id": order_id,
            "plan_name": plan['name'],
            "server": "VIP Server",
            "disp_gb": disp_gb,
            "expire_date": "Admin မှ ထည့်သွင်းပေးပါမည်",
            "vpn_key": "",
            "manual": True,
            "new_balance": new_bal,
            "remaining_balance": new_bal,
            "key_details": None,
            "message": "အော်ဒါမှာယူမှု အောင်မြင်ပါသည်။ ဤ Plan သည် စိတ်ကြိုက်သုံး 5 Device Plan ဖြစ်သဖြင့် Admin မှ ခေတ္တအတွင်း Key အား ပို့ပေးပါမည်ခင်ဗျာ။",
        })

    # Auto key minting
    vpn_key = None
    key_name = None
    expire_date = None
    try:
        if plan_code == "ultimate":
            vpn_key, key_name, expire_date, _ = renew_or_create_unlimited_key(
                server_num, user_name, uid, months_count=1, custom_days=apply_days, order_id=order_id
            )
        else:
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
    except Exception:
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

    key_rec = {
        "timestamp": myanmar_now().strftime("%d/%m/%Y (%I:%M %p)"),
        "order_id": order_id,
        "plan_name": plan['name'],
        "disp_gb": disp_gb,
        "months": 1,
        "price_str": f"{amount:,} Ks",
        "server": str(server_num),
        "expire_date": expire_date,
        "vpn_key": vpn_key,
    }
    key_details = _format_user_key(key_rec, idx=1)

    # Deliver key via Telegram bot chat
    try:
        from bot_app.helpers.deeplink import get_key_delivery_markup
        exp_info_text = f"⏰ <b>သက်တမ်းကုန်ဆုံးရက်:</b> {expire_date}"
        if apply_days:
            exp_info_text += f" <i>(Redeem Wallet ငွေအလိုက် {apply_days} ရက် သက်တမ်း)</i>"
        user_disp_bal = "♾️" if is_admin_user else f"{new_bal:,} MMK"
        success_text = (
            f"🎉 <b>ဝယ်ယူမှု အောင်မြင်ပါသည်ခင်ဗျာ! (Mini App)</b>\n\n"
            f"🧾 <b>Order ID:</b> <code>{order_id}</code>\n\n"
            f"🛍️ <b>Plan:</b> {plan['name']} ({disp_gb})\n\n"
            f"📡 <b>Server:</b> {get_server_display_name(server_num)}\n\n"
            f"{exp_info_text}\n\n"
            f"💳 <b>ကျန်ရှိသော လက်ကျန်ငွေ:</b> <code>{user_disp_bal}</code>\n\n"
            f"🔑 <b>လူကြီးမင်း၏ VPN Key:</b>\n\n"
            f"<code>{vpn_key}</code>\n\n"
            f"☝️ Key ကို တစ်ချက်နှိပ်ရုံဖြင့် Auto Copy ကူးနိုင်သလို၊ အောက်က Button များကို နှိပ်ပြီးလည်း တိုက်ရိုက်ထည့်သွင်း အသုံးပြုနိုင်ပါပြီခင်ဗျာ။"
        )
        bot.send_message(uid, success_text, parse_mode="HTML", reply_markup=get_key_delivery_markup(vpn_key))
    except Exception:
        pass

    for aid in ADMIN_CHAT_IDS:
        try:
            bot.send_message(
                aid,
                f"🛍️ <b>Mini App မှ ကီးဝယ်ယူမှု:</b>\n\n"
                f"🧾 Order ID: <code>{order_id}</code>\n"
                f"👤 Customer: {user_name} (ID: <code>{uid}</code>)\n"
                f"🛍️ Plan: {plan['name']}\n"
                f"📡 Server: {get_server_display_name(server_num)}\n"
                f"💵 ရရှိငွေ: {amount:,} MMK\n"
                f"⏰ သက်တမ်း: {expire_date} ({f'Redeem ငွေဖြင့် {apply_days} ရက်' if apply_days else '၁လစာ'})",
                parse_mode="HTML",
            )
        except Exception:
            pass

    return jsonify({
        "success": True,
        "order_id": order_id,
        "plan_name": plan['name'],
        "server": get_server_display_name(server_num),
        "disp_gb": disp_gb,
        "expire_date": expire_date,
        "vpn_key": vpn_key,
        "new_balance": new_bal,
        "remaining_balance": new_bal,
        "key_details": key_details,
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

    record_slip(
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

    server_num = str(matched_rec.get("server") or "1")
    vpn_key = matched_rec.get("vpn_key", "")
    full_name = matched_rec.get("plan_name", "HMA User")

    # Match key in persistent_keys_registry to find outline key id and remaining GB
    persistent_reg = load_persistent_keys()
    outline_key_id = "0"
    limit_b = None
    for k_val in persistent_reg.values():
        if clean_ss_url(k_val.get("access_url", "")) == clean_ss_url(vpn_key) or k_val.get("order_id") == matched_rec.get("order_id"):
            outline_key_id = str(k_val.get("key_id", "0"))
            server_num = str(k_val.get("server", server_num))
            limit_b = k_val.get("limit_bytes")
            if k_val.get("name"):
                full_name = k_val["name"]
            break

    total_gb = bytes_to_gb(limit_b) if limit_b else 50.0
    rem_gb = total_gb

    date_match = re.search(r'\d{1,2}\.\d{1,2}\.(\d{4}|\d{2})', exp_date_str)
    exp_date = date_match.group(0) if date_match else exp_date_str

    alert_text = (
        f"♻️ <b>KEY REPLACEMENT REQUEST (Mini App)</b>\n\n"
        f"👤 Customer: <code>{uid}</code>\n"
        f"🧾 Order ID: <code>{matched_rec.get('order_id')}</code>\n"
        f"📡 Server: Server {server_num}\n"
        f"🔑 Key အဟောင်း: {full_name}\n"
        f"🧰 ကျန်ရှိ Data: <b>{rem_gb} GB</b> / {total_gb} GB\n"
        f"⏰ သက်တမ်းကုန်ရက်: <b>{exp_date}</b>"
    )

    markup = InlineKeyboardMarkup()
    target_servers = get_configured_servers()
    if target_servers:
        for srv in target_servers:
            sid = str(srv.get("id"))
            btn_label = f"📡 {get_server_display_name(sid)} သို့"
            markup.add(InlineKeyboardButton(btn_label, callback_data=f"replace_srv{sid}_{server_num}_{outline_key_id}_{uid}_{rem_gb}_{exp_date}"))
    markup.row(InlineKeyboardButton("❌ Reject", callback_data=f"replace_reject_{uid}_{outline_key_id}"))

    # Notify admins
    for aid in ADMIN_CHAT_IDS:
        try:
            bot.send_message(
                aid,
                alert_text,
                parse_mode="HTML",
                reply_markup=markup
            )
        except Exception:
            pass

    return jsonify({
        "success": True,
        "message": "Key အစားထိုး လဲလှယ်ရန် Admin ထံ တောင်းဆိုမှု ပို့ဆောင်ပြီးပါပြီခင်ဗျာ။",
    })


@user_bp.route("/redeem-points", methods=["POST"])
def redeem_points():
    """Redeem loyalty points for a Starter Plan key (25GB / 30 days)."""
    if not points_enabled():
        return jsonify({"success": False, "error": "Points system is disabled", "message": "Points စနစ်ကို ယာယီ ပိတ်ထားပါသည်။"}), 400

    uid = current_user_id()
    res = redeem_starter(uid)
    if not res.get("ok"):
        error = res.get("error")
        if error == "needs_topup":
            msg = "🔒 လဲယူရန် အနည်းဆုံး တစ်ကြိမ် ငွေဖြည့်ရန် လိုအပ်ပါသည်။"
        elif error == "insufficient_points":
            msg = "❌ Points မလုံလောက်ပါ။"
        else:
            msg = "❌ လဲယူ၍ မရနိုင်သေးပါ။"
        return jsonify({"success": False, "error": error, "message": msg}), 400

    order_id = "PTS-" + "".join(random.choices(string.ascii_uppercase + string.digits, k=6))
    user_info = getattr(g, "current_user", {}) or {}
    user_name = user_info.get("name") or user_info.get("first_name") or "HMA Customer"
    plan = PLANS.get("starter") or {"name": "Starter Plan", "data": "25 GB", "bytes": 25 * 1000**3}

    vpn_key = key_name = expire_date = None
    try:
        vpn_key, key_name, expire_date = create_outline_key(
            "1", user_name, plan_info=plan, target_chat_id=uid,
            custom_days=30, is_giveaway=True, order_id=order_id,
        )
    except Exception:
        vpn_key = None

    if not vpn_key:
        refund = refund_starter(uid)
        return jsonify({
            "success": False,
            "error": "server_unavailable",
            "new_points": refund.get("new_balance", 0),
            "message": "ဆာဗာလိုင်း မရရှိသဖြင့် မအောင်မြင်ပါ။ သုံးထားသော Points များကို ပြန်လည် ထည့်သွင်းပေးထားပါသည်။",
        }), 502

    save_user_purchase_record(
        chat_id=uid, order_id=order_id, plan_name=f"{plan['name']} (Points Reward)",
        disp_gb=plan.get("data", "25 GB"), months_count=1, price_str="0 Ks (Points)",
        server_num="1", expire_date=expire_date, vpn_key=vpn_key,
    )
    save_key_mapping(user_name.strip().lower(), uid)

    key_rec = {
        "timestamp": myanmar_now().strftime("%d/%m/%Y (%I:%M %p)"),
        "order_id": order_id,
        "plan_name": plan['name'],
        "disp_gb": plan.get("data", "25 GB"),
        "months": 1,
        "price_str": "0 Ks (Points)",
        "server": "1",
        "expire_date": expire_date,
        "vpn_key": vpn_key,
    }
    key_details = _format_user_key(key_rec, idx=1)

    try:
        from bot_app.helpers.deeplink import get_key_delivery_markup
        bot.send_message(
            uid,
            f"🎉 <b>Points ဖြင့် Starter Plan လဲယူမှု အောင်မြင်ပါသည်! (Mini App)</b>\n\n"
            f"🧾 Order ID: <code>{order_id}</code>\n"
            f"🛍️ Plan: {plan['name']} (25 GB)\n"
            f"📡 Server: {get_server_display_name('1')}\n"
            f"⏰ သက်တမ်း: {expire_date}\n"
            f"💎 ကျန်ရှိ Points: {res.get('new_balance', 0):,}\n\n"
            f"🔑 <b>လူကြီးမင်း၏ VPN Key:</b>\n<code>{vpn_key}</code>\n\n"
            f"☝️ Key ကို တစ်ချက်နှိပ်ရုံဖြင့် Auto Copy ကူးနိုင်သလို၊ အောက်က Button များကို နှိပ်ပြီးလည်း တိုက်ရိုက်ထည့်သွင်း အသုံးပြုနိုင်ပါပြီခင်ဗျာ။",
            parse_mode="HTML",
            reply_markup=get_key_delivery_markup(vpn_key),
        )
    except Exception:
        pass

    return jsonify({
        "success": True,
        "order_id": order_id,
        "vpn_key": vpn_key,
        "expire_date": expire_date,
        "new_points": res.get("new_balance", 0),
        "key_details": key_details,
        "message": "Points ဖြင့် Starter Plan လဲယူမှု အောင်မြင်ပါသည်ခင်ဗျာ!",
    })


@user_bp.route("/redeem-code", methods=["POST"])
def redeem_promo_code():
    """Redeem promo / gift wallet balance code."""
    uid = current_user_id()
    data = request.get_json(silent=True) or {}
    code_input = (data.get("code") or "").strip().lower()

    if not code_input:
        return jsonify({"success": False, "error": "missing_code", "message": "Redeem Code ထည့်သွင်းပေးပါခင်ဗျာ။"}), 400

    is_admin = str(uid) in [str(aid) for aid in ADMIN_CHAT_IDS]
    if not is_admin:
        _, bonus_bal, _ = get_user_balance_breakdown(uid)
        if bonus_bal > 0:
            return jsonify({
                "success": False,
                "error": "existing_bonus",
                "message": f"လူကြီးမင်းတွင် လက်ရှိ အသုံးပြုနိုင်သော Redeem Bonus လက်ကျန်ငွေ ({bonus_bal:,} MMK) ရှိနေဆဲ ဖြစ်ပါသဖြင့် နောက်ထပ် Code အသစ်ကို ထပ်မံ ရယူခွင့် မရှိသေးပါခင်ဗျာ။",
            }), 400

    codes = load_redeem_codes()
    matched_code_key = None
    for c_k in codes.keys():
        if c_k.strip().lower() == code_input:
            matched_code_key = c_k
            break

    if not matched_code_key:
        return jsonify({
            "success": False,
            "error": "invalid_code",
            "message": "ထည့်သွင်းထားသော Redeem Code မှားယွင်းနေပါသည် (သို့မဟုတ်) အသုံးပြုပြီးသား ဖြစ်နေပါသည်ခင်ဗျာ။",
        }), 400

    code_info = codes[matched_code_key]
    if is_code_expired(code_info):
        return jsonify({
            "success": False,
            "error": "code_expired",
            "message": f"ဤ Code ၏ သက်တမ်း ကုန်ဆုံးသွားပါပြီ (ကုန်ဆုံးရက်: {code_info.get('expires_at')})",
        }), 400

    validity_days = int(code_info.get("validity_days", 1))
    mode = code_info.get("mode", "single")
    user_str_id = str(uid)
    claimed_users = code_info.get("claimed_users", [])

    if mode == "shared":
        if not is_admin and user_str_id in claimed_users:
            return jsonify({
                "success": False,
                "error": "already_claimed",
                "message": "သင်သည် ဤ Code အား ရယူပြီးဖြစ်ပါသည်ခင်ဗျာ။ (Code တစ်ခုလျှင် လူတစ်ဦး ၁ ကြိမ်သာ ရယူနိုင်ပါသည်)",
            }), 400

        remaining = int(code_info.get("remaining", 0))
        if remaining < 500:
            del codes[matched_code_key]
            save_redeem_codes(codes)
            return jsonify({
                "success": False,
                "error": "code_exhausted",
                "message": "ဤ Code ၏ သတ်မှတ်ထားသော ပမာဏ ပြည့်သွားပါပြီဖြစ်၍ အသုံးပြု၍ မရတော့ပါခင်ဗျာ။",
            }), 400

        possible_amounts = [1000, 2000, 3000]
        valid_options = [opt for opt in possible_amounts if opt <= remaining]
        if not valid_options:
            awarded_amt = remaining
        else:
            weights = [70, 20, 10][:len(valid_options)]
            awarded_amt = random.choices(valid_options, weights=weights, k=1)[0]

        new_balance, exp_disp = add_expiring_bonus_to_wallet(uid, awarded_amt, validity_days)
        remaining -= awarded_amt
        claimed_users.append(user_str_id)
        code_info["remaining"] = remaining
        code_info["claimed_users"] = claimed_users

        if remaining < 500:
            del codes[matched_code_key]
        else:
            codes[matched_code_key] = code_info
        save_redeem_codes(codes)
    else:
        awarded_amt = int(code_info.get("amount", 1000))
        del codes[matched_code_key]
        save_redeem_codes(codes)
        new_balance, exp_disp = add_expiring_bonus_to_wallet(uid, awarded_amt, validity_days)

    user_info = getattr(g, "current_user", {}) or {}
    user_name = user_info.get("name") or user_info.get("first_name") or "HMA Customer"

    # Telegram bot alert to admins
    for aid in ADMIN_CHAT_IDS:
        try:
            bot.send_message(
                aid,
                f"🎟️ <b>Mini App Redeem Code Claimed:</b>\n\n"
                f"Customer: {user_name} (ID: <code>{uid}</code>) သည် Code <code>{matched_code_key}</code> ဖြင့် "
                f"<b>+{awarded_amt:,} MMK</b> ({validity_days} ရက် သက်တမ်း) ရယူသွားပါပြီခင်ဗျာ။",
                parse_mode="HTML"
            )
        except Exception:
            pass

    return jsonify({
        "success": True,
        "code": matched_code_key,
        "awarded_amount": awarded_amt,
        "validity_days": validity_days,
        "expire_date": exp_disp,
        "new_balance": new_balance,
        "message": f"🎉 ဂုဏ်ယူပါတယ်ခင်ဗျာ! Redeem Code အောင်မြင်စွာ အသုံးပြုပြီးပါပြီ (+{awarded_amt:,} Ks)",
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
