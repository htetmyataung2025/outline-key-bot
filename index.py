import os
import requests
import random
import string
import time
import uuid
from flask import Flask, request, jsonify
import telebot
from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton, ReplyKeyboardMarkup, KeyboardButton, WebAppInfo
import re
import base64
import json
import html
from datetime import datetime, timedelta
from dateutil.relativedelta import relativedelta

app = Flask(__name__)

# Token & API Configuration
TELEGRAM_TOKEN = "8779558815:AAEaXF6rRqCVM-PFhbOlwgubSknk5xTiKvU"

# 📢 Force Join Channel Configuration
REQUIRED_CHANNEL = "@hefeature"

# 🌐 API Server ၁ နှင့် ၂ လင့်ခ်များ (Outline)
OUTLINE_API_URL_1 = "https://h.e.feature.hma.qzz.io:49429/YkDBSn3KwUaICBvzDQtvxQ"
OUTLINE_API_URL_2 = "https://104.207.77.147:5714/UrZDutqOIvK931jb3x7hLA"

# ⚡️ 3X-UI Panel Configuration
XUI_BASE_URL = "https://h.e.feature.hma.qzz.io:14096"
XUI_WEB_PATH = "SHXjOMXGbiCuHQ6X1G"
XUI_USER = "hma"
XUI_PASS = "Hm@147025"
XUI_INBOUND_ID = 1  # Inbound ID 1 (#1 HMA, Port 8080)
XUI_DOMAIN = "h.e.feature.hma.qzz.io"
XUI_PORT = 8080

# 🔑 Admin Telegram Chat IDs (Admin ၂ ယောက်လုံး ပါဝင်သည်)
ADMIN_CHAT_IDS = ["8778394176", "6297145771"]

bot = telebot.TeleBot(TELEGRAM_TOKEN, threaded=False)
requests.packages.urllib3.disable_warnings()

# 🌐 Vercel Upstash Redis REST API Setup (Permanently Data သိမ်းရန်)
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

# Temp Files & Redis Fallback Configs
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

# Lock Check Function
def is_callback_processed(call_id):
    if call_id in PROCESSED_CALLBACKS:
        return True
    PROCESSED_CALLBACKS.add(call_id)
    if len(PROCESSED_CALLBACKS) > 1000:
        PROCESSED_CALLBACKS.clear()
    return False

# ---------------------------------------------------------
# 🔌 3X-UI PANEL HELPER FUNCTIONS
# ---------------------------------------------------------
def xui_login():
    session = requests.Session()
    login_url = f"{XUI_BASE_URL}/{XUI_WEB_PATH}/login"
    try:
        res = session.post(login_url, data={"username": XUI_USER, "password": XUI_PASS}, verify=False, timeout=8)
        if res.status_code == 200 and res.json().get("success"):
            return session
    except Exception as e:
        print("3X-UI Login Error:", e)
    return None

def create_3xui_vless_client(email, limit_bytes=0, expiry_timestamp=0):
    session = xui_login()
    if not session:
        return None, None, None

    client_uuid = str(uuid.uuid4())
    sub_id = ''.join(random.choices(string.ascii_lowercase + string.digits, k=16))
    
    client_item = {
        "id": client_uuid,
        "colId": "",
        "email": email,
        "subId": sub_id,
        "totalGB": limit_bytes,
        "expiryTime": expiry_timestamp,
        "enable": True,
        "tgId": "",
        "limitIp": 0,
        "flow": "xtls-rprx-vision"
    }

    add_url = f"{XUI_BASE_URL}/{XUI_WEB_PATH}/panel/api/inbounds/addClient"
    payload = {
        "id": XUI_INBOUND_ID,
        "settings": json.dumps({"clients": [client_item]})
    }

    try:
        res = session.post(add_url, json=payload, verify=False, timeout=8)
        if res.status_code == 200 and res.json().get("success"):
            vless_link = f"vless://{client_uuid}@{XUI_DOMAIN}:{XUI_PORT}?type=tcp&security=reality&flow=xtls-rprx-vision#{email}"
            return vless_link, client_uuid, email
    except Exception as e:
        print("3X-UI Create Client Error:", e)

    return None, None, None

def get_3xui_client_info(search_key):
    session = xui_login()
    if not session:
        return None

    try:
        res = session.get(f"{XUI_BASE_URL}/{XUI_WEB_PATH}/panel/api/inbounds/get/{XUI_INBOUND_ID}", verify=False, timeout=8)
        if res.status_code == 200 and res.json().get("success"):
            inbound = res.json().get("obj", {})
            settings = json.loads(inbound.get("settings", "{}"))
            clients = settings.get("clients", [])
            client_stats = inbound.get("clientStats", [])

            clean_search = search_key.replace("vless://", "").split("@")[0].split("#")[0].strip()

            target_client = None
            for c in clients:
                c_uuid = c.get("id", "")
                c_email = c.get("email", "")
                if clean_search in c_uuid or clean_search in c_email or clean_search in c.get("subId", ""):
                    target_client = c
                    break

            if target_client:
                c_email = target_client.get("email")
                c_uuid = target_client.get("id")

                stat_up, stat_down = 0, 0
                for st in client_stats:
                    if st.get("email") == c_email:
                        stat_up = st.get("up", 0)
                        stat_down = st.get("down", 0)
                        break

                return {
                    "email": c_email,
                    "uuid": c_uuid,
                    "total_bytes": target_client.get("totalGB", 0),
                    "used_bytes": stat_up + stat_down,
                    "expiry_time": target_client.get("expiryTime", 0),
                    "enable": target_client.get("enable", True)
                }
    except Exception as e:
        print("3X-UI Fetch Error:", e)
    return None

