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

PROCESSED_CALLBACKS = set()

def is_callback_processed(call_id):
    if call_id in PROCESSED_CALLBACKS:
        return True
    PROCESSED_CALLBACKS.add(call_id)
    if len(PROCESSED_CALLBACKS) > 1000:
        PROCESSED_CALLBACKS.clear()
    return False

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
    return users

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
    return {}

def save_user_plan(chat_id, plan_data):
    plans = load_user_plans()
    plans[str(chat_id)] = plan_data
    redis_set("user_plans", plans)

def load_key_mappings():
    data = redis_get("key_mappings")
    if data is not None:
        return data
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
    if str(chat_id) in [str(aid) for aid in ADMIN_CHAT_IDS]:
        return
    sales = load_sales_history()
    now = datetime.utcnow() + timedelta(hours=6, minutes=30)
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

# 🟣 3X-UI Panel API Helper Functions (TotalGB Fixed)
def get_3xui_session():
    session = requests.Session()
    base_clean = PANEL_BASE_URL.rstrip('/')
    login_url = f"{base_clean}/login"
    payload = {"username": PANEL_USERNAME, "password": PANEL_PASSWORD}
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)",
        "Accept": "application/json, text/plain, */*"
    }
    try:
        res = session.post(login_url, data=payload, headers=headers, verify=False, timeout=10)
        if res.status_code == 200:
            return session, "OK"
        else:
            return None, f"Login HTTP {res.status_code}"
    except Exception as e:
        return None, f"Login Error: {str(e)}"

def create_3xui_vless_key(user_name, custom_gb=25, target_chat_id=None, custom_days=None, months_count=1, is_giveaway=False, custom_expire_date=None):
    session, err_msg = get_3xui_session()
    if not session:
        return None, None, None, f"Session Failed: {err_msg}"

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
    
    clean_user = "".join(re.findall(r'[a-zA-Z0-9]', user_name)) or "HMAUser"
    id_str = f"_{target_chat_id}" if target_chat_id else ""
    gw_str = "_GW" if is_giveaway else ""
    email_name = f"{clean_user}{id_str}{gw_str}_{expire_date_str}".replace(".", "_")

    # 💡 3X-UI API တွင် totalGB ကို Bytes သို့မဟုတ် GB ပမာဏ အပြည့်အစုံ တွက်ချက်ခြင်း
    total_bytes = int(custom_gb) * 1024 * 1024 * 1024

    client_data = {
        "id": client_uuid,
        "email": email_name,
        "flow": VLESS_FLOW,
        "totalGB": total_bytes,
        "expiryTime": expiry_timestamp_ms,
        "enable": True,
        "tgId": str(target_chat_id) if target_chat_id else "",
        "subId": "".join(random.choices(string.ascii_lowercase + string.digits, k=16))
    }

    client_settings = {
        "clients": [client_data]
    }

    base_clean = PANEL_BASE_URL.rstrip('/')
    add_url = f"{base_clean}/panel/api/inbounds/addClient"
    payload = {
        "id": int(VLESS_INBOUND_ID),
        "settings": json.dumps(client_settings)
    }

    try:
        headers = {
            "Accept": "application/json", 
            "Content-Type": "application/json",
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"
        }
        res = session.post(add_url, json=payload, headers=headers, verify=False, timeout=10)
        
        if res.status_code == 200:
            res_json = res.json()
            if res_json.get("success"):
                parsed_host = "h.e.feature.hma.qzz.io"
                vless_link = f"vless://{client_uuid}@{parsed_host}:8080?type=tcp&security=reality&flow={VLESS_FLOW}#{user_name}"
                return vless_link, email_name, expire_date_str, "SUCCESS"
            else:
                return None, None, None, f"Panel Error: {res_json.get('msg', res.text)}"
        else:
            return None, None, None, f"HTTP Error {res.status_code}: {res.text}"
    except Exception as e:
        return None, None, None, f"API Exception: {str(e)}"

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

