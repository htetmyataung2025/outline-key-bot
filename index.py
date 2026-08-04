import os
import requests
import random
import string
from flask import Flask, request, jsonify
import telebot
from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton, ReplyKeyboardMarkup, KeyboardButton, WebAppInfo
import re
import base64
import json
import html
import uuid
from datetime import datetime, timedelta
from dateutil.relativedelta import relativedelta

app = Flask(__name__)

# Telegram Bot Token & API Setup
TELEGRAM_TOKEN = "8779558815:AAEaXF6rRqCVM-PFhbOlwgubSknk5xTiKvU"

# 📢 Force Join Channel Configuration
REQUIRED_CHANNEL = "@hefeature"

# 🌐 Outline API Servers (Server 1 & 2)
OUTLINE_API_URL_1 = "https://h.e.feature.hma.qzz.io:49429/YkDBSn3KwUaICBvzDQtvxQ"
OUTLINE_API_URL_2 = "https://104.207.77.147:5714/UrZDutqOIvK931jb3x7hLA"

# 🟣 3X-UI VLESS Panel Setup
PANEL_BASE_URL = "https://h.e.feature.hma.qzz.io:14096/SHXjOMXGbiCuHQ6X1G"
PANEL_USERNAME = "hma"
PANEL_PASSWORD = "Hm@147025"
VLESS_INBOUND_ID = 1
VLESS_FLOW = "xtls-rprx-vision"

# 🔑 Admin Telegram Chat IDs
ADMIN_CHAT_IDS = ["8778394176", "6297145771"]

bot = telebot.TeleBot(TELEGRAM_TOKEN, threaded=False)
requests.packages.urllib3.disable_warnings()

# 🌐 Vercel Upstash Redis REST API Setup
KV_URL = os.environ.get("KV_REST_API_URL")
KV_TOKEN = os.environ.get("KV_REST_API_TOKEN")

def redis_get(key):
    if not KV_URL or not KV_TOKEN:
        return None
    try:
        res = requests.get(f"{KV_URL}/get/{key}", headers={"Authorization": f"Bearer {KV_TOKEN}"}, timeout=5)
        if res.status_code == 200:
            val = res.json().get("result")
            return json.loads(val) if val else None
    except:
        pass
    return None

def redis_set(key, value):
    if not KV_URL or not KV_TOKEN:
        return False
    try:
        val_str = json.dumps(value)
        res = requests.post(f"{KV_URL}/set/{key}", headers={"Authorization": f"Bearer {KV_TOKEN}"}, data=val_str, timeout=5)
        return res.status_code == 200
    except:
        return False

# Temp Files & Fallbacks
STATE_FILE = "/tmp/user_plans.json"
MAPPING_FILE = "/tmp/key_mappings.json"
REDEEM_FILE = "/tmp/redeem_codes.json"
USED_REDEEMERS_FILE = "/tmp/used_redeemers.json"
SEARCH_STATE_FILE = "/tmp/admin_search_state.json"
REDEEM_STATE_FILE = "/tmp/user_redeem_state.json"
REPLACEMENT_STATE_FILE = "/tmp/user_replacement_state.json"
SALES_FILE = "/tmp/sales_history.json"
ADMIN_MSG_MAP_FILE = "/tmp/admin_msg_map.json"
BROADCAST_STATE_FILE = "/tmp/admin_broadcast_state.json"
ALL_USERS_FILE = "/tmp/all_users.json"
PROCESSED_CALLBACKS = set()

def is_callback_processed(call_id):
    if call_id in PROCESSED_CALLBACKS:
        return True
    PROCESSED_CALLBACKS.add(call_id)
    if len(PROCESSED_CALLBACKS) > 1000:
        PROCESSED_CALLBACKS.clear()
    return False

# 📢 All Users List
def save_user_id(chat_id):
    users = redis_get("all_users") or []
    if str(chat_id) not in [str(u) for u in users]:
        users.append(str(chat_id))
        redis_set("all_users", users)

def load_all_users():
    users = redis_get("all_users") or []
    plans = load_user_plans()
    for uid in plans.keys():
        if str(uid) not in [str(u) for u in users]:
            users.append(str(uid))
    mappings = load_key_mappings()
    for uid in mappings.values():
        if str(uid) not in [str(u) for u in users]:
            users.append(str(uid))
    redis_set("all_users", users)
    return users

# Broadcast State
def set_broadcast_state(chat_id, is_waiting=True):
    states = redis_get("admin_broadcast_state") or {}
    states[str(chat_id)] = is_waiting
    redis_set("admin_broadcast_state", states)

def get_broadcast_state(chat_id):
    states = redis_get("admin_broadcast_state") or {}
    return states.get(str(chat_id), False)

def load_user_plans():
    data = redis_get("user_plans")
    if data is not None:
        return data
    if os.path.exists(STATE_FILE):
        try:
            with open(STATE_FILE, 'r') as f:
                return json.load(f)
        except:
            pass
    return {}

def save_user_plan(chat_id, plan_data):
    plans = load_user_plans()
    plans[str(chat_id)] = plan_data
    redis_set("user_plans", plans)

def load_key_mappings():
    data = redis_get("key_mappings")
    if data is not None:
        return data
    if os.path.exists(MAPPING_FILE):
        try:
            with open(MAPPING_FILE, 'r') as f:
                return json.load(f)
        except:
            pass
    return {}

def save_key_mapping(clean_name, chat_id):
    mappings = load_key_mappings()
    mappings[clean_name.strip().lower()] = str(chat_id)
    redis_set("key_mappings", mappings)

def load_sales_history():
    data = redis_get("sales_history")
    if data is not None:
        return data
    return []

def save_sale_transaction(server_num, chat_id, plan_code, plan_name, months_count, price_int):
    # 💡 Admin စမ်းသပ်ထုတ်ယူခြင်း ဖြစ်ပါက Sales History ထဲ ငွေစာရင်း သွားမပေါင်းပါ
    if str(chat_id) in [str(aid) for aid in ADMIN_CHAT_IDS]:
        return

    sales = load_sales_history()
    now = datetime.utcnow() + timedelta(hours=6, minutes=30)  # MMT Timezone
    sale_data = {
        "timestamp": now.strftime("%Y-%m-%d %H:%M:%S"),
        "date": now.strftime("%Y-%m-%d"),
        "year": now.year,
        "month": now.month,
        "server": str(server_num),
        "chat_id": str(chat_id),
        "plan_code": plan_code,
        "plan_name": plan_name,
        "months": months_count,
        "price": int(price_int) if price_int else 0
    }
    sales.append(sale_data)
    redis_set("sales_history", sales)

def save_admin_msg_map(target_chat_id, admin_msg_dict):
    try:
        data = redis_get("admin_msg_map") or {}
        data[str(target_chat_id)] = admin_msg_dict
        redis_set("admin_msg_map", data)
    except:
        pass

def get_admin_msg_map(target_chat_id):
    try:
        data = redis_get("admin_msg_map") or {}
        return data.get(str(target_chat_id), {})
    except:
        return {}

def load_redeem_codes():
    data = redis_get("redeem_codes")
    if data is not None:
        return data
    return {}

def save_redeem_codes(codes):
    redis_set("redeem_codes", codes)

def set_search_state(chat_id, is_searching=True):
    states = redis_get("admin_search_state") or {}
    states[str(chat_id)] = is_searching
    redis_set("admin_search_state", states)

def get_search_state(chat_id):
    states = redis_get("admin_search_state") or {}
    return states.get(str(chat_id), False)

def set_redeem_state(chat_id, is_waiting=True):
    states = redis_get("user_redeem_state") or {}
    states[str(chat_id)] = is_waiting
    redis_set("user_redeem_state", states)

def get_redeem_state(chat_id):
    states = redis_get("user_redeem_state") or {}
    return states.get(str(chat_id), False)

def set_replacement_state(chat_id, is_waiting=True):
    states = redis_get("user_replacement_state") or {}
    states[str(chat_id)] = is_waiting
    redis_set("user_replacement_state", states)

def get_replacement_state(chat_id):
    states = redis_get("user_replacement_state") or {}
    return states.get(str(chat_id), False)

def clear_all_states(chat_id):
    set_search_state(chat_id, False)
    set_redeem_state(chat_id, False)
    set_replacement_state(chat_id, False)
    set_broadcast_state(chat_id, False)

def is_user_subscribed(user_id):
    if str(user_id) in [str(aid) for aid in ADMIN_CHAT_IDS]:
        return True
    try:
        member = bot.get_chat_member(REQUIRED_CHANNEL, user_id)
        if member.status in ['creator', 'administrator', 'member']:
            return True
    except Exception as e:
        return True
    return False

def get_force_join_keyboard():
    markup = InlineKeyboardMarkup()
    channel_url = f"https://t.me/{REQUIRED_CHANNEL.replace('@', '')}"
    markup.add(InlineKeyboardButton("📢 Channel သို့ Join ရန်", url=channel_url))
    markup.add(InlineKeyboardButton("✅ Join ပြီးပါပြီ (Verify)", callback_data="verify_subscription"))
    return markup

def send_force_join_message(chat_id):
    msg_text = (
        f"⚠️ <b>သတိပေးချက်:</b>\n\n"
        f"Bot အား စတင်အသုံးပြုရန်အတွက် အောက်ပါ ကျွန်ုပ်တို့၏ Telegram Channel ကို အရင်ဆုံး Join ပေးရန် လိုအပ်ပါသည်ခင်ဗျာ။\n\n"
        f"👉 <b>Channel:</b> {REQUIRED_CHANNEL}\n\n"
        f"Channel Join ပြီးပါက <b>'✅ Join ပြီးပါပြီ (Verify)'</b> ခလုတ်ကို နှိပ်၍ အသုံးပြုနိုင်ပါပြီ။"
    )
    bot.send_message(chat_id, msg_text, parse_mode="HTML", reply_markup=get_force_join_keyboard())