def delete_3xui_client(client_uuid):
    session = xui_login()
    if not session:
        return False
    try:
        del_url = f"{XUI_BASE_URL}/{XUI_WEB_PATH}/panel/api/inbounds/{XUI_INBOUND_ID}/delClient/{client_uuid}"
        res = session.post(del_url, verify=False, timeout=8)
        return res.status_code == 200 and res.json().get("success")
    except:
        return False

# ---------------------------------------------------------
# 🛠️ GENERAL SYSTEM UTILITIES & STORAGE
# ---------------------------------------------------------
def save_user_id(chat_id):
    users = redis_get("all_users") or []
    if str(chat_id) not in [str(u) for u in users]:
        users.append(str(chat_id))
        redis_set("all_users", users)

def load_all_users():
    data = redis_get("all_users")
    if data is not None:
        return data
    return []

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
    try:
        with open(STATE_FILE, 'w') as f:
            json.dump(plans, f)
    except:
        pass

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
    try:
        with open(MAPPING_FILE, 'w') as f:
            json.dump(mappings, f)
    except:
        pass

def load_sales_history():
    data = redis_get("sales_history")
    if data is not None:
        return data
    if os.path.exists(SALES_FILE):
        try:
            with open(SALES_FILE, 'r') as f:
                return json.load(f)
        except:
            pass
    return []

def save_sale_transaction(server_num, chat_id, plan_code, plan_name, months_count, price_int, protocol="outline", is_test=False):
    # 💡 Test Key သို့မဟုတ် စျေးနှုန်း 0 ဖြစ်ပါက ငွေစာရင်း (Sales History) ထဲ မပေါင်းထည့်ပါ
    if is_test or int(price_int) == 0:
        return

    sales = load_sales_history()
    now = datetime.utcnow() + timedelta(hours=6, minutes=30)  # MMT Timezone
    sale_data = {
        "timestamp": now.strftime("%Y-%m-%d %H:%M:%S"),
        "date": now.strftime("%Y-%m-%d"),
        "year": now.year,
        "month": now.month,
        "server": str(server_num),
        "protocol": protocol,
        "chat_id": str(chat_id),
        "plan_code": plan_code,
        "plan_name": plan_name,
        "months": months_count,
        "price": int(price_int)
    }
    sales.append(sale_data)
    redis_set("sales_history", sales)
    try:
        with open(SALES_FILE, 'w') as f:
            json.dump(sales, f)
    except:
        pass

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
        if not data and os.path.exists(ADMIN_MSG_MAP_FILE):
            with open(ADMIN_MSG_MAP_FILE, 'r') as f:
                data = json.load(f)
        return data.get(str(target_chat_id), {})
    except:
        return {}

def load_redeem_codes():
    data = redis_get("redeem_codes")
    if data is not None:
        return data
    if os.path.exists(REDEEM_FILE):
        try:
            with open(REDEEM_FILE, 'r') as f:
                return json.load(f)
        except:
            pass
    return {}

def save_redeem_codes(codes):
    redis_set("redeem_codes", codes)
    try:
        with open(REDEEM_FILE, 'w') as f:
            json.dump(codes, f)
    except:
        pass

def load_used_redeemers():
    data = redis_get("used_redeemers")
    if data is not None:
        return data
    if os.path.exists(USED_REDEEMERS_FILE):
        try:
            with open(USED_REDEEMERS_FILE, 'r') as f:
                return json.load(f)
        except:
            pass
    return []

def save_used_redeemer(chat_id):
    used_list = load_used_redeemers()
    if str(chat_id) not in used_list:
        used_list.append(str(chat_id))
        redis_set("used_redeemers", used_list)