def create_outline_key(server_num, user_name, plan_info=None, custom_gb=None, target_chat_id=None, custom_days=None, months_count=1, is_giveaway=False, custom_expire_date=None):
    today = datetime.now()
    if custom_expire_date:
        expire_date = custom_expire_date
    elif custom_days:
        expire_date = (today + timedelta(days=custom_days)).strftime("%d.%m.%Y")
    else:
        expire_date = (today + relativedelta(months=months_count)).strftime("%d.%m.%Y")
    
    id_str = f" ({target_chat_id})" if target_chat_id else ""
    gw_str = " [GW]" if is_giveaway else ""
    key_name = f"{user_name}{id_str}{gw_str} {expire_date}"
    
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
        bot.send_message(chat_id, "👋 မင်္ဂလာပါ! H & E FEATURE PREMIUM VPN ဝန်ဆောင်မှု Bot မှ ကြိုဆိုပါတယ်။", reply_markup=get_main_menu_keyboard(chat_id))
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
    welcome_text = "👋 မင်္ဂလာပါ! H & E FEATURE PREMIUM VPN ဝန်ဆောင်မှု Bot မှ ကြိုဆိုပါတယ်။"
    try:
        bot.set_chat_menu_button(chat_id, telebot.types.MenuButtonWebApp(type="web_app", text="Main Website", web_app=WebAppInfo(url="https://h-e.feature.hma.qzz.io")))
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
        markup = InlineKeyboardMarkup()
        markup.row(
            InlineKeyboardButton("🟢 Outline VPN Key ယူမည်", callback_data=f"proto_outline_{plan_code}"),
            InlineKeyboardButton("🟣 VLESS (3X-UI) Key ယူမည်", callback_data=f"proto_vless_{plan_code}")
        )
        markup.row(InlineKeyboardButton("🔙 Plan များသို့ ပြန်သွားရန်", callback_data="back_to_plans"))
        bot.edit_message_text(f"📌 <b>{plan['name']} ({plan['data']})</b> - {plan['price']:,} Ks\n\n👇 မည်သည့် VPN Key အမျိုးအစား ရယူလိုပါသလဲ ရွေးချယ်ပေးပါခင်ဗျာ:", chat_id=chat_id, message_id=call.message.message_id, parse_mode="HTML", reply_markup=markup)

@bot.callback_query_handler(func=lambda call: call.data.startswith("proto_"))
def handle_protocol_selection(call):
    bot.answer_callback_query(call.id)
    chat_id = call.message.chat.id
    parts = call.data.split("_")
    proto_choice, plan_code = parts[1], parts[2]
    plan = PLANS.get(plan_code)
    if plan:
        save_user_plan(chat_id, {"code": plan_code, "name": plan["name"], "data": plan["data"], "protocol": proto_choice, "months": 1, "price_str": f"{plan['price']:,} Ks", "price_int": plan["price"]})
        proto_disp = "🟢 Outline VPN Key" if proto_choice == "outline" else "🟣 VLESS (3X-UI) Key"
        markup = InlineKeyboardMarkup()
        markup.row(InlineKeyboardButton("🔙 Plan များသို့ ပြန်သွားရန်", callback_data="back_to_plans"))
        markup.row(InlineKeyboardButton("🔙 မူလ Menu သို့ ပြန်သွားရန်", callback_data="back_to_main"))
        payment_text = f"✅ သင်ရွေးချယ်ထားသော Plan:\n📌 {plan['name']} ({plan['data']}) - 1 လစာ ({plan['price']:,} Ks)\n⚡️ Key အမျိုးအစား: <b>{proto_disp}</b>\n\n💰 KBZ Pay - 09699970092\n👤 Htet Myat Aung\n\n🙏🏻 ငွေလွှဲပြီး Screenshotလေး ပို့ပေးပါခင်ဗျာ🥰"
        bot.edit_message_text(payment_text, chat_id=chat_id, message_id=call.message.message_id, parse_mode="HTML", reply_markup=markup)