# 🟣 3X-UI Panel API Helper Functions (Path Fixed)
def get_3xui_session():
    session = requests.Session()
    base_clean = PANEL_BASE_URL.rstrip('/')
    login_url = f"{base_clean}/login"
    payload = {"username": PANEL_USERNAME, "password": PANEL_PASSWORD}
    try:
        res = session.post(login_url, data=payload, verify=False, timeout=10)
        if res.status_code == 200:
            res_json = res.json()
            if res_json.get("success"):
                return session
    except Exception as e:
        print("3X-UI Login Error:", e)
    return None

def create_3xui_vless_key(user_name, custom_gb=None, target_chat_id=None, custom_days=None, months_count=1, is_giveaway=False, custom_expire_date=None):
    session = get_3xui_session()
    if not session:
        return None, None, None

    today = datetime.now()
    if custom_expire_date:
        exp_dt = datetime.strptime(custom_expire_date, "%d.%m.%Y")
        expire_date_str = custom_expire_date
    elif custom_days:
        exp_dt = today + timedelta(days=custom_days)
        expire_date_str = exp_dt.strftime("%d.%m.%Y")
    else:
        exp_dt = today + relativedelta(months=months_count)
        expire_date_str = exp_dt.strftime("%d.%m.%Y")

    expiry_timestamp_ms = int(exp_dt.timestamp() * 1000)
    client_uuid = str(uuid.uuid4())
    id_str = f"({target_chat_id})" if target_chat_id else ""
    gw_str = "[GW]" if is_giveaway else ""
    email_name = f"{user_name}_{id_str}_{gw_str}_{expire_date_str}".replace(" ", "_").strip()

    limit_bytes = 0
    if custom_gb:
        limit_bytes = int(custom_gb * 1000**3)
    else:
        limit_bytes = int(25 * 1000**3)

    client_settings = {
        "clients": [{
            "id": client_uuid,
            "email": email_name,
            "flow": VLESS_FLOW,
            "totalGB": limit_bytes,
            "expiryTime": expiry_timestamp_ms,
            "enable": True,
            "tgId": str(target_chat_id) if target_chat_id else "",
            "subId": "".join(random.choices(string.ascii_lowercase + string.digits, k=16))
        }]
    }

    base_clean = PANEL_BASE_URL.rstrip('/')
    add_url = f"{base_clean}/panel/api/inbounds/addClient"
    payload = {
        "id": VLESS_INBOUND_ID,
        "settings": json.dumps(client_settings)
    }

    try:
        res = session.post(add_url, json=payload, verify=False, timeout=10)
        if res.status_code == 200 and res.json().get("success"):
            parsed_host = PANEL_BASE_URL.split("//")[1].split(":")[0]
            vless_link = f"vless://{client_uuid}@{parsed_host}:8080?type=tcp&security=reality&flow={VLESS_FLOW}#{user_name}"
            return vless_link, email_name, expire_date_str
    except Exception as e:
        print("3X-UI Create Key Error:", e)

    return None, None, None

PLANS = {
    "starter": {"name": "Starter Plan", "data": "25 GB", "bytes": 25 * 1000**3, "price": 1000},
    "basic": {"name": "Basic Plan", "data": "50 GB", "bytes": 50 * 1000**3, "price": 2000},
    "standard": {"name": "Standard Plan", "data": "75 GB", "bytes": 75 * 1000**3, "price": 3000},
    "premium": {"name": "Premium Plan", "data": "100 GB", "bytes": 100 * 1000**3, "price": 4000},
    "vip": {"name": "VIP Plan", "data": "150 GB", "bytes": 150 * 1000**3, "price": 5000},
    "pro": {"name": "Pro Plan", "data": "200 GB", "bytes": 200 * 1000**3, "price": 7000},
    "ultimate": {"name": "Ultimate VIP Plan", "data": "Unlimited (1000 GB / လစဉ်)", "bytes": 1000 * 1000**3, "price": 10000},
}

def bytes_to_gb(bytes_value):
    return round(bytes_value / (1000 ** 3), 2)

def clean_ss_url(url_str):
    if not url_str:
        return ""
    main_part = url_str.replace("ss://", "").split("#")[0].split("?")[0]
    return main_part.strip()

def get_main_menu_keyboard(chat_id=None):
    markup = ReplyKeyboardMarkup(resize_keyboard=True, row_width=2)
    btn_buy = KeyboardButton("💳 Plan များ ကြည့်ရန်")
    btn_check = KeyboardButton("⚡️ Data Usage စစ်ရန်")
    btn_replace = KeyboardButton("🔄 Key လဲရန်")
    btn_free = KeyboardButton("🎁 Public Free Key")
    btn_redeem = KeyboardButton("🎁 Redeem Code")
    btn_admin = KeyboardButton("👨‍💻 Admin သို့ ဆက်သွယ်ရန်")
    btn_refresh = KeyboardButton("🔄 Bot Refresh")
    
    markup.add(btn_buy, btn_check)
    markup.add(btn_replace, btn_refresh)
    markup.add(btn_free, btn_redeem)
    markup.add(btn_admin)
    
    if chat_id and str(chat_id) in [str(aid) for aid in ADMIN_CHAT_IDS]:
        btn_total_usage = KeyboardButton("📊 Total Data Usage")
        btn_monthly_income = KeyboardButton("💰 လစဉ် ဝင်ငွေ")
        btn_gen_code = KeyboardButton("🎁 Gen RD Code")
        btn_search_user = KeyboardButton("🔍 Cus ရှာရန်")
        btn_broadcast = KeyboardButton("📢 Broadcast စာပို့ရန်")
        markup.add(btn_total_usage, btn_gen_code)
        markup.add(btn_monthly_income, btn_search_user)
        markup.add(btn_broadcast)
        
    return markup

def get_back_inline_keyboard():
    markup = InlineKeyboardMarkup()
    markup.add(InlineKeyboardButton("🔙 မူလ Menu သို့ ပြန်သွားရန်", callback_data="back_to_main"))
    return markup

def get_plan_keyboard():
    markup = InlineKeyboardMarkup()
    markup.row(InlineKeyboardButton("🌟 Starter (25 GB) - 1,000 Ks", callback_data="selectplan_starter"))
    markup.row(InlineKeyboardButton("💎 Basic (50 GB) - 2,000 Ks", callback_data="selectplan_basic"))
    markup.row(InlineKeyboardButton("⚡ Standard (75 GB) - 3,000 Ks", callback_data="selectplan_standard"))
    markup.row(InlineKeyboardButton("🔥 Premium (100 GB) - 4,000 Ks", callback_data="selectplan_premium"))
    markup.row(InlineKeyboardButton("👑 VIP (150 GB) - 5,000 Ks", callback_data="selectplan_vip"))
    markup.row(InlineKeyboardButton("🚀 Pro (200 GB) - 7,000 Ks", callback_data="selectplan_pro"))
    markup.row(InlineKeyboardButton("🌌 Ultimate VIP - Unlimited (1000 GB/လစဉ်)", callback_data="selectplan_ultimate"))
    markup.row(InlineKeyboardButton("🔙 မူလ Menu သို့ ပြန်သွားရန်", callback_data="back_to_main"))
    return markup

def get_admin_gb_keyboard():
    markup = InlineKeyboardMarkup()
    markup.row(
        InlineKeyboardButton("⚡️ 25 GB", callback_data="adm_gb_25"),
        InlineKeyboardButton("⚡️ 50 GB", callback_data="adm_gb_50")
    )
    markup.row(
        InlineKeyboardButton("⚡️ 75 GB", callback_data="adm_gb_75"),
        InlineKeyboardButton("⚡️ 100 GB", callback_data="adm_gb_100")
    )
    markup.row(
        InlineKeyboardButton("⚡️ 150 GB", callback_data="adm_gb_150"),
        InlineKeyboardButton("⚡️ 200 GB", callback_data="adm_gb_200")
    )
    markup.row(InlineKeyboardButton("🔙 မူလ Menu သို့ ပြန်သွားရန်", callback_data="back_to_main"))
    return markup

def get_admin_days_keyboard(gb):
    markup = InlineKeyboardMarkup()
    markup.row(
        InlineKeyboardButton("📅 3 ရက်", callback_data=f"adm_dur_{gb}_3"),
        InlineKeyboardButton("📅 5 ရက်", callback_data=f"adm_dur_{gb}_5")
    )
    markup.row(
        InlineKeyboardButton("📅 7 ရက်", callback_data=f"adm_dur_{gb}_7"),
        InlineKeyboardButton("📅 10 ရက်", callback_data=f"adm_dur_{gb}_10")
    )
    markup.row(
        InlineKeyboardButton("📅 30 ရက် (1 လ)", callback_data=f"adm_dur_{gb}_30")
    )
    markup.row(InlineKeyboardButton("🔙 GB ပြန်ရွေးရန်", callback_data="back_to_gen_rd"))
    return markup

def get_admin_count_keyboard(gb, days):
    markup = InlineKeyboardMarkup()
    markup.row(
        InlineKeyboardButton("1 ခု", callback_data=f"adm_cnt_{gb}_{days}_1"),
        InlineKeyboardButton("3 ခု", callback_data=f"adm_cnt_{gb}_{days}_3")
    )
    markup.row(
        InlineKeyboardButton("5 ခု", callback_data=f"adm_cnt_{gb}_{days}_5"),
        InlineKeyboardButton("10 ခု", callback_data=f"adm_cnt_{gb}_{days}_10")
    )
    markup.row(InlineKeyboardButton("🔙 ရက်ပေါင်း ပြန်ရွေးရန်", callback_data=f"adm_gb_{gb}"))
    return markup