def has_active_giveaway_key(chat_id):
    for api_url in [OUTLINE_API_URL_1, OUTLINE_API_URL_2]:
        try:
            res = requests.get(f"{api_url}/access-keys", verify=False, timeout=5)
            if res.status_code == 200:
                keys = res.json().get("accessKeys", [])
                for k in keys:
                    k_name = k.get("name", "")
                    if f"({chat_id})" in k_name and ("[gw]" in k_name.lower() or "giveaway" in k_name.lower()):
                        return True
        except:
            pass
    return False

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
    xui_keys, xui_rev, xui_today_keys, xui_today_rev = 0, 0, 0, 0

    s1_plans, s2_plans, xui_plans, today_plans = {}, {}, {}, {}

    for item in sales_history:
        item_year = item.get("year")
        item_month = item.get("month")
        
        if item_year == current_year and item_month == current_month:
            srv = str(item.get("server", "s1"))
            price = int(item.get("price", 0))
            p_name = item.get("plan_name", "Plan")
            p_months = item.get("months", 1)
            p_key_str = f"{p_name} [{p_months} လစာ]"
            is_today = (item.get("date") == today_str)

            if is_today:
                today_plans[p_key_str] = today_plans.get(p_key_str, 0) + 1

            if srv in ["1", "s1", "srv1"]:
                s1_keys += 1
                s1_rev += price
                s1_plans[p_key_str] = s1_plans.get(p_key_str, 0) + 1
                if is_today:
                    s1_today_keys += 1
                    s1_today_rev += price
            elif srv in ["xui", "vless"]:
                xui_keys += 1
                xui_rev += price
                xui_plans[p_key_str] = xui_plans.get(p_key_str, 0) + 1
                if is_today:
                    xui_today_keys += 1
                    xui_today_rev += price
            else:
                s2_keys += 1
                s2_rev += price
                s2_plans[p_key_str] = s2_plans.get(p_key_str, 0) + 1
                if is_today:
                    s2_today_keys += 1
                    s2_today_rev += price

    total_keys = s1_keys + s2_keys + xui_keys
    total_rev = s1_rev + s2_rev + xui_rev
    today_keys = s1_today_keys + s2_today_keys + xui_today_keys
    today_rev = s1_today_rev + s2_today_rev + xui_today_rev

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
        f"{format_sales_breakdown(s1_plans)}\n"
        f"💵 S1 လစဉ်ဝင်ငွေ: <b>{s1_rev:,} Ks</b>\n\n"
        f"📡 <b>Server 2 🇸🇬 (Outline):</b>\n"
        f"🔑 Total Paid Keys: <b>{s2_keys} ခု</b>\n"
        f"{format_sales_breakdown(s2_plans)}\n"
        f"💵 S2 လစဉ်ဝင်ငွေ: <b>{s2_rev:,} Ks</b>\n\n"
        f"⚡️ <b>3X-UI Server 🇸🇬 (VLESS):</b>\n"
        f"🔑 Total Paid Keys: <b>{xui_keys} ခု</b>\n"
        f"{format_sales_breakdown(xui_plans)}\n"
        f"💵 VLESS လစဉ်ဝင်ငွေ: <b>{xui_rev:,} Ks</b>\n\n"
        f"━━━━━━━━━━━━━━━━━\n"
        f"🌐 <b>Total This Month Paid Keys:</b> <b>{total_keys} ခု</b>\n"
        f"💎 <b>ဒီလ စုစုပေါင်း ဝင်ငွေ:</b> <b>{total_rev:,} MMK</b>\n\n"
        f"<i>* မှတ်ချက်: Test Keys / Discount စျေးနှုန်းများအား အမှန်တကယ် ပမာဏအတိုင်း အတိအကျ တွက်ချက်ထားပါသည်။</i>"
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

    s1_total, s1_bytes = get_server_stats(OUTLINE_API_URL_1)
    s2_total, s2_bytes = get_server_stats(OUTLINE_API_URL_2)

    s1_gb = bytes_to_gb(s1_bytes)
    s2_gb = bytes_to_gb(s2_bytes)
    overall_bytes = s1_bytes + s2_bytes
    overall_gb = bytes_to_gb(overall_bytes)

    report = (
        f"📊 <b>SERVER DATA STATS REPORT</b>\n\n"
        f"📡 <b>Server 1 🇸🇬 (Outline)</b>\n"
        f"🔑 Total Keys: <b>{s1_total}</b>\n"
        f"⚡️ Total Usage: <b>{s1_gb} GB</b>\n\n"
        f"📡 <b>Server 2 🇸🇬 (Outline)</b>\n"
        f"🔑 Total Keys: <b>{s2_total}</b>\n"
        f"⚡️ Total Usage: <b>{s2_gb} GB</b>\n"
        f"━━━━━━━━━━━━━━━━━\n"
        f"🌟 <b>Overall Total Usage:</b> <b>{overall_gb} GB (~{round(overall_gb/1000, 2)} TB)</b>"
    )
    return report

def search_users_by_query(query):
    query_clean = query.strip().lower()
    markup = InlineKeyboardMarkup()
    found_matches = []

    for server_num, api_url in [("1", OUTLINE_API_URL_1), ("2", OUTLINE_API_URL_2)]:
        try:
            res = requests.get(f"{api_url}/access-keys", verify=False, timeout=8)
            if res.status_code == 200:
                keys = res.json().get("accessKeys", [])
                for k in keys:
                    k_name = k.get("name", "").strip()
                    k_name_lower = k_name.lower()

                    if len(query_clean) == 1:
                        if k_name_lower.startswith(query_clean):
                            found_matches.append((server_num, str(k.get("id")), k_name))
                    else:
                        if query_clean in k_name_lower:
                            found_matches.append((server_num, str(k.get("id")), k_name))
        except:
            pass

    for server_num, key_id, k_name in found_matches[:30]:
        srv_icon = "📡 S1🇸🇬" if server_num == "1" else "📡 S2🇸🇬"
        markup.add(InlineKeyboardButton(f"{srv_icon} | {k_name}", callback_data=f"viewkey_{server_num}_{key_id}"))

    return found_matches, markup

# ---------------------------------------------------------
# 🤖 BOT CALLBACKS & HANDLERS
# ---------------------------------------------------------
@bot.callback_query_handler(func=lambda call: call.data == "back_to_main")
def handle_back_to_main_callback(call):
    chat_id = call.message.chat.id
    clear_all_states(chat_id)
    bot.answer_callback_query(call.id, "🔙 မူလ Menu သို့ ပြန်သွားပါပြီ။")
    try:
        bot.delete_message(chat_id, call.message.message_id)
    except:
        pass
    bot.send_message(chat_id, "👋 မင်္ဂလာပါ! H & E FEATURE PREMIUM VPN ဝန်ဆောင်မှု Bot မှ ကြိုဆိုပါတယ်။\n\n👇 အောက်ခြေက Menu Button တွေကို အသုံးပြုပြီး မိမိတို့ အလိုရှိရာကို ရွေးချယ်နိုင်ပါတယ်ခင်ဗျာ။", reply_markup=get_main_menu_keyboard(chat_id))

@bot.callback_query_handler(func=lambda call: call.data == "back_to_gen_rd")
def handle_back_to_gen_rd(call):
    bot.answer_callback_query(call.id)
    if str(call.message.chat.id) not in [str(aid) for aid in ADMIN_CHAT_IDS]:
        return
    bot.edit_message_text(
        "🎁 <b>Giveaway Redeem Code ထုတ်ရန်:</b>\n\nကျေးပြု၍ ဖန်တီးလိုသော <b>GB ပမာဏ</b> ကို ရွေးချယ်ပေးပါခင်ဗျာ:",
        chat_id=call.message.chat.id, message_id=call.message.message_id, parse_mode="HTML", reply_markup=get_admin_gb_keyboard()
    )