@bot.callback_query_handler(func=lambda call: call.data == "back_to_plans")
def handle_back_to_plans(call):
    bot.answer_callback_query(call.id)
    bot.edit_message_text("🧸 ကျေးဇူးပြု၍ ဝယ်ယူလိုသော VPN Plan ကို ရွေးချယ်ပေးပါခင်ဗျာ:", chat_id=call.message.chat.id, message_id=call.message.message_id, reply_markup=get_plan_keyboard())

# Admin Approve Callback Handler (Detailed Debug Info Added)
@bot.callback_query_handler(func=lambda call: call.data.startswith("approve_"))
def handle_approve_callback(call):
    bot.answer_callback_query(call.id, "⏳ Key ထုတ်ပေးနေပါသည်...")
    if is_callback_processed(f"appr_{call.message.message_id}_{call.data}") or str(call.message.chat.id) not in [str(aid) for aid in ADMIN_CHAT_IDS]:
        return
        
    try:
        parts = call.data.split("_")
        action_srv, target_chat_id, plan_code = parts[1], parts[2], parts[3]
        months_count = int(parts[4]) if len(parts) > 4 else 1
        
        plan_info = PLANS.get(plan_code, PLANS["starter"])
        u_plan = load_user_plans().get(str(target_chat_id), {})
        price_int = u_plan.get("price_int", plan_info["price"])

        chat_info = bot.get_chat(target_chat_id)
        user_name = f"{chat_info.first_name or ''} {chat_info.last_name or ''}".strip() or "HMA Customer"
        
        vpn_key, key_name, expire_date, status_msg = None, None, None, "OK"

        if action_srv == "vless":
            gb_val = int(plan_info['data'].split()[0]) * months_count
            vpn_key, key_name, expire_date, status_msg = create_3xui_vless_key(user_name, custom_gb=gb_val, target_chat_id=target_chat_id, months_count=months_count)
            srv_title = "🟣 3X-UI Server 🇸🇬 (VLESS REALITY)"
        else:
            server_num = "1" if action_srv == "srv1" else "2"
            vpn_key, key_name, expire_date = create_outline_key(server_num, user_name, plan_info=plan_info, target_chat_id=target_chat_id, months_count=months_count)
            srv_title = f"📡 Outline Server {server_num} 🇸🇬"

        if vpn_key:
            save_sale_transaction(action_srv, target_chat_id, plan_code, plan_info['name'], months_count, price_int)
            success_message = f"🎉 <b>ငွေလွှဲမှု အောင်မြင်စွာ အတည်ပြုပြီးပါပြီခင်ဗျာ။</b>\n\n👤 <b>ဝယ်ယူသူ:</b> {user_name}\n💳 <b>Plan:</b> {plan_info['name']} - {months_count} လစာ\n⏰ <b>သက်တမ်းကုန်ဆုံးရက်:</b> {expire_date}\n\n🔑 <b>လူကြီးမင်း၏ VPN Key</b>\n\n<code>{vpn_key}</code>"
            bot.send_message(target_chat_id, success_message, parse_mode="HTML")
            save_key_mapping(user_name.strip().lower(), target_chat_id)
            
            admin_msg_map = get_admin_msg_map(target_chat_id)
            updated_caption = (call.message.caption or "") + f"\n\n✅ <b>DONE ({srv_title})</b>\n\n🔑 {key_name}"
            for aid, mid in admin_msg_map.items():
                try:
                    bot.edit_message_caption(chat_id=aid, message_id=mid, caption=updated_caption, parse_mode="HTML", reply_markup=None)
                except:
                    pass
        else:
            bot.send_message(call.message.chat.id, f"❌ <b>Key မွေး၍ မရပါခင်ဗျာ!</b>\n\n⚠️ <b>Error Details:</b>\n<code>{status_msg}</code>", parse_mode="HTML")

    except Exception as e:
        bot.send_message(call.message.chat.id, f"❌ Exception: {str(e)}")