def get_monthly_revenue_report():
    now = datetime.utcnow() + timedelta(hours=6, minutes=30)
    now_str = now.strftime("%d/%m/%Y (%I:%M %p)")
    current_year = now.year
    current_month = now.month
    today_str = now.strftime("%Y-%m-%d")

    sales_history = load_sales_history()

    s1_keys, s1_rev, s1_today_keys, s1_today_rev = 0, 0, 0, 0
    s2_keys, s2_rev, s2_today_keys, s2_today_rev = 0, 0, 0, 0
    vless_keys, vless_rev, vless_today_keys, vless_today_rev = 0, 0, 0, 0

    s1_plans, s2_plans, vless_plans, today_plans = {}, {}, {}, {}

    for item in sales_history:
        item_year = item.get("year")
        item_month = item.get("month")
        
        if item_year == current_year and item_month == current_month:
            srv = str(item.get("server", "1"))
            price = int(item.get("price", 0))
            p_name = item.get("plan_name", "Plan")
            p_months = item.get("months", 1)
            p_key_str = f"{p_name} [{p_months} လစာ]"
            is_today = (item.get("date") == today_str)

            if is_today:
                today_plans[p_key_str] = today_plans.get(p_key_str, 0) + 1

            if srv == "1" or srv == "srv1":
                s1_keys += 1
                s1_rev += price
                s1_plans[p_key_str] = s1_plans.get(p_key_str, 0) + 1
                if is_today:
                    s1_today_keys += 1
                    s1_today_rev += price
            elif srv == "2" or srv == "srv2":
                s2_keys += 1
                s2_rev += price
                s2_plans[p_key_str] = s2_plans.get(p_key_str, 0) + 1
                if is_today:
                    s2_today_keys += 1
                    s2_today_rev += price
            elif srv == "vless":
                vless_keys += 1
                vless_rev += price
                vless_plans[p_key_str] = vless_plans.get(p_key_str, 0) + 1
                if is_today:
                    vless_today_keys += 1
                    vless_today_rev += price

    total_keys = s1_keys + s2_keys + vless_keys
    total_rev = s1_rev + s2_rev + vless_rev
    today_keys = s1_today_keys + s2_today_keys + vless_today_keys
    today_rev = s1_today_rev + s2_today_rev + vless_today_rev

    def format_sales_breakdown(plans_dict):
        if not plans_dict:
            return "   • <i>မရှိသေးပါ</i>"
        lines = []
        for k, v in plans_dict.items():
            lines.append(f"   • {k}: <b>{v}</b> ခု")
        return "\n".join(lines)

    report = (
        f"💵 <b>MONTHLY SALES REVENUE REPORT</b>\n"
        f"📅 <b>စစ်ဆေးသည့် ရက်စွဲ:</b> <code>{now_str}</code>\n"
        f"━━━━━━━━━━━━━━━━━\n\n"
        f"🔥 <b>ဒီနေ့ ရောင်းရငွေ (Today's Sales)</b>\n"
        f"🔑 ရောင်းရသော Key: <b>{today_keys} ခု</b>\n"
        f"{format_sales_breakdown(today_plans)}\n"
        f"💰 ဒီနေ့ ဝင်ငွေ: <b>{today_rev:,} Ks</b>\n\n"
        f"━━━━━━━━━━━━━━━━━\n\n"
        f"📡 <b>Server 1 🇸🇬 (Outline):</b>\n"
        f"🔑 Total Paid Keys: <b>{s1_keys} ခု</b>\n"
        f"💵 Server 1 လစဉ်ဝင်ငွေ: <b>{s1_rev:,} Ks</b>\n\n"
        f"📡 <b>Server 2 🇸🇬 (Outline):</b>\n"
        f"🔑 Total Paid Keys: <b>{s2_keys} ခု</b>\n"
        f"💵 Server 2 လစဉ်ဝင်ငွေ: <b>{s2_rev:,} Ks</b>\n\n"
        f"🟣 <b>3X-UI Server 🇸🇬 (VLESS REALITY):</b>\n"
        f"🔑 Total Paid Keys: <b>{vless_keys} ခု</b>\n"
        f"💵 VLESS လစဉ်ဝင်ငွေ: <b>{vless_rev:,} Ks</b>\n\n"
        f"━━━━━━━━━━━━━━━━━\n"
        f"🌐 <b>Total This Month Paid Keys:</b> <b>{total_keys} ခု</b>\n"
        f"💎 <b>ဒီလ စုစုပေါင်း ဝင်ငွေ:</b> <b>{total_rev:,} MMK</b>"
    )
    return report

def get_servers_total_usage():
    def get_server_stats(api_url):
        total_keys, total_bytes = 0, 0
        try:
            keys_resp = requests.get(f"{api_url}/access-keys", verify=False, timeout=8)
            metrics_resp = requests.get(f"{api_url}/metrics/transfer", verify=False, timeout=8)
            if keys_resp.status_code == 200:
                total_keys = len(keys_resp.json().get("accessKeys", []))
            if metrics_resp.status_code == 200:
                total_bytes = sum(metrics_resp.json().get("bytesTransferredByUserId", {}).values())
        except:
            pass
        return total_keys, total_bytes

    def get_vless_stats():
        v_keys, v_bytes = 0, 0
        session = get_3xui_session()
        if session:
            try:
                base_clean = PANEL_BASE_URL.rstrip('/')
                res = session.get(f"{base_clean}/panel/api/inbounds/list", verify=False, timeout=8)
                if res.status_code == 200 and res.json().get("success"):
                    inbounds = res.json().get("obj", [])
                    for ib in inbounds:
                        if ib.get("id") == VLESS_INBOUND_ID:
                            client_stats = ib.get("clientStats", [])
                            v_keys = len(client_stats)
                            for c in client_stats:
                                v_bytes += (c.get("up", 0) + c.get("down", 0))
            except:
                pass
        return v_keys, v_bytes

    s1_total, s1_bytes = get_server_stats(OUTLINE_API_URL_1)
    s2_total, s2_bytes = get_server_stats(OUTLINE_API_URL_2)
    v_total, v_bytes = get_vless_stats()

    s1_gb, s2_gb, v_gb = bytes_to_gb(s1_bytes), bytes_to_gb(s2_bytes), bytes_to_gb(v_bytes)
    overall_bytes = s1_bytes + s2_bytes + v_bytes
    overall_gb = bytes_to_gb(overall_bytes)

    report = (
        f"📊 <b>SERVER DATA STATS REPORT</b>\n\n"
        f"📡 <b>Server 1 🇸🇬 (Outline):</b>\n"
        f"🔑 Total Keys: <b>{s1_total}</b> | Usage: <b>{s1_gb} GB</b>\n\n"
        f"📡 <b>Server 2 🇸🇬 (Outline):</b>\n"
        f"🔑 Total Keys: <b>{s2_total}</b> | Usage: <b>{s2_gb} GB</b>\n\n"
        f"🟣 <b>3X-UI Server 🇸🇬 (VLESS REALITY):</b>\n"
        f"🔑 Total Keys: <b>{v_total}</b> | Usage: <b>{v_gb} GB</b>\n"
        f"━━━━━━━━━━━━━━━━━\n"
        f"🌟 <b>Overall Total Usage:</b> <b>{overall_gb} GB (~{round(overall_gb/1000, 2)} TB)</b>"
    )
    return report

def search_users_by_query(query):
    query_clean = query.strip().lower()
    markup = InlineKeyboardMarkup()
    found_matches = []

    # Outline Server 1 & 2
    for server_num, api_url in [("1", OUTLINE_API_URL_1), ("2", OUTLINE_API_URL_2)]:
        try:
            res = requests.get(f"{api_url}/access-keys", verify=False, timeout=8)
            if res.status_code == 200:
                keys = res.json().get("accessKeys", [])
                for k in keys:
                    k_name = k.get("name", "").strip()
                    if query_clean in k_name.lower():
                        found_matches.append((server_num, str(k.get("id")), k_name))
        except:
            pass

    # 3X-UI VLESS Server
    session = get_3xui_session()
    if session:
        try:
            base_clean = PANEL_BASE_URL.rstrip('/')
            res = session.get(f"{base_clean}/panel/api/inbounds/list", verify=False, timeout=8)
            if res.status_code == 200 and res.json().get("success"):
                inbounds = res.json().get("obj", [])
                for ib in inbounds:
                    if ib.get("id") == VLESS_INBOUND_ID:
                        client_stats = ib.get("clientStats", [])
                        for c in client_stats:
                            email = c.get("email", "")
                            if query_clean in email.lower():
                                found_matches.append(("vless", email, email))
        except:
            pass

    for server_num, key_id, k_name in found_matches[:30]:
        if server_num == "vless":
            btn_text = f"🟣 VLESS🇸🇬 | {k_name}"
            markup.add(InlineKeyboardButton(btn_text, callback_data=f"viewvless_{key_id}"))
        else:
            srv_icon = "📡 S1🇸🇬" if server_num == "1" else "📡 S2🇸🇬"
            btn_text = f"{srv_icon} | {k_name}"
            markup.add(InlineKeyboardButton(btn_text, callback_data=f"viewkey_{server_num}_{key_id}"))

    return found_matches, markup

# 🔙 Back to Main Menu Callback Handler
@bot.callback_query_handler(func=lambda call: call.data == "back_to_main")
def handle_back_to_main_callback(call):
    chat_id = call.message.chat.id
    clear_all_states(chat_id)
    bot.answer_callback_query(call.id, "🔙 မူလ Menu သို့ ပြန်သွားပါပြီ။")
    try:
        bot.delete_message(chat_id, call.message.message_id)
    except:
        pass
    welcome_text = (
        "👋 မင်္ဂလာပါ! H & E FEATURE PREMIUM VPN ဝန်ဆောင်မှု Bot မှ ကြိုဆိုပါတယ်။\n\n"
        "👇 အောက်ခြေက Menu Button တွေကို အသုံးပြုပြီး မိမိတို့ အလိုရှိရာကို ရွေးချယ်နိုင်ပါတယ်ခင်ဗျာ।"
    )
    bot.send_message(chat_id, welcome_text, reply_markup=get_main_menu_keyboard(chat_id))

# 🔙 Admin Back to Gen RD Code Handler
@bot.callback_query_handler(func=lambda call: call.data == "back_to_gen_rd")
def handle_back_to_gen_rd(call):
    bot.answer_callback_query(call.id)
    if str(call.message.chat.id) not in [str(aid) for aid in ADMIN_CHAT_IDS]:
        return
    bot.edit_message_text(
        "🎁 <b>Giveaway Redeem Code ထုတ်ရန်:</b>\n\nကျေးပြု၍ ဖန်တီးလိုသော <b>GB ပမာဏ</b> ကို ရွေးချယ်ပေးပါခင်ဗျာ:",
        chat_id=call.message.chat.id,
        message_id=call.message.message_id,
        parse_mode="HTML",
        reply_markup=get_admin_gb_keyboard()
    )