@bot.callback_query_handler(func=lambda call: call.data.startswith("viewkey_"))
def handle_view_key_detail(call):
    bot.answer_callback_query(call.id)
    if str(call.message.chat.id) not in [str(aid) for aid in ADMIN_CHAT_IDS]:
        return
    
    parts = call.data.split("_")
    server_num, key_id = parts[1], parts[2]
    api_url = OUTLINE_API_URL_1 if server_num == "1" else OUTLINE_API_URL_2
    
    try:
        keys_resp = requests.get(f"{api_url}/access-keys", verify=False, timeout=8)
        metrics_resp = requests.get(f"{api_url}/metrics/transfer", verify=False, timeout=8)
        
        if keys_resp.status_code == 200:
            keys_data = keys_resp.json().get("accessKeys", [])
            bytes_transferred = metrics_resp.json().get("bytesTransferredByUserId", {}) if metrics_resp.status_code == 200 else {}
            
            target_key = next((k for k in keys_data if str(k.get("id")) == str(key_id)), None)
            if target_key:
                full_name = target_key.get("name", "Unnamed Key")
                raw_access_url = target_key.get("accessUrl", "")
                final_key = f"{raw_access_url}#{full_name}" if full_name else raw_access_url
                
                limit_bytes = target_key.get("dataLimit", {}).get("bytes")
                plan_gb = f"{bytes_to_gb(limit_bytes)} GB" if limit_bytes else "Unlimited"
                usage_gb = bytes_to_gb(bytes_transferred.get(str(key_id), 0))
                
                date_match = re.search(r'\d{1,2}\.\d{1,2}\.(\d{4}|\d{2})', full_name)
                end_date = date_match.group(0) if date_match else "မသိရှိပါ"
                
                markup = InlineKeyboardMarkup()
                markup.add(InlineKeyboardButton("🗑️ Key ဖျက်ရန် (Delete)", callback_data=f"delkey_ask_{server_num}_{key_id}"))

                detail_msg = (
                    f"👤 <b>Customer Information✅ </b>\n\n"
                    f"🤖 <b>Name:</b> {html.escape(full_name)}\n"
                    f"📡 <b>Server:</b> Server {server_num} 🇸🇬\n"
                    f"⚡️ <b>Data Usage :</b> <code>{usage_gb} GB</code> / <code>{plan_gb}</code>\n"
                    f"⏰ <b>Expired Date:</b> {end_date}\n"
                    f"🔑 <b>VPN Key Link:</b>\n\n"
                    f"<code>{final_key}</code>"
                )
                bot.send_message(call.message.chat.id, detail_msg, parse_mode="HTML", reply_markup=markup)
    except Exception as e:
        bot.send_message(call.message.chat.id, f"❌ Error: {str(e)}")

@bot.callback_query_handler(func=lambda call: call.data.startswith("delkey_"))
def handle_admin_del_key(call):
    bot.answer_callback_query(call.id)
    if is_callback_processed(f"del_{call.message.message_id}_{call.data}") or str(call.message.chat.id) not in [str(aid) for aid in ADMIN_CHAT_IDS]:
        return

    parts = call.data.split("_")
    action, server_num, key_id = parts[1], parts[2], parts[3]

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
                bot.edit_message_text(f"❌ Key ဖျက်ရာတွင် အမှားအယွင်း ရှိနေပါသည်", chat_id=call.message.chat.id, message_id=call.message.message_id)
        except Exception as e:
            bot.edit_message_text(f"❌ Error: {str(e)}", chat_id=call.message.chat.id, message_id=call.message.message_id)

    elif action == "cancel":
        bot.edit_message_text("❌ Key ဖျက်ခြင်းကို ပယ်ဖျက်လိုက်ပါပြီခင်ဗျာ။", chat_id=call.message.chat.id, message_id=call.message.message_id)

# ---------------------------------------------------------
# 💳 PLAN & PROTOCOL SELECTION
# ---------------------------------------------------------
@bot.callback_query_handler(func=lambda call: call.data.startswith("selectplan_"))
def handle_select_plan(call):
    bot.answer_callback_query(call.id)
    chat_id = call.message.chat.id
    plan_code = call.data.replace("selectplan_", "")
    
    markup = InlineKeyboardMarkup()
    markup.row(
        InlineKeyboardButton("📡 Outline (SS)", callback_data=f"selectproto_{plan_code}_outline"),
        InlineKeyboardButton("⚡️ VLESS (3X-UI)", callback_data=f"selectproto_{plan_code}_vless")
    )
    markup.row(InlineKeyboardButton("🔙 Plan များသို့ ပြန်သွားရန်", callback_data="back_to_plans"))
    
    bot.edit_message_text(
        "⚡️ <b>အသုံးပြုလိုသော Protocol/Type ကို ရွေးချယ်ပေးပါခင်ဗျာ:</b>\n\n"
        "• <b>Outline:</b> Outline VPN / Shadowsocks App ဖြင့် သုံးရန်\n"
        "• <b>VLESS:</b> v2rayNG, Streisand, Sing-box App ဖြင့် သုံးရန်",
        chat_id=chat_id, message_id=call.message.message_id, parse_mode="HTML", reply_markup=markup
    )