@bot.message_handler(content_types=['photo'])
def handle_photo_messages(message):
    chat_id = message.chat.id
    save_user_id(chat_id)
    if not is_user_subscribed(chat_id):
        send_force_join_message(chat_id)
        return

    clear_all_states(chat_id)
    user_name = f"{message.from_user.first_name or ''} {message.from_user.last_name or ''}".strip() or "HMA User"
    user_plans = load_user_plans()
    
    if str(chat_id) not in user_plans:
        bot.reply_to(message, "⚠️ ကျေးဇူးပြု၍ '💳 Plan များ ကြည့်ရန်' ခလုတ်ကို အရင်နှိပ်ပေးပါဦးခင်ဗျာ။")
        return

    plan_info = user_plans.get(str(chat_id))
    plan_code = plan_info.get('code', 'starter')
    proto_choice = plan_info.get('protocol', 'outline')
    months_count = plan_info.get('months', 1)
    
    proto_disp = "🟢 Outline VPN" if proto_choice == "outline" else "🟣 VLESS (3X-UI)"

    admin_alert_text = (
        f"💰 <b>ငွေလွှဲပြေစာအသစ်</b>\n"
        f"👤 ဝယ်ယူသူ: {user_name}\n"
        f"📦 Plan: {plan_info['name']} [{months_count} လစာ]\n"
        f"⚡️ Key အမျိုးအစား: <b>{proto_disp}</b>\n"
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
    for admin_id in ADMIN_CHAT_IDS:
        try:
            sent_msg = bot.send_photo(admin_id, message.photo[-1].file_id, caption=admin_alert_text, parse_mode="HTML", reply_markup=approve_markup)
            if sent_msg:
                admin_msg_dict[str(admin_id)] = sent_msg.message_id
        except:
            pass
    save_admin_msg_map(chat_id, admin_msg_dict)
    bot.reply_to(message, "💌 ငွေလွှဲပြေစာအား စစ်ဆေးနေပါသည်။ Admin အတည်ပြုပြီးပါက VPN Key ကို ချက်ချင်းပို့ပေးပါမည်။ 🙏")

@bot.message_handler(func=lambda message: True)
def handle_all_messages(message):
    input_value = message.text.strip()
    chat_id = message.chat.id
    save_user_id(chat_id)

    if not is_user_subscribed(chat_id):
        send_force_join_message(chat_id)
        return

    if input_value in ["💳 Plan များ ကြည့်ရန်", "Plan များ ကြည့်ရန်"]:
        clear_all_states(chat_id)
        bot.send_message(chat_id, "🧸 လူကြီးမင်း ဝယ်ယူလိုသော VPN Plan ကို ရွေးချယ်ပေးပါခင်ဗျာ:", reply_markup=get_plan_keyboard())
        return

    if input_value in ["🔄 Bot Refresh", "/refresh"]:
        clear_all_states(chat_id)
        bot.send_message(chat_id, "🔄 <b>Bot စနစ်အား Refresh ပြုလုပ်ပြီးပါပြီခင်ဗျာ!</b>", parse_mode="HTML", reply_markup=get_main_menu_keyboard(chat_id))
        return

    bot.reply_to(message, "💡 Menu ခလုတ်များကို အသုံးပြုပေးပါခင်ဗျာ။", reply_markup=get_main_menu_keyboard(chat_id))

@app.route('/', defaults={'path': ''}, methods=['POST', 'GET'])
@app.route('/<path:path>', methods=['POST', 'GET'])
def index(path):
    if request.method == 'POST':
        json_string = request.get_data().decode('utf-8')
        update = telebot.types.Update.de_json(json_string)
        bot.process_new_updates([update])
        return jsonify({"status": "ok"}), 200
    return "Bot is running perfectly!", 200