@bot.callback_query_handler(func=lambda call: call.data.startswith("viewkey_"))
def handle_view_key_detail(call):
    bot.answer_callback_query(call.id)
    if str(call.message.chat.id) not in [str(aid) for aid in ADMIN_CHAT_IDS]:
        return
    
    parts = call.data.split("_")
    server_num = parts[1]
    key_id = parts[2]
    
    api_url = OUTLINE_API_URL_1 if server_num == "1" else OUTLINE_API_URL_2
    
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
                full_name = target_key.get("name", "Unnamed Key")
                raw_access_url = target_key.get("accessUrl", "")
                final_key = f"{raw_access_url}#{full_name}" if full_name else raw_access_url
                
                limit_bytes = target_key.get("dataLimit", {}).get("bytes")
                plan_gb = f"{bytes_to_gb(limit_bytes)} GB" if limit_bytes else "Unlimited"
                usage_bytes = bytes_transferred.get(str(key_id), 0)
                usage_gb = bytes_to_gb(usage_bytes)
                
                date_match = re.search(r'\d{1,2}\.\d{1,2}\.(\d{4}|\d{2})', full_name)
                end_date = date_match.group(0) if date_match else "မသိရှိပါ"
                
                server_name = "Server 1 🇸🇬" if server_num == "1" else "Server 2 🇸🇬"
                
                markup = InlineKeyboardMarkup()
                markup.add(InlineKeyboardButton("🗑️ Key ဖျက်ရန် (Delete)", callback_data=f"delkey_ask_{server_num}_{key_id}"))

                detail_msg = (
                    f"👤 <b>Customer Information✅ </b>\n\n"
                    f"🤖 <b>Name:</b> {html.escape(full_name)}\n"
                    f"📡 <b>Server:</b> {server_name}\n"
                    f"⚡️ <b>Data Usage :</b> <code>{usage_gb} GB</code> / <code>{plan_gb}</code>\n"
                    f"⏰ <b>Expired Date:</b> {end_date}\n"
                    f"🔑 <b>VPN Key Link:</b>\n\n"
                    f"<code>{final_key}</code>"
                )
                bot.send_message(call.message.chat.id, detail_msg, parse_mode="HTML", reply_markup=markup)
                return
    except Exception as e:
        bot.send_message(call.message.chat.id, f"❌ Error: {str(e)}")

@bot.callback_query_handler(func=lambda call: call.data.startswith("delkey_"))
def handle_admin_del_key(call):
    bot.answer_callback_query(call.id)
    if is_callback_processed(f"del_{call.message.message_id}_{call.data}"):
        return

    if str(call.message.chat.id) not in [str(aid) for aid in ADMIN_CHAT_IDS]:
        return

    parts = call.data.split("_")
    action = parts[1]
    server_num = parts[2]
    key_id = parts[3]

    if action == "ask":
        markup = InlineKeyboardMarkup()
        markup.row(
            InlineKeyboardButton("✅ Yes (ဖျက်မည်)", callback_data=f"delkey_confirm_{server_num}_{key_id}"),
            InlineKeyboardButton("❌ No (မဖျက်တော့ပါ)", callback_data="delkey_cancel")
        )
        bot.send_message(call.message.chat.id, f"⚠️ <b>သတိပေးချက်:</b> Server {server_num} ပေါ်မှ ID ({key_id}) ရှိသော Key ကို အပြီးတိုင် ဖျက်ရန် သေချာပါသလား?", parse_mode="HTML", reply_markup=markup)

    elif action == "confirm":
        api_url = OUTLINE_API_URL_1 if server_num == "1" else OUTLINE_API_URL_2
        try:
            del_res = requests.delete(f"{api_url}/access-keys/{key_id}", verify=False, timeout=8)
            if del_res.status_code in [200, 204]:
                bot.edit_message_text(f"✅ <b>Server {server_num} ပေါ်မှ Key (ID: {key_id}) အား အောင်မြင်စွာ ဖျက်ဆီးပြီးပါပြီဗျာ။</b>", chat_id=call.message.chat.id, message_id=call.message.message_id, parse_mode="HTML")
            else:
                bot.edit_message_text(f"❌ Key ဖျက်ရာတွင် အမှားအယွင်း ရှိနေပါသည် (Status: {del_res.status_code})", chat_id=call.message.chat.id, message_id=call.message.message_id)
        except Exception as e:
            bot.edit_message_text(f"❌ Error: {str(e)}", chat_id=call.message.chat.id, message_id=call.message.message_id)

    elif action == "cancel":
        bot.edit_message_text("❌ Key ဖျက်ခြင်းကို ပယ်ဖျက်လိုက်ပါပြီခင်ဗျာ။", chat_id=call.message.chat.id, message_id=call.message.message_id)

def get_user_key_count(user_name):
    count = 0
    clean_user = user_name.strip().lower()
    for api_url in [OUTLINE_API_URL_1, OUTLINE_API_URL_2]:
        try:
            res = requests.get(f"{api_url}/access-keys", verify=False, timeout=5)
            if res.status_code == 200:
                keys = res.json().get("accessKeys", [])
                for k in keys:
                    k_name = k.get("name", "").lower()
                    if clean_user in k_name:
                        count += 1
        except:
            pass
    return count

def renew_or_create_unlimited_key(server_num, user_name, target_chat_id, months_count=1):
    api_url = OUTLINE_API_URL_1 if str(server_num) == "1" else OUTLINE_API_URL_2
    today = datetime.now()
    new_expire_date = (today + relativedelta(months=months_count)).strftime("%d.%m.%Y")
    add_bytes = (1000 * months_count) * 1000**3
    
    try:
        keys_resp = requests.get(f"{api_url}/access-keys", verify=False, timeout=8)
        metrics_resp = requests.get(f"{api_url}/metrics/transfer", verify=False, timeout=8)
        
        if keys_resp.status_code == 200:
            keys_data = keys_resp.json().get("accessKeys", [])
            bytes_transferred = metrics_resp.json().get("bytesTransferredByUserId", {}) if metrics_resp.status_code == 200 else {}
            
            target_key_id = None
            target_key_name = None
            
            for k in keys_data:
                k_name = k.get("name", "")
                if f"({target_chat_id})" in k_name and not "[gw]" in k_name.lower():
                    target_key_id = k.get("id")
                    target_key_name = k_name
                    break
            
            if target_key_id:
                used_bytes = bytes_transferred.get(str(target_key_id), 0)
                new_fup_limit = used_bytes + add_bytes

                updated_name = re.sub(r'\d{1,2}\.\d{1,2}\.(\d{4}|\d{2})$', new_expire_date, target_key_name)
                if updated_name == target_key_name:
                    updated_name = f"{target_key_name.split('(')[0].strip()} ({target_chat_id}) {new_expire_date}"
                
                requests.put(f"{api_url}/access-keys/{target_key_id}/name", data={"name": updated_name}, verify=False, timeout=8)
                requests.put(f"{api_url}/access-keys/{target_key_id}/data-limit", json={"limit": {"bytes": new_fup_limit}}, verify=False, timeout=8)
                
                raw_access_url = k.get("accessUrl", "")
                final_key = f"{raw_access_url}#{updated_name}"
                return final_key, updated_name, new_expire_date, True
    except Exception as e:
        print("Unlimited Renewal Error:", e)

    vpn_key, key_name, expire_date = create_outline_key(server_num, user_name, plan_info={"bytes": add_bytes}, target_chat_id=target_chat_id, months_count=months_count, is_giveaway=False)
    return vpn_key, key_name, expire_date, False

def create_outline_key(server_num, user_name, plan_info=None, custom_gb=None, target_chat_id=None, custom_days=None, months_count=1, is_giveaway=False, custom_expire_date=None):
    today = datetime.now()
    if custom_expire_date:
        expire_date = custom_expire_date
    elif custom_days:
        expire_date = (today + timedelta(days=custom_days)).strftime("%d.%m.%Y")
    else:
        expire_date = (today + relativedelta(months=months_count)).strftime("%d.%m.%Y")
    
    existing_count = get_user_key_count(user_name)
    id_str = f" ({target_chat_id})" if target_chat_id else ""
    gw_str = " [GW]" if is_giveaway else ""
    
    if existing_count == 0:
        key_name = f"{user_name}{id_str}{gw_str} {expire_date}"
    else:
        key_number = existing_count + 1
        key_name = f"{user_name}{id_str}{gw_str} ({key_number}) {expire_date}"
    
    api_url = OUTLINE_API_URL_1 if str(server_num) == "1" else OUTLINE_API_URL_2
    
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
                limit_bytes = plan_info.get("bytes") * months_count

            if limit_bytes:
                requests.put(f"{api_url}/access-keys/{key_id}/data-limit", json={"limit": {"bytes": limit_bytes}}, verify=False, timeout=8)
            
            raw_access_url = key_data.get("accessUrl", "")
            final_key = f"{raw_access_url}#{key_name}"
            return final_key, key_name, expire_date
    except Exception as e:
        print("Key Generation Error:", e)
    return None, None, None

@bot.callback_query_handler(func=lambda call: call.data.startswith("adm_gb_"))
def handle_admin_gb_select(call):
    bot.answer_callback_query(call.id)
    if str(call.message.chat.id) not in [str(aid) for aid in ADMIN_CHAT_IDS]:
        return
    
    gb = call.data.replace("adm_gb_", "")
    bot.edit_message_text(
        f"🎁 <b>{gb} GB</b> အတွက် သက်တမ်း (ရက်) ရွေးချယ်ပေးပါခင်ဗျာ:",
        chat_id=call.message.chat.id,
        message_id=call.message.message_id,
        parse_mode="HTML",
        reply_markup=get_admin_days_keyboard(gb)
    )