@bot.callback_query_handler(func=lambda call: call.data.startswith("selectproto_"))
def handle_select_proto(call):
    bot.answer_callback_query(call.id)
    chat_id = call.message.chat.id
    parts = call.data.split("_")
    plan_code = parts[1]
    proto = parts[2]

    plan = PLANS.get(plan_code)
    if plan:
        amount = plan["price"]
        plan_data = {
            "code": plan_code,
            "name": plan["name"],
            "data": plan["data"],
            "protocol": proto,
            "months": 1,
            "price_str": f"{amount:,} Ks",
            "price_int": amount
        }
        save_user_plan(chat_id, plan_data)

        payment_text = (
            f"✅ သင်ရွေးချယ်ထားသော Plan:\n"
            f"📌 {plan['name']} ({plan['data']}) - [{proto.upper()}]\n\n"
            f"━━━━━━━━━━━━━━━\n"
            f"💰 ငွေလွှဲရမည့် အကောင့်အချက်အလက်များ:\n\n"
            f"📱 KBZ Pay - 09699970092\n👤 Htet Myat Aung\n\n"
            f"📱 Wave Pay - 09699970092\n👤 Htet Myat Aung\n\n"
            f"📱 AYA Pay - 09699970092\n👤 Htet Myat Aung\n\n"
            f"📱 Uab Pay - 09699970092\n👤 Htet Myat Aung\n"
            f"━━━━━━━━━━━━━━━\n\n"
            f"🙏🏻 ငွေလွှဲပြီး Screenshotလေး ပို့ပေးပါခင်ဗျာ🥰\n"
            f"(ပြေစာစစ်ဆေးပြီးသည်နှင့် VPN Key ကို အမြန်ဆုံး ပို့ပေးပါမည်။)"
        )
        markup = InlineKeyboardMarkup()
        markup.row(InlineKeyboardButton("🔙 Plan များသို့ ပြန်သွားရန်", callback_data="back_to_plans"))
        markup.row(InlineKeyboardButton("🔙 မူလ Menu သို့ ပြန်သွားရန်", callback_data="back_to_main"))
        bot.edit_message_text(payment_text, chat_id=chat_id, message_id=call.message.message_id, reply_markup=markup)

@bot.callback_query_handler(func=lambda call: call.data == "back_to_plans")
def handle_back_to_plans(call):
    bot.answer_callback_query(call.id)
    chat_id = call.message.chat.id
    bot.edit_message_text("🧸 ကျေးဇူးပြု၍ ဝယ်ယူလိုသော VPN Plan ကို ရွေးချယ်ပေးပါခင်ဗျာ:", chat_id=chat_id, message_id=call.message.message_id, reply_markup=get_plan_keyboard())

# ---------------------------------------------------------
# 👑 ADMIN APPROVAL HANDLER (OPTIMIZED SHORT CALLBACK)
# ---------------------------------------------------------
@bot.callback_query_handler(func=lambda call: call.data.startswith("ap_"))
def handle_approve_callback(call):
    try:
        bot.answer_callback_query(call.id, "⏳ Key ထုတ်ပေးနေပါသည်...")
    except:
        pass

    if is_callback_processed(f"appr_{call.message.message_id}_{call.data}") or str(call.message.chat.id) not in [str(aid) for aid in ADMIN_CHAT_IDS]:
        return

    try:
        parts = call.data.split("_")  # ap_srv_chatid_plan
        target_srv = parts[1]       # s1, s2, xui
        target_chat_id = parts[2]
        plan_code = parts[3]
        months_count = 1

        is_test_key = (plan_code == "test")
        plan_info = PLANS.get(plan_code, {"name": "Test Key", "data": "5 GB", "bytes": 5 * 1000**3, "price": 0})
        user_plans = load_user_plans()
        u_plan = user_plans.get(str(target_chat_id), {})
        price_int = 0 if is_test_key else u_plan.get("price_int", plan_info.get("price", 0))

        chat_info = bot.get_chat(target_chat_id)
        user_name = f"{chat_info.first_name or ''} {chat_info.last_name or ''}".strip() or "HMA Customer"

        vpn_key = None
        expire_date = (datetime.now() + relativedelta(months=months_count)).strftime("%d.%m.%Y")
        disp_gb = f"{int(plan_info['data'].split()[0]) * months_count} GB" if 'data' in plan_info else "5 GB"

        if target_srv == "xui":
            limit_bytes = plan_info['bytes'] * months_count
            expiry_ts = int((datetime.now() + relativedelta(months=months_count)).timestamp() * 1000)
            email_name = f"{'TEST_' if is_test_key else ''}{user_name.replace(' ', '_')}_{target_chat_id}"
            
            vless_link, _, _ = create_3xui_vless_client(email_name, limit_bytes=limit_bytes, expiry_timestamp=expiry_ts)
            vpn_key = vless_link
            srv_title = "3X-UI VLESS ⚡️"
        else:
            srv_num = "1" if target_srv == "s1" else "2"
            api_url = OUTLINE_API_URL_1 if srv_num == "1" else OUTLINE_API_URL_2
            res = requests.post(f"{api_url}/access-keys", verify=False, timeout=8)
            if res.status_code in [200, 201]:
                k_data = res.json()
                key_id = k_data.get("id")
                prefix_tag = "[TEST] " if is_test_key else ""
                key_name = f"{prefix_tag}{user_name} ({target_chat_id}) {expire_date}"
                requests.put(f"{api_url}/access-keys/{key_id}/name", data={"name": key_name}, verify=False)
                requests.put(f"{api_url}/access-keys/{key_id}/data-limit", json={"limit": {"bytes": plan_info['bytes'] * months_count}}, verify=False)
                vpn_key = f"{k_data.get('accessUrl')}#{key_name}"
            srv_title = f"Outline Server {srv_num} 🇸🇬"

        if vpn_key:
            save_sale_transaction(target_srv, target_chat_id, plan_code, plan_info['name'], months_count, price_int, protocol=target_srv, is_test=is_test_key)
            
            test_tag = "🧪 <b>[TEST KEY]</b>\n" if is_test_key else ""
            success_msg = (
                f"🎉 {test_tag}<b>ငွေလွှဲမှု အောင်မြင်စွာ အတည်ပြုပြီးပါပြီခင်ဗျာ။</b>\n\n"
                f"👤 <b>ဝယ်ယူသူ:</b> {user_name}\n"
                f"💳 <b>Plan:</b> {plan_info['name']} ({disp_gb}) [{srv_title}]\n"
                f"⏰ <b>သက်တမ်းကုန်ဆုံးရက်:</b> {expire_date}\n\n"
                f"🔑 <b>လူကြီးမင်း၏ VPN Key:</b>\n\n"
                f"<code>{vpn_key}</code>\n\n"
                f"☝️ တစ်ချက်တည်း နှိပ်၍ Auto Copy ကူးသွားပါလိမ့်မယ်ခင်ဗျာ။"
            )
            bot.send_message(target_chat_id, success_msg, parse_mode="HTML")
            
            try:
                bot.edit_message_caption(chat_id=call.message.chat.id, message_id=call.message.message_id, caption=call.message.caption + f"\n\n✅ <b>DONE ({srv_title}) {'[TEST]' if is_test_key else ''}</b>", parse_mode="HTML")
            except:
                pass
        else:
            bot.send_message(call.message.chat.id, "❌ Key မွေးရာတွင် Error ဖြစ်ပေါ်နေပါသည်။ Server/Panel Config ကို စစ်ဆေးပါ။")
    except Exception as e:
        print("Approve Error:", e)

# 📸 Photo Message Handler
@bot.message_handler(content_types=['photo'])
def handle_photo_messages(message):
    chat_id = message.chat.id
    save_user_id(chat_id)

    if not is_user_subscribed(chat_id):
        send_force_join_message(chat_id)
        return

    # Broadcast Photo Handler
    if str(chat_id) in [str(aid) for aid in ADMIN_CHAT_IDS] and get_broadcast_state(chat_id):
        set_broadcast_state(chat_id, False)
        all_users = load_all_users()
        success_count = 0
        photo_id = message.photo[-1].file_id
        caption_text = message.caption or ""

        bot.send_message(chat_id, f"⏳ ပုံပါသော Broadcast စာအား User စုစုပေါင်း ({len(all_users)}) ဆီ ပို့ပေးနေပါသည်...")
        for uid in all_users:
            if str(uid) in [str(aid) for aid in ADMIN_CHAT_IDS]:
                continue
            try:
                bot.send_photo(uid, photo_id, caption=caption_text, parse_mode="HTML")
                success_count += 1
            except:
                pass
        bot.send_message(chat_id, f"✅ <b>Broadcast ပို့ပြီးပါပြီ!</b>\n\nရောက်ရှိသွားသော User: <b>{success_count} / {len(all_users)}</b>", parse_mode="HTML")
        return

    # Payment Screenshot Handler
    clear_all_states(chat_id)
    user_plans = load_user_plans()
    if str(chat_id) not in user_plans:
        bot.reply_to(message, "⚠️ ခွင့်လွှတ်ပါ၊ '💳 Plan များ ကြည့်ရန်' ခလုတ်ကို အရင်နှိပ်ပြီး Plan ရွေးချယ်ပေးပါဦးခင်ဗျာ။")
        return

    plan_info = user_plans.get(str(chat_id))
    plan_code = plan_info.get('code', 'starter')
    proto = plan_info.get('protocol', 'outline')
    
    admin_alert_text = (
        f"💰 <b>ငွေလွှဲပြေစာအသစ် [{proto.upper()}]</b>\n"
        f"👤 ဝယ်ယူသူ: {message.from_user.first_name} (@{message.from_user.username or 'No Username'})\n"
        f"📦 Plan: {plan_info['name']} ({plan_info.get('data', '')})\n"
        f"💵 ကျသင့်ငွေ: {plan_info.get('price_str', '')}\n"
        f"🆔 User Chat ID: {chat_id}"
    )

    markup = InlineKeyboardMarkup()
    if proto == "vless":
        markup.row(InlineKeyboardButton("⚡️ Approve 3X-UI VLESS", callback_data=f"ap_xui_{chat_id}_{plan_code}"))
        markup.row(InlineKeyboardButton("🧪 Test Key (0 Ks)", callback_data=f"ap_xui_{chat_id}_test"))
    else:
        markup.row(
            InlineKeyboardButton("📡 S1 Outline", callback_data=f"ap_s1_{chat_id}_{plan_code}"),
            InlineKeyboardButton("📡 S2 Outline", callback_data=f"ap_s2_{chat_id}_{plan_code}")
        )
        markup.row(InlineKeyboardButton("🧪 Test Key (0 Ks)", callback_data=f"ap_s1_{chat_id}_test"))

    for admin_id in ADMIN_CHAT_IDS:
        try:
            bot.send_photo(admin_id, message.photo[-1].file_id, caption=admin_alert_text, parse_mode="HTML", reply_markup=markup)
        except:
            pass
    bot.reply_to(message, "💌 ငွေလွှဲပြေစာအား စစ်ဆေးနေပါသည်။ Admin အတည်ပြုပြီးပါက VPN Key ကို ပို့ပေးပါမည်။ ကျေးဇူးတင်ပါသည်ခင်ဗျာ။ 🙏")