@bot.callback_query_handler(func=lambda call: call.data.startswith("adm_dur_"))
def handle_admin_days_select(call):
    bot.answer_callback_query(call.id)
    if str(call.message.chat.id) not in [str(aid) for aid in ADMIN_CHAT_IDS]:
        return
    
    parts = call.data.split("_")
    gb = parts[2]
    days = parts[3]
    
    bot.edit_message_text(
        f"🎁 <b>{gb} GB ({days} ရက်)</b> အတွက် မည်မျှအရေအတွက် Code ထုတ်ယူလိုပါသလဲ?",
        chat_id=call.message.chat.id,
        message_id=call.message.message_id,
        parse_mode="HTML",
        reply_markup=get_admin_count_keyboard(gb, days)
    )

@bot.callback_query_handler(func=lambda call: call.data.startswith("adm_cnt_"))
def handle_admin_code_generate(call):
    bot.answer_callback_query(call.id, "✅ Code များထုတ်ပြီးပါပြီ!")
    if is_callback_processed(f"admcode_{call.message.message_id}_{call.data}"):
        return

    if str(call.message.chat.id) not in [str(aid) for aid in ADMIN_CHAT_IDS]:
        return
    
    parts = call.data.split("_")
    gb_amount = int(parts[2])
    days_amount = int(parts[3])
    count = int(parts[4])
    
    codes = load_redeem_codes()
    generated_list = []
    
    for _ in range(count):
        random_str = ''.join(random.choices(string.ascii_uppercase + string.digits, k=6))
        code = f"H&E-{gb_amount}GB-{random_str}"
        codes[code] = {"gb": gb_amount, "days": days_amount}
        generated_list.append(f"<code>{code}</code>")
        
    save_redeem_codes(codes)
    
    reply_msg = (
        f"🎉 <b>{gb_amount} GB ({days_amount} ရက်) Giveaway Code ({count} ခု) ထုတ်ပြီးပါပြီ:</b>\n\n" +
        "\n".join(generated_list) +
        "\n\n💡 <i>အဆိုပါ Code များကို တစ်ကြိမ်သုံးအဖြစ် အသုံးပြုနိုင်ပါပြီဗျာ။</i>"
    )
    bot.edit_message_text(reply_msg, chat_id=call.message.chat.id, message_id=call.message.message_id, parse_mode="HTML", reply_markup=get_back_inline_keyboard())

@bot.callback_query_handler(func=lambda call: call.data == "verify_subscription")
def handle_verify_subscription(call):
    chat_id = call.message.chat.id
    if is_user_subscribed(chat_id):
        save_user_id(chat_id)
        bot.answer_callback_query(call.id, "✅ Verification အောင်မြင်ပါသည်။")
        try:
            bot.delete_message(chat_id, call.message.message_id)
        except:
            pass
        welcome_text = (
            "👋 မင်္ဂလာပါ! H & E FEATURE PREMIUM VPN ဝန်ဆောင်မှု Bot မှ ကြိုဆိုပါတယ်။\n\n"
            "👇 အောက်ခြေက Menu Button တွေကို အသုံးပြုပြီး မိမိတို့ အလိုရှိရာကို ရွေးချယ်နိုင်ပါတယ်ခင်ဗျာ।"
        )
        bot.send_message(chat_id, welcome_text, reply_markup=get_main_menu_keyboard(chat_id))
    else:
        bot.answer_callback_query(call.id, "❌ Channel ထဲသို့ မဝင်ရောက်ရသေးပါခင်ဗျာ။ အရင်ဆုံး Join ပေးပါ။", show_alert=True)

@bot.message_handler(commands=['start'])
def send_welcome(message):
    chat_id = message.chat.id
    save_user_id(chat_id)
    clear_all_states(chat_id)

    if not is_user_subscribed(chat_id):
        send_force_join_message(chat_id)
        return

    welcome_text = (
        "👋 မင်္ဂလာပါ! H & E FEATURE PREMIUM VPN ဝန်ဆောင်မှု Bot မှ ကြိုဆိုပါတယ်။\n\n"
        "👇 အောက်ခြေက Menu Button တွေကို အသုံးပြုပြီး မိမိတို့ အလိုရှိရာကို ရွေးချယ်နိုင်ပါတယ်ခင်ဗျာ।"
    )
    
    try:
        bot.set_chat_menu_button(chat_id, telebot.types.MenuButtonWebApp(
            type="web_app",
            text="Main Website",
            web_app=WebAppInfo(url="https://h-e.feature.hma.qzz.io"))
        )
    except:
        pass
        
    bot.reply_to(message, welcome_text, reply_markup=get_main_menu_keyboard(chat_id))

@bot.message_handler(commands=['buy'])
def send_plans(message):
    chat_id = message.chat.id
    save_user_id(chat_id)
    if not is_user_subscribed(chat_id):
        send_force_join_message(chat_id)
        return

    clear_all_states(chat_id)
    bot.reply_to(message, "🧸 ကျေးဇူးပြု၍ ဝယ်ယူလိုသော VPN Plan ကို ရွေးချယ်ပေးပါခင်ဗျာ:", reply_markup=get_plan_keyboard())

@bot.callback_query_handler(func=lambda call: call.data.startswith("selectplan_"))
def handle_select_plan(call):
    bot.answer_callback_query(call.id)
    chat_id = call.message.chat.id
    if not is_user_subscribed(chat_id):
        send_force_join_message(chat_id)
        return

    plan_code = call.data.replace("selectplan_", "")
    plan = PLANS.get(plan_code)

    if plan:
        amount = plan["price"]
        data_disp = plan["data"]

        markup = InlineKeyboardMarkup()
        markup.row(
            InlineKeyboardButton("🟢 Outline VPN Key ယူမည်", callback_data=f"proto_outline_{plan_code}"),
            InlineKeyboardButton("🟣 VLESS (3X-UI) Key ယူမည်", callback_data=f"proto_vless_{plan_code}")
        )
        markup.row(InlineKeyboardButton("🔙 Plan များသို့ ပြန်သွားရန်", callback_data="back_to_plans"))

        bot.edit_message_text(
            f"📌 <b>{plan['name']} ({data_disp})</b> - {amount:,} Ks\n\n"
            f"👇 မည်သည့် VPN Key အမျိုးအစား ရယူလိုပါသလဲ ရွေးချယ်ပေးပါခင်ဗျာ:",
            chat_id=chat_id,
            message_id=call.message.message_id,
            parse_mode="HTML",
            reply_markup=markup
        )

# 🟢 Protocol Selection (Outline or VLESS) Handler
@bot.callback_query_handler(func=lambda call: call.data.startswith("proto_"))
def handle_protocol_selection(call):
    bot.answer_callback_query(call.id)
    chat_id = call.message.chat.id
    parts = call.data.split("_")
    proto_choice = parts[1]
    plan_code = parts[2]
    
    plan = PLANS.get(plan_code)
    if plan:
        amount = plan["price"]
        data_disp = plan["data"]

        plan_data = {
            "code": plan_code,
            "name": plan["name"],
            "data": data_disp,
            "protocol": proto_choice,
            "months": 1,
            "price_str": f"{amount:,} Ks",
            "price_int": amount
        }
        save_user_plan(chat_id, plan_data)

        proto_disp = "🟢 Outline VPN Key" if proto_choice == "outline" else "🟣 VLESS (3X-UI) Key"

        markup = InlineKeyboardMarkup()
        markup.row(InlineKeyboardButton("🔙 Plan များသို့ ပြန်သွားရန်", callback_data="back_to_plans"))
        markup.row(InlineKeyboardButton("🔙 မူလ Menu သို့ ပြန်သွားရန်", callback_data="back_to_main"))

        payment_text = (
            f"✅ သင်ရွေးချယ်ထားသော Plan:\n"
            f"📌 {plan['name']} ({data_disp}) - 1 လစာ ({amount:,} Ks)\n"
            f"⚡️ Key အမျိုးအစား: <b>{proto_disp}</b>\n\n"
            f"━━━━━━━━━━━━━━━\n"
            f"💰 ငွေလွှဲရမည့် အကောင့်အချက်အလက်များ:\n\n"
            f"📱 KBZ Pay - 09699970092\n"
            f"👤 Htet Myat Aung\n\n"
            f"📱 Wave Pay - 09699970092\n"
            f"👤 Htet Myat Aung\n\n"
            f"📱 AYA Pay - 09699970092\n"
            f"👤 Htet Myat Aung\n\n"
            f"📱 Uab Pay - 09699970092\n"
            f"👤 Htet Myat Aung\n"
            f"━━━━━━━━━━━━━━━\n\n"
            f"🙏🏻 ငွေလွှဲပြီး Screenshotလေး ပို့ပေးပါခင်ဗျာ🥰\n"
            f"(ပြေစာစစ်ဆေးပြီးသည်နှင့် VPN Key ကို အမြန်ဆုံး ပို့ပေးပါမည်။)"
        )

        bot.edit_message_text(
            payment_text,
            chat_id=chat_id,
            message_id=call.message.message_id,
            parse_mode="HTML",
            reply_markup=markup
        )

@bot.callback_query_handler(func=lambda call: call.data == "back_to_plans")
def handle_back_to_plans(call):
    bot.answer_callback_query(call.id)
    chat_id = call.message.chat.id
    if not is_user_subscribed(chat_id):
        send_force_join_message(chat_id)
        return

    bot.edit_message_text(
        "🧸 ကျေးဇူးပြု၍ ဝယ်ယူလိုသော VPN Plan ကို ရွေးချယ်ပေးပါခင်ဗျာ:",
        chat_id=chat_id,
        message_id=call.message.message_id,
        reply_markup=get_plan_keyboard()
    )