# ---------------------------------------------------------
# 💬 ALL TEXT MESSAGES & HANDLERS
# ---------------------------------------------------------
@bot.message_handler(func=lambda message: True)
def handle_all_messages(message):
    input_value = message.text.strip()
    chat_id = message.chat.id
    save_user_id(chat_id)

    if not is_user_subscribed(chat_id):
        send_force_join_message(chat_id)
        return

    # Broadcast Text Handler
    if str(chat_id) in [str(aid) for aid in ADMIN_CHAT_IDS] and get_broadcast_state(chat_id):
        set_broadcast_state(chat_id, False)
        all_users = load_all_users()
        success_count = 0
        bot.send_message(chat_id, f"⏳ Broadcast စာအား User ({len(all_users)}) ဆီ ပို့ပေးနေပါသည်...")
        for uid in all_users:
            if str(uid) in [str(aid) for aid in ADMIN_CHAT_IDS]:
                continue
            try:
                bot.send_message(uid, input_value, parse_mode="HTML")
                success_count += 1
            except:
                pass
        bot.send_message(chat_id, f"✅ <b>Broadcast ပို့ပြီးပါပြီ!</b>\n\nရောက်ရှိသွားသော User: <b>{success_count} / {len(all_users)}</b>", parse_mode="HTML")
        return

    if input_value in ["💳 Plan များ ကြည့်ရန်"]:
        clear_all_states(chat_id)
        bot.send_message(chat_id, "🧸 လူကြီးမင်း ဝယ်ယူလိုသော VPN Plan ကို ရွေးချယ်ပေးပါခင်ဗျာ:", reply_markup=get_plan_keyboard())
        return

    if input_value in ["⚡️ Data Usage စစ်ရန်"]:
        clear_all_states(chat_id)
        bot.send_message(chat_id, "👇 ဝယ်ယူထားသော VPN Key (<code>ss://...</code> သို့မဟုတ် <code>vless://...</code>) ကို Paste ချ ပို့ပေးပါခင်ဗျာ:", parse_mode="HTML", reply_markup=get_back_inline_keyboard())
        return

    if input_value in ["🔄 Key လဲရန်"]:
        clear_all_states(chat_id)
        set_replacement_state(chat_id, True)
        bot.send_message(chat_id, "🔄 <b>VPN Key အစားထိုး လဲလှယ်ရန်:</b>\n\n👇 အဆင်မပြေ ဖြစ်နေသော VPN Key ကို ဒီ Chat ထဲသို့ Paste ချ ပေးပို့ပေးပါခင်ဗျာ။", parse_mode="HTML", reply_markup=get_back_inline_keyboard())
        return

    if input_value in ["🎁 Public Free Key"]:
        clear_all_states(chat_id)
        free_key = "ss://Y2hhY2hhMjAtaWV0Zi1wb2x5MTMwNTpFQTVIUmNwYW1odkQyNnY5ZnNBNFgw@h.e.feature.hma.qzz.io:443/?outline=1#🚀🌩️ HMA | Thunder Strike ⚡️"
        free_text = f"🎁 <b>H & E FEATURE VPN 1.5TB Free Key:</b>\n\n<code>{free_key}</code>\n\n☝️ တစ်ချက်တည်း နှိပ်၍ Auto Copy ယူနိုင်ပါသည်ခင်ဗျာ။"
        bot.send_message(chat_id, free_text, parse_mode="HTML", reply_markup=get_back_inline_keyboard())
        return

    if input_value in ["🎁 Redeem Code"]:
        clear_all_states(chat_id)
        set_redeem_state(chat_id, True)
        bot.send_message(chat_id, "🎁 <b>Giveaway Redeem Code အသုံးပြုရန်:</b>\n\n👇 Admin ထံမှ ရရှိထားသော Code ကို Paste ချ ပို့ပေးပါခင်ဗျာ။", parse_mode="HTML", reply_markup=get_back_inline_keyboard())
        return

    if input_value in ["👨‍💻 Admin သို့ ဆက်သွယ်ရန်"]:
        clear_all_states(chat_id)
        markup = InlineKeyboardMarkup()
        markup.add(InlineKeyboardButton("💬 စာပို့ရန် နှိပ်ပါ", url="https://t.me/H_M_A_2026"))
        markup.add(InlineKeyboardButton("🔙 မူလ Menu သို့ ပြန်သွားရန်", callback_data="back_to_main"))
        bot.send_message(chat_id, "👇 အောက်ကခလုတ်ကိုနှိပ်ပြီး Admin ထံ ဆက်သွယ်နိုင်ပါပြီဗျာ။", reply_markup=markup)
        return

    if input_value == "🔍 Cus ရှာရန်" and str(chat_id) in [str(aid) for aid in ADMIN_CHAT_IDS]:
        clear_all_states(chat_id)
        set_search_state(chat_id, True)
        bot.send_message(chat_id, "🔍 <b>Customer ရှာဖွေရန်:</b>\n\n👇 ရှာဖွေလိုသော Cus နာမည်အစ စာလုံးကို ရိုက်ပို့ပေးပါခင်ဗျာ:", parse_mode="HTML", reply_markup=get_back_inline_keyboard())
        return

    if input_value == "🎁 Gen RD Code" and str(chat_id) in [str(aid) for aid in ADMIN_CHAT_IDS]:
        clear_all_states(chat_id)
        bot.send_message(chat_id, "🎁 <b>Giveaway Redeem Code ထုတ်ရန်:</b>\n\nGB ပမာဏ ကို ရွေးချယ်ပေးပါခင်ဗျာ:", parse_mode="HTML", reply_markup=get_admin_gb_keyboard())
        return

    if input_value == "📢 Broadcast စာပို့ရန်" and str(chat_id) in [str(aid) for aid in ADMIN_CHAT_IDS]:
        clear_all_states(chat_id)
        set_broadcast_state(chat_id, True)
        bot.send_message(chat_id, f"📢 <b>Broadcast စာပို့ရန်:</b>\n\n👥 လက်ရှိ User စုစုပေါင်း: <b>{len(load_all_users())} ယောက်</b>\n\n👇 ကြေညာလိုသော စာ/ပုံ ပို့ပေးပါခင်ဗျာ:", parse_mode="HTML", reply_markup=get_back_inline_keyboard())
        return

    if input_value == "📊 Total Data Usage" and str(chat_id) in [str(aid) for aid in ADMIN_CHAT_IDS]:
        clear_all_states(chat_id)
        bot.send_message(chat_id, get_servers_total_usage(), parse_mode="HTML", reply_markup=get_back_inline_keyboard())
        return

    if input_value in ["💰 လစဉ် ဝင်ငွေ"] and str(chat_id) in [str(aid) for aid in ADMIN_CHAT_IDS]:
        clear_all_states(chat_id)
        bot.send_message(chat_id, get_monthly_revenue_report(), parse_mode="HTML", reply_markup=get_back_inline_keyboard())
        return

    if input_value in ["🔄 Bot Refresh", "/refresh"]:
        clear_all_states(chat_id)
        bot.send_message(chat_id, "🔄 <b>Bot စနစ်အား Refresh ပြုလုပ်ပြီးပါပြီခင်ဗျာ!</b>", parse_mode="HTML", reply_markup=get_main_menu_keyboard(chat_id))
        return

    # ⚡️ Check VLESS Data Usage
    if input_value.startswith("vless://") or "xtls-rprx-vision" in input_value:
        xui_info = get_3xui_client_info(input_value)
        if xui_info:
            used_gb = bytes_to_gb(xui_info["used_bytes"])
            total_gb = bytes_to_gb(xui_info["total_bytes"]) if xui_info["total_bytes"] > 0 else "Unlimited"
            exp_date = datetime.fromtimestamp(xui_info["expiry_time"] / 1000).strftime("%d.%m.%Y") if xui_info["expiry_time"] > 0 else "Unlimited"
            
            res_text = (
                f"⚡️ <b>3X-UI VLESS Key Data Stats</b>\n\n"
                f"👤 Client: {xui_info['email']}\n"
                f"💳 Total Plan: {total_gb} GB\n"
                f"⚡️ Used Data: {used_gb} GB\n"
                f"⏰ Expire Date: {exp_date}"
            )
            bot.reply_to(message, res_text, parse_mode="HTML", reply_markup=get_back_inline_keyboard())
            return

    bot.reply_to(message, "❌ <b>ခွင့်လွှတ်ပါဗျာ၊ တစ်ခုခုမှားနေပါတယ်ခင်ဗျာ။ Menu ခလုတ် သို့မဟုတ် /start ကို နှိပ်ပေးပါခင်ဗျာ။</b>", parse_mode="HTML", reply_markup=get_main_menu_keyboard(chat_id))