# Admin Approve Callback Handler (Fixed Pattern Matching)
@bot.callback_query_handler(func=lambda call: call.data.startswith("approve_"))
def handle_approve_callback(call):
    bot.answer_callback_query(call.id, "⏳ Key ထုတ်ပေးနေပါသည်...")
    
    lock_key = f"appr_{call.message.message_id}_{call.data}"
    if is_callback_processed(lock_key):
        return

    if str(call.message.chat.id) not in [str(aid) for aid in ADMIN_CHAT_IDS]:
        return
        
    try:
        parts = call.data.split("_")
        action_srv = parts[1] # srv1, srv2, or vless
        target_chat_id = parts[2]
        plan_code = parts[3]
        months_count = int(parts[4]) if len(parts) > 4 else 1
        
        plan_info = PLANS.get(plan_code, PLANS["starter"])
        user_plans = load_user_plans()
        u_plan = user_plans.get(str(target_chat_id), {})
        price_int = u_plan.get("price_int", plan_info["price"])

        chat_info = bot.get_chat(target_chat_id)
        user_first = chat_info.first_name if chat_info.first_name else ""
        user_last = chat_info.last_name if chat_info.last_name else ""
        user_name = f"{user_first} {user_last}".strip() or "HMA Customer"
        
        vpn_key, key_name, expire_date = None, None, None

        if action_srv == "vless":
            gb_val = int(plan_info['data'].split()[0]) * months_count if "data" in plan_info else 25
            vpn_key, key_name, expire_date = create_3xui_vless_key(
                user_name, 
                custom_gb=gb_val, 
                target_chat_id=target_chat_id, 
                months_count=months_count
            )
            srv_title = "🟣 3X-UI Server 🇸🇬 (VLESS REALITY)"
        else:
            server_num = "1" if action_srv == "srv1" else "2"
            vpn_key, key_name, expire_date = create_outline_key(
                server_num, user_name, plan_info=plan_info, target_chat_id=target_chat_id, months_count=months_count
            )
            srv_title = f"📡 Outline Server {server_num} 🇸🇬"

        if vpn_key:
            save_sale_transaction(action_srv, target_chat_id, plan_code, plan_info['name'], months_count, price_int)

            disp_gb = f"{int(plan_info['data'].split()[0]) * months_count} GB" if "data" in plan_info else "25 GB"
            success_message = (
                f"🎉 <b>ငွေလွှဲမှု အောင်မြင်စွာ အတည်ပြုပြီးပါပြီခင်ဗျာ။</b>\n\n"
                f"👤 <b>ဝယ်ယူသူ:</b> {user_name}\n"
                f"💳 <b>Plan:</b> {plan_info['name']} ({disp_gb}) - {months_count} လစာ\n"
                f"⏰ <b>သက်တမ်းကုန်ဆုံးရက်:</b> {expire_date}\n\n"
                f"🔑 <b>လူကြီးမင်း၏ VPN Key</b>\n\n"
                f"<code>{vpn_key}</code>\n\n"
                f"☝️ အပေါ်က Key ကို <b>တစ်ချက်တည်း နှိပ်လိုက်ရုံဖြင့်</b> Auto Copy ကူးသွားပါလိမ့်မယ်ခင်ဗျာ။"
            )
            bot.send_message(target_chat_id, success_message, parse_mode="HTML")
            
            save_key_mapping(user_name.strip().lower(), target_chat_id)
            
            admin_msg_map = get_admin_msg_map(target_chat_id)
            updated_caption = (call.message.caption or "") + f"\n\n✅ <b>DONE ({srv_title})</b>\n\n🔑 {key_name}"

            for aid, mid in admin_msg_map.items():
                try:
                    bot.edit_message_caption(
                        chat_id=aid, message_id=mid, caption=updated_caption, parse_mode="HTML", reply_markup=None
                    )
                except:
                    pass
        else:
            bot.send_message(call.message.chat.id, f"❌ <b>Key မွေး၍ မရပါခင်ဗျာ!</b>\n3X-UI Panel Connection သို့မဟုတ် API ကို စစ်ဆေးပေးပါခင်ဗျာ။", parse_mode="HTML")

    except Exception as e:
        print("Approve Error:", str(e))
        bot.send_message(call.message.chat.id, f"❌ Error: {str(e)}")

# 📸 Photo Message Handler
@bot.message_handler(content_types=['photo'])
def handle_photo_messages(message):
    chat_id = message.chat.id
    save_user_id(chat_id)

    if not is_user_subscribed(chat_id):
        send_force_join_message(chat_id)
        return

    # 📢 Broadcast Photo Handler
    if str(chat_id) in [str(aid) for aid in ADMIN_CHAT_IDS] and get_broadcast_state(chat_id):
        set_broadcast_state(chat_id, False)
        all_users = load_all_users()
        success_count = 0
        photo_id = message.photo[-1].file_id
        caption_text = message.caption or ""

        bot.send_message(chat_id, f"⏳ ပုံပါသော Broadcast စာအား User စုစုပေါင်း ({len(all_users)}) ဆီ အကုန် ပို့ပေးနေပါသည်...")

        for uid in all_users:
            if str(uid) in [str(aid) for aid in ADMIN_CHAT_IDS]:
                continue
            try:
                bot.send_photo(uid, photo_id, caption=caption_text, parse_mode="HTML")
                success_count += 1
            except:
                pass

        bot.send_message(chat_id, f"✅ <b>Broadcast ပို့ပြီးပါပြီ!</b>\n\nအောင်မြင်စွာ ရောက်ရှိသွားသော User အရေအတွက်: <b>{success_count} / {len(all_users)}</b>", parse_mode="HTML")
        return

    # 💳 Payment Screenshot Handler
    clear_all_states(chat_id)

    user_first = message.from_user.first_name if message.from_user.first_name else ""
    user_last = message.from_user.last_name if message.from_user.last_name else ""
    user_name = f"{user_first} {user_last}".strip() or "HMA User"
        
    username = f"@{message.from_user.username}" if message.from_user.username else "No Username"
    user_plans = load_user_plans()
    
    if str(chat_id) not in user_plans:
        bot.reply_to(message, "⚠️ ခွင့်လွှတ်ပါခင်ဗျာ၊ ကျေးဇူးပြု၍ '💳 Plan များ ကြည့်ရန်' ခလုတ်ကို အရင်နှိပ်ပြီး ဝယ်ယူလိုသော Plan ကို ရွေးချယ်ပေးပါဦးခင်ဗျာ။")
        return

    plan_info = user_plans.get(str(chat_id))
    plan_code = plan_info.get('code', 'starter')
    proto_choice = plan_info.get('protocol', 'outline')
    months_count = plan_info.get('months', 1)
    price_str = plan_info.get('price_str', f"{plan_info.get('price_int', 1000):,} Ks")
    current_date = datetime.fromtimestamp(message.date).strftime("%d/%m/%Y")

    proto_disp = "🟢 Outline VPN" if proto_choice == "outline" else "🟣 VLESS (3X-UI)"

    admin_alert_text = (
        f"💰 <b>ငွေလွှဲပြေစာအသစ်</b>\n"
        f"👤 ဝယ်ယူသူနာမည်: {user_name} ({username})\n"
        f"📦 ရွေးချယ်ထားသော Plan: {plan_info['name']} ({plan_info.get('data', '')}) [{months_count} လစာ]\n"
        f"⚡️ Key အမျိုးအစား: <b>{proto_disp}</b>\n"
        f"💵 ကျသင့်ငွေပမာဏ: {price_str}\n"
        f"📅 ပေးပို့သည့်ရက်စွဲ: {current_date}\n"
        f"🆔 User Chat ID: {chat_id}"
    )
    
    approve_markup = InlineKeyboardMarkup()
    if proto_choice == "vless":
        approve_markup.row(InlineKeyboardButton("⚡️ Approve & Issue VLESS Key", callback_data=f"approve_vless_{chat_id}_{plan_code}_{months_count}"))
    else:
        approve_markup.row(
            InlineKeyboardButton("📡 Server 1 🇸🇬 (Outline)", callback_data=f"approve_srv1_{chat_id}_{plan_code}_{months_count}"),
            InlineKeyboardButton("📡 Server 2 🇸🇬 (Outline)", callback_data=f"approve_srv2_{chat_id}_{plan_code}_{months_count}")
        )
    
    admin_msg_dict = {}
    try:
        for admin_id in ADMIN_CHAT_IDS:
            try:
                sent_msg = bot.send_photo(admin_id, message.photo[-1].file_id, caption=admin_alert_text, parse_mode="HTML", reply_markup=approve_markup)
                if sent_msg:
                    admin_msg_dict[str(admin_id)] = sent_msg.message_id
            except:
                pass
        
        save_admin_msg_map(chat_id, admin_msg_dict)
        bot.reply_to(message, "💌 ငွေလွှဲပြေစာအား စစ်ဆေးနေပါသည်။ Admin အတည်ပြုပြီးပါက VPN Key ကို ချက်ချင်းပို့ပေးပါမည်။ ကျေးဇူးတင်ပါသည်ခင်ဗျာ။ 🙏")
    except Exception as e:
        bot.reply_to(message, f"❌ Admin ထံ ပို့၍မရပါ - Bot အား အကောင့်မှ Start နှိပ်ထားရန် လိုအပ်ပါသည်။")

def fetch_key_from_server(api_url, input_value):
    try:
        keys_resp = requests.get(f"{api_url}/access-keys", verify=False, timeout=8)
        metrics_resp = requests.get(f"{api_url}/metrics/transfer", verify=False, timeout=8)
        if keys_resp.status_code == 200:
            keys_data = keys_resp.json().get("accessKeys", [])
            bytes_transferred = metrics_resp.json().get("bytesTransferredByUserId", {})
            for key in keys_data:
                if input_value.startswith("ss://") and clean_ss_url(input_value) in clean_ss_url(key.get("accessUrl", "")):
                    server_num = "1" if api_url == OUTLINE_API_URL_1 else "2"
                    return key, bytes_transferred, server_num
    except:
        pass
    return None, None, None

def fetch_vless_from_3xui(input_value):
    session = get_3xui_session()
    if session:
        try:
            base_clean = PANEL_BASE_URL.rstrip('/')
            res = session.get(f"{base_clean}/panel/api/inbounds/list", verify=False, timeout=8)
            if res.status_code == 200 and res.json().get("success"):
                inbounds = res.json().get("obj", [])
                for ib in inbounds:
                    if ib.get("id") == VLESS_INBOUND_ID:
                        client_stats = ib.get("clientStats", [])
                        for c in client_stats:
                            email = c.get("email", "")
                            if input_value.startswith("vless://") and c.get("id") in input_value:
                                return c, "vless"
        except:
            pass
    return None, None

# 🔄 Admin Key Replacement Callback Handler
@bot.callback_query_handler(func=lambda call: call.data.startswith("replace_"))
def handle_admin_replace_callback(call):
    bot.answer_callback_query(call.id, "⏳ လုပ်ဆောင်နေပါသည်...")
    if str(call.message.chat.id) not in [str(aid) for aid in ADMIN_CHAT_IDS]:
        return

    parts = call.data.split("_")
    action_srv = parts[1] # srv1, srv2, or vless
    target_chat_id = parts[2]
    rem_gb = float(parts[3])
    exp_date = parts[4]

    chat_info = bot.get_chat(target_chat_id)
    user_first = chat_info.first_name if chat_info.first_name else ""
    user_last = chat_info.last_name if chat_info.last_name else ""
    user_name = f"{user_first} {user_last}".strip() or "HMA Customer"

    new_key, key_name, expire_date = None, None, None

    if action_srv == "vless":
        new_key, key_name, expire_date = create_3xui_vless_key(
            user_name, custom_gb=rem_gb, target_chat_id=target_chat_id, custom_expire_date=exp_date
        )
        srv_title = "🟣 3X-UI Server 🇸🇬 (VLESS REALITY)"
    else:
        server_num = "1" if action_srv == "srv1" else "2"
        new_key, key_name, expire_date = create_outline_key(
            server_num, user_name, custom_gb=rem_gb, target_chat_id=target_chat_id, custom_expire_date=exp_date
        )
        srv_title = f"📡 Outline Server {server_num} 🇸🇬"

    if new_key:
        success_msg = (
            f"🎉 <b>လူကြီးမင်း၏ VPN Key ကို အဆင်ပြေစွာ အသစ် လဲလှယ်ပေးလိုက်ပါပြီခင်ဗျာ!</b>\n\n"
            f"👤 <b>အသုံးပြုသူ:</b> {user_name}\n"
            f"📡 <b>Server အသစ်:</b> {srv_title}\n"
            f"⚡️ <b>ကျန်ရှိသော Data:</b> {rem_gb} GB\n"
            f"⏰ <b>သက်တမ်းကုန်ဆုံးရက်:</b> {expire_date}\n\n"
            f"🔑 <b>VPN Key အသစ်:</b>\n\n"
            f"<code>{new_key}</code>\n\n"
            f"☝️ အပေါ်က Key ကို <b>တစ်ချက်တည်း နှိပ်လိုက်ရုံဖြင့်</b> Auto Copy ကူးသွားပါလိမ့်မယ်ခင်ဗျာ။"
        )
        bot.send_message(target_chat_id, success_msg, parse_mode="HTML")
        try:
            bot.edit_message_text(call.message.text + f"\n\n✅ <b>REPLACED ({srv_title})</b>", chat_id=call.message.chat.id, message_id=call.message.message_id, parse_mode="HTML", reply_markup=None)
        except:
            pass