# ---------------------------------------------------------
# 🌐 CRON & WEBHOOK SERVER INDEX
# ---------------------------------------------------------
@app.route('/cron-check', methods=['GET', 'POST'])
def cron_check():
    today = (datetime.utcnow() + timedelta(hours=6, minutes=30)).date()
    notified_count, deleted_count = 0, 0

    for api_url in [OUTLINE_API_URL_1, OUTLINE_API_URL_2]:
        try:
            keys_resp = requests.get(f"{api_url}/access-keys", verify=False, timeout=8)
            metrics_resp = requests.get(f"{api_url}/metrics/transfer", verify=False, timeout=8)
            if keys_resp.status_code != 200:
                continue
            
            keys_data = keys_resp.json().get("accessKeys", [])
            bytes_transferred = metrics_resp.json().get("bytesTransferredByUserId", {})

            for key in keys_data:
                full_name = key.get("name", "")
                key_id = str(key.get("id"))
                limit_bytes = key.get("dataLimit", {}).get("bytes")
                usage_bytes = bytes_transferred.get(key_id, 0)

                should_delete = False
                date_matches = list(re.finditer(r'(\d{1,2})\.(\d{1,2})\.(\d{2,4})', full_name))
                if date_matches:
                    date_match = date_matches[-1]
                    try:
                        k_day, k_month = int(date_match.group(1)), int(date_match.group(2))
                        k_year_raw = date_match.group(3)
                        k_year = int("20" + k_year_raw) if len(k_year_raw) == 2 else int(k_year_raw)
                        if today > datetime(k_year, k_month, k_day).date():
                            should_delete = True
                    except:
                        pass

                if should_delete:
                    try:
                        del_res = requests.delete(f"{api_url}/access-keys/{key_id}", verify=False, timeout=8)
                        if del_res.status_code in [200, 204]:
                            deleted_count += 1
                    except:
                        pass
        except:
            pass

    return jsonify({"status": "cron completed", "notified": notified_count, "deleted": deleted_count}), 200

@app.route('/', defaults={'path': ''}, methods=['POST', 'GET'])
@app.route('/<path:path>', methods=['POST', 'GET'])
def index(path):
    if request.method == 'POST':
        json_string = request.get_data().decode('utf-8')
        update = telebot.types.Update.de_json(json_string)
        bot.process_new_updates([update])
        return jsonify({"status": "ok"}), 200
    return "Bot is running perfectly!", 200