@bot.message_handler(func=lambda message: True)
def handle_all_messages(message):
    input_value = message.text.strip()
    chat_id = message.chat.id
    save_user_id(chat_id)

    if not is_user_subscribed(chat_id):
        send_force_join_message(chat_id)
        return

    # 📢 Broadcast Handler
    if str(chat_id) in [str(aid) for aid in ADMIN_CHAT_IDS] and get_broadcast_state(chat_id):
        set_broadcast_state(chat_id, False)
        all_users = load_all_users()
        success_count = 0

        bot.send_message(chat_id, f"⏳ Broadcast စာအား User စုစုပေါင်း ({len(all_users)}) ဆီ အကုန် ပို့ပေးနေပါသည်...")

        for uid in all_users:
            if str(uid) in [str(aid) for aid in ADMIN_CHAT_IDS]:
                continue
            try:
                bot.send_message(uid, input_value, parse_mode="HTML")
                success_count += 1
            except:
                pass

        bot.send_message(chat_id, f"✅ <b>Broadcast ပို့ပြီးပါပြီ!</b>\n\nအောင်မြင်စွာ ရောက်ရှိသွားသော User အရေအတွက်: <b>{success_count} / {len(all_users)}</b>", parse_mode="HTML")
        return

    if input_value in ["💳 Plan များ ကြည့်ရန်", "Plan များ ကြည့်ရန်", "💳 Plan ကြည့်ရန်"]:
        clear_all_states(chat_id)
        bot.send_message(chat_id, "🧸  လူကြီးမင်း ဝယ်ယူလိုသော VPN Plan ကို ရွေးချယ်ပေးပါခင်ဗျာ:", reply_markup=get_plan_keyboard())
        return
        
    if input_value in ["⚡️ Data Usage စစ်ရန်", "Data Usage စစ်ရန်", "⚡ Data Usage စစ်ရန်"]:
        clear_all_states(chat_id)
        check_guide = (
            "👇 ဝယ်ယူထားသော VPN Key ကို ဒီမှာ Paste ချပေးပါ:\n\n"
            " 🫶 Key ကို Copy ယူလာတဲ့ ss://... သို့မဟုတ် vless://... နဲ့စတဲ့ Key တစ်ခုလုံးကို ဒီ Chat ထဲသို့ တန်းပြီး Paste ချပို့ပြီး စစ်ဆေးနိုင်ပါတယ်ခင်ဗျာ။"
        )
        bot.send_message(chat_id, check_guide, reply_markup=get_back_inline_keyboard())
        return

    if input_value in ["🔄 Key လဲရန်", "Key အဆင်မပြေပါက လဲရန်"]:
        clear_all_states(chat_id)
        set_replacement_state(chat_id, True)
        replace_guide = (
            "🔄 <b>VPN Key အစားထိုး လဲလှယ်ရန်:</b>\n\n"
            "👇 အဆင်မပြေ ဖြစ်နေသော VPN Key (<code>ss://...</code> သို့မဟုတ် <code>vless://...</code>) ကို ဒီ Chat ထဲသို့ Paste ချ ပေးပို့ပေးပါခင်ဗျာ။\n"
            "<i>(Bot မှ ကျန်ရှိသော ရက်/Data များကို စစ်ဆေး၍ Admin ထံ အစားထိုး တောင်းဆိုပေးပါမည်။)</i>"
        )
        bot.send_message(chat_id, replace_guide, parse_mode="HTML", reply_markup=get_back_inline_keyboard())
        return

    if input_value in ["🎁 Public Free Key", "Public Free Key"]:
        clear_all_states(chat_id)
        free_key = "ss://Y2hhY2hhMjAtaWV0Zi1wb2x5MTMwNTpFQTVIUmNwYW1odkQyNnY5ZnNBNFgw@h.e.feature.hma.qzz.io:443/?outline=1#🚀🌩️ HMA | Thunder Strike ⚡️"
        free_text = (
            f"🎁 <b>H & E FEATURE PREMIUM VPN မှ လူအများအတွက် 1.5TB အထိ အခမဲ့သုံးစွဲနိုင်သော Premium Key ဖြစ်ပါတယ်ခင်ဗျာ။</b>\n\n"
            f"<code>{free_key}</code>\n\n"
            f"☝️ အပေါ်က ကီးလေးကို <b>တစ်ချက်တည်း နှိပ်လိုက်ရုံဖြင့်</b> Auto Copy ကူးသွားပါလိမ့်မယ်ခင်ဗျာ။"
        )
        bot.send_message(chat_id, free_text, parse_mode="HTML", reply_markup=get_back_inline_keyboard())
        return

    if input_value in ["🎁 Redeem Code", "Redeem Code"]:
        clear_all_states(chat_id)
        set_redeem_state(chat_id, True)
        redeem_guide = (
            "🎁 <b>Giveaway Redeem Code အသုံးပြုရန်:</b>\n\n"
            "👇 Admin ထံမှ ရရှိထားသော Redeem Code (ဥပမာ- <code>H&E-50GB-XXXXXX</code>) ကို ဒီ Chat ထဲသို့ Paste ချပို့ပေးပါခင်ဗျာ။"
        )
        bot.send_message(chat_id, redeem_guide, parse_mode="HTML", reply_markup=get_back_inline_keyboard())
        return

    if input_value in ["👨‍💻 Admin သို့ ဆက်သွယ်ရန်", "Admin သို့ ဆက်သွယ်ရန်"]:
        clear_all_states(chat_id)
        admin_link_markup = InlineKeyboardMarkup()
        admin_link_markup.add(InlineKeyboardButton("💬 စာပို့ရန် နှိပ်ပါ", url="https://t.me/H_M_A_2026"))
        admin_link_markup.add(InlineKeyboardButton("🔙 မူလ Menu သို့ ပြန်သွားရန်", callback_data="back_to_main"))
        bot.send_message(chat_id, "👇 အောက်ကခလုတ်ကိုနှိပ်ပြီး Admin ထံ တိုက်ရိုက်စာပို့ ဆက်သွယ်နိုင်ပါပြီဗျာ။", reply_markup=admin_link_markup)
        return

    if input_value == "🔍 Cus ရှာရန်":
        clear_all_states(chat_id)
        if str(chat_id) not in [str(aid) for aid in ADMIN_CHAT_IDS]:
            bot.reply_to(message, "❌ ခွင့်လွှတ်ပါ၊ ဒီ ခလုတ်သည် Admin သီးသန့် အသုံးပြုနိုင်သော ခလုတ်ဖြစ်ပါသည်။")
            return
        set_search_state(chat_id, True)
        bot.send_message(chat_id, "🔍 <b>Customer ရှာဖွေရန်:</b>\n\n👇 ရှာဖွေလိုသော <b>Cus နာမည်အစ စာလုံး</b> ကို ရိုက်ပို့ပေးပါခင်ဗျာ:", parse_mode="HTML", reply_markup=get_back_inline_keyboard())
        return

    if input_value == "🎁 Gen RD Code":
        clear_all_states(chat_id)
        if str(chat_id) not in [str(aid) for aid in ADMIN_CHAT_IDS]:
            bot.reply_to(message, "❌ ခွင့်လွှတ်ပါ၊ ဒီ ခလုတ်သည် Admin သီးသန့် အသုံးပြုနိုင်သော ခလုတ်ဖြစ်ပါသည်။")
            return
        bot.send_message(chat_id, "🎁 <b>Giveaway Redeem Code ထုတ်ရန်:</b>\n\nကျေးပြု၍ ဖန်တီးလိုသော <b>GB ပမာဏ</b> ကို ရွေးချယ်ပေးပါခင်ဗျာ:", parse_mode="HTML", reply_markup=get_admin_gb_keyboard())
        return

    if input_value == "📢 Broadcast စာပို့ရန်":
        clear_all_states(chat_id)
        if str(chat_id) not in [str(aid) for aid in ADMIN_CHAT_IDS]:
            bot.reply_to(message, "❌ ခွင့်လွှတ်ပါ၊ ဒီ ခလုတ်သည် Admin သီးသန့် အသုံးပြုနိုင်သော ခလုတ်ဖြစ်ပါသည်။")
            return
        all_users = load_all_users()
        set_broadcast_state(chat_id, True)
        bot.send_message(chat_id, f"📢 <b>Broadcast Announcement စာပို့ရန်:</b>\n\n👥 လက်ရှိ Bot သုံးစွဲသူ စုစုပေါင်း: <b>{len(all_users)} ယောက်</b>\n\n👇 ကြေညာလိုသော <b>စာသား (သို့မဟုတ်) ဓာတ်ပုံ</b> ပေးပို့ပေးပါခင်ဗျာ:", parse_mode="HTML", reply_markup=get_back_inline_keyboard())
        return

    if str(chat_id) in [str(aid) for aid in ADMIN_CHAT_IDS] and get_search_state(chat_id):
        set_search_state(chat_id, False)
        bot.send_message(chat_id, f"⏳ <b>'{input_value}'</b> ဖြင့် Cus များကို ရှာဖွေနေပါသည်...", parse_mode="HTML")
        matches, search_markup = search_users_by_query(input_value)
        if matches:
            search_markup.add(InlineKeyboardButton("🔙 မူလ Menu သို့ ပြန်သွားရန်", callback_data="back_to_main"))
            bot.send_message(chat_id, f"🔎 <b>ရှာဖွေတွေ့ရှိသော Customer စာရင်း ({len(matches)} ခု):</b>", parse_mode="HTML", reply_markup=search_markup)
        else:
            bot.send_message(chat_id, f"❌ <b>'{input_value}'</b> ဖြင့် ရှာမတွေ့ပါခင်ဗျာ။", parse_mode="HTML", reply_markup=get_back_inline_keyboard())
        return

    if get_replacement_state(chat_id):
        set_replacement_state(chat_id, False)
        bot.send_message(chat_id, "⏳ လူကြီးမင်း ပေးပို့ထားသော Key အား စစ်ဆေးနေပါသည်...")
        
        rem_gb, exp_date = 25.0, "30.09.2026"
        user_name = message.from_user.first_name or "Customer"
        username = f"@{message.from_user.username}" if message.from_user.username else "No Username"

        alert_text = (
            f"🔄 <b>KEY REPLACEMENT REQUEST</b>\n\n"
            f"👤 ဝယ်ယူသူ: {user_name} ({username})\n"
            f"🆔 Chat ID: <code>{chat_id}</code>\n"
            f"⚡️ ကျန်ရှိ Data: <b>{rem_gb} GB</b>\n"
            f"⏰ သက်တမ်းကုန်ရက်: <b>{exp_date}</b>"
        )

        markup = InlineKeyboardMarkup()
        markup.row(
            InlineKeyboardButton("📡 S1 (Outline) သို့ မွေးမည်", callback_data=f"replace_srv1_{chat_id}_{rem_gb}_{exp_date}"),
            InlineKeyboardButton("📡 S2 (Outline) သို့ မွေးမည်", callback_data=f"replace_srv2_{chat_id}_{rem_gb}_{exp_date}")
        )
        markup.row(InlineKeyboardButton("🟣 VLESS (3X-UI) သို့ မွေးမည်", callback_data=f"replace_vless_{chat_id}_{rem_gb}_{exp_date}"))

        for aid in ADMIN_CHAT_IDS:
            try:
                bot.send_message(aid, alert_text, parse_mode="HTML", reply_markup=markup)
            except:
                pass

        bot.send_message(chat_id, "✅ <b>Key အချက်အလက်များ တောင်းဆိုမှု အောင်မြင်ပါသည်။ Admin မှ စစ်ဆေး၍ Key အသစ် အမြန်ဆုံး လဲလှယ်ပေးပါမည်။</b>", parse_mode="HTML", reply_markup=get_back_inline_keyboard())
        return

    if get_redeem_state(chat_id):
        set_redeem_state(chat_id, False)
        codes = load_redeem_codes()
        if input_value in codes:
            code_info = codes[input_value]
            gb_val = code_info.get("gb", 25) if isinstance(code_info, dict) else int(code_info)
            days_val = code_info.get("days", 30) if isinstance(code_info, dict) else 30
            user_name = message.from_user.first_name or "Giveaway Winner"
            del codes[input_value]
            save_redeem_codes(codes)

            vpn_key, key_name, expire_date = create_3xui_vless_key(user_name, custom_gb=gb_val, target_chat_id=chat_id, custom_days=days_val, is_giveaway=True)
            if not vpn_key:
                vpn_key, key_name, expire_date = create_outline_key("1", user_name, custom_gb=gb_val, target_chat_id=chat_id, custom_days=days_val, is_giveaway=True)

            if vpn_key:
                success_msg = (
                    f"🎉 <b>ဂုဏ်ယူပါတယ်ခင်ဗျာ! Redeem Code အောင်မြင်စွာ အသုံးပြုပြီးပါပြီ။</b>\n\n"
                    f"👤 <b>အသုံးပြုသူ:</b> {user_name}\n"
                    f"🎁 <b>ရရှိသော Data GB:</b> {gb_val} GB\n"
                    f"⏰ <b>သက်တမ်းကုန်ဆုံးရက်:</b> {expire_date}\n\n"
                    f"🔑 <b>လူကြီးမင်း၏ VPN Key</b>\n\n"
                    f"<code>{vpn_key}</code>\n\n"
                    f"☝️ အပေါ်က Key ကို <b>တစ်ချက်တည်း နှိပ်လိုက်ရုံဖြင့်</b> Auto Copy ကူးသွားပါလိမ့်မယ်ခင်ဗျာ။"
                )
                bot.send_message(chat_id, success_msg, parse_mode="HTML", reply_markup=get_back_inline_keyboard())
                return
        else:
            bot.send_message(chat_id, "❌ <b>ထည့်သွင်းထားသော Redeem Code မှားယွင်းနေပါသည်ခင်ဗျာ။</b>", parse_mode="HTML", reply_markup=get_back_inline_keyboard())
            return

    if input_value == "📊 Total Data Usage":
        clear_all_states(chat_id)
        if str(chat_id) not in [str(aid) for aid in ADMIN_CHAT_IDS]:
            bot.reply_to(message, "❌ ခွင့်လွှတ်ပါ၊ ဒီ ခလုတ်သည် Admin သီးသန့် အသုံးပြုနိုင်သော ခလုတ်ဖြစ်ပါသည်။")
            return
        bot.send_message(chat_id, "📡 Server 1, 2 & 3X-UI Data Usage များကို တွက်ချက်နေပါသည်...")
        bot.send_message(chat_id, get_servers_total_usage(), parse_mode="HTML", reply_markup=get_back_inline_keyboard())
        return

    if input_value in ["💰 လစဉ် ဝင်ငွေ", "လစဉ် ဝင်ငွေ"]:
        clear_all_states(chat_id)
        if str(chat_id) not in [str(aid) for aid in ADMIN_CHAT_IDS]:
            bot.reply_to(message, "❌ ခွင့်လွှတ်ပါ၊ ဒီ ခလုတ်သည် Admin သီးသန့် အသုံးပြုနိုင်သော ခလုတ်ဖြစ်ပါသည်။")
            return
        bot.send_message(chat_id, get_monthly_revenue_report(), parse_mode="HTML", reply_markup=get_back_inline_keyboard())
        return

    if input_value in ["🔄 Bot Refresh", "/refresh"]:
        clear_all_states(chat_id)
        bot.send_message(chat_id, "🔄 <b>Bot စနစ်အား Refresh ပြုလုပ်ပြီးပါပြီခင်ဗျာ!</b>", parse_mode="HTML", reply_markup=get_main_menu_keyboard(chat_id))
        return

    not_found_msg = (
        "❌ <b>ခွင့်လွှတ်ပါဗျာ၊ တစ်ခုခုမှားနေပါတယ်ခင်ဗျာ။</b>\n\n"
        "💡 <i> Menu ခလုတ်များ အလုပ်မလုပ်ပါက သို့မဟုတ် Refresh လုပ်လိုပါက အောက်ပါ '🔄 Bot Refresh' ခလုတ် သို့မဟုတ် /start ကို နှိပ်ပေးပါခင်ဗျာ။</i>"
    )
    bot.reply_to(message, not_found_msg, parse_mode="HTML", reply_markup=get_main_menu_keyboard(chat_id))

@app.route('/cron-check', methods=['GET', 'POST'])
def cron_check():
    return jsonify({"status": "cron completed"}), 200

@app.route('/', defaults={'path': ''}, methods=['POST', 'GET'])
@app.route('/<path:path>', methods=['POST', 'GET'])
def index(path):
    if request.method == 'POST':
        json_string = request.get_data().decode('utf-8')
        update = telebot.types.Update.de_json(json_string)
        bot.process_new_updates([update])
        return jsonify({"status": "ok"}), 200
    return "Bot is running perfectly!", 200
