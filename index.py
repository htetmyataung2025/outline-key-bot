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

# 🌐 Outline API Servers
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

# Temp Files & Configs
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
PROCESSED_CALLBACKS = set()

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
# 🛠️ GENERAL SYSTEM UTILITIES & DATABASE
# ---------------------------------------------------------
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
    return redis_get("all_users") or []

def set_broadcast_state(chat_id, is_waiting=True):
    states = redis_get("admin_broadcast_state") or {}
    states[str(chat_id)] = is_waiting
    redis_set("admin_broadcast_state", states)

def get_broadcast_state(chat_id):
    states = redis_get("admin_broadcast_state") or {}
    return states.get(str(chat_id), False)

def load_user_plans():
    return redis_get("user_plans") or {}

def save_user_plan(chat_id, plan_data):
    plans = load_user_plans()
    plans[str(chat_id)] = plan_data
    redis_set("user_plans", plans)

def load_key_mappings():
    return redis_get("key_mappings") or {}

def save_key_mapping(clean_name, chat_id):
    mappings = load_key_mappings()
    mappings[clean_name.strip().lower()] = str(chat_id)
    redis_set("key_mappings", mappings)

def load_sales_history():
    return redis_get("sales_history") or []

def save_sale_transaction(server_num, chat_id, plan_code, plan_name, months_count, price_int, protocol="outline", is_test=False):
    # 💡 Test Key သို့မဟုတ် စျေးနှုန်း 0 ဖြစ်ပါက စာရင်းထဲ မပေါင်းထည့်ပါ
    if is_test or int(price_int) == 0:
        return

    sales = load_sales_history()
    now = datetime.utcnow() + timedelta(hours=6, minutes=30)
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

def load_redeem_codes():
    return redis_get("redeem_codes") or {}

def save_redeem_codes(codes):
    redis_set("redeem_codes", codes)

def set_search_state(chat_id, is_searching=True):
    states = redis_get("admin_search_state") or {}
    states[str(chat_id)] = is_searching
    redis_set("admin_search_state", states)

def get_search_state(chat_id):
    return (redis_get("admin_search_state") or {}).get(str(chat_id), False)

def set_redeem_state(chat_id, is_waiting=True):
    states = redis_get("user_redeem_state") or {}
    states[str(chat_id)] = is_waiting
    redis_set("user_redeem_state", states)

def get_redeem_state(chat_id):
    return (redis_get("user_redeem_state") or {}).get(str(chat_id), False)

def set_replacement_state(chat_id, is_waiting=True):
    states = redis_get("user_replacement_state") or {}
    states[str(chat_id)] = is_waiting
    redis_set("user_replacement_state", states)

def get_replacement_state(chat_id):
    return (redis_get("user_replacement_state") or {}).get(str(chat_id), False)

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

def send_force_join_message(chat_id):
    msg_text = (
        f"⚠️ <b>သတိပေးချက်:</b>\n\n"
        f"Bot အား စတင်အသုံးပြုရန်အတွက် အောက်ပါ ကျွန်ုပ်တို့၏ Telegram Channel ကို အရင်ဆုံး Join ပေးရန် လိုအပ်ပါသည်ခင်ဗျာ။\n\n"
        f"👉 <b>Channel:</b> {REQUIRED_CHANNEL}\n\n"
        f"Channel Join ပြီးပါက <b>'✅ Join ပြီးပါပြီ (Verify)'</b> ခလုတ်ကို နှိပ်၍ အသုံးပြုနိုင်ပါပြီ။"
    )
    markup = InlineKeyboardMarkup()
    markup.add(InlineKeyboardButton("📢 Channel သို့ Join ရန်", url=f"https://t.me/{REQUIRED_CHANNEL.replace('@', '')}"))
    markup.add(InlineKeyboardButton("✅ Join ပြီးပါပြီ (Verify)", callback_data="verify_subscription"))
    bot.send_message(chat_id, msg_text, parse_mode="HTML", reply_markup=markup)

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
    return url_str.replace("ss://", "").split("#")[0].split("?")[0].strip()

def get_main_menu_keyboard(chat_id=None):
    markup = ReplyKeyboardMarkup(resize_keyboard=True, row_width=2)
    markup.add(KeyboardButton("💳 Plan များ ကြည့်ရန်"), KeyboardButton("⚡️ Data Usage စစ်ရန်"))
    markup.add(KeyboardButton("🔄 Key လဲရန်"), KeyboardButton("🔄 Bot Refresh"))
    markup.add(KeyboardButton("🎁 Public Free Key"), KeyboardButton("🎁 Redeem Code"))
    markup.add(KeyboardButton("👨‍💻 Admin သို့ ဆက်သွယ်ရန်"))
    
    if chat_id and str(chat_id) in [str(aid) for aid in ADMIN_CHAT_IDS]:
        markup.add(KeyboardButton("📊 Total Data Usage"), KeyboardButton("🎁 Gen RD Code"))
        markup.add(KeyboardButton("💰 လစဉ် ဝင်ငွေ"), KeyboardButton("🔍 Cus ရှာရန်"))
        markup.add(KeyboardButton("📢 Broadcast စာပို့ရန်"))
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

# ---------------------------------------------------------
# 🤖 BOT HANDLERS & CALLBACKS
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
    bot.send_message(chat_id, "👋 မင်္ဂလာပါ! H & E FEATURE PREMIUM VPN ဝန်ဆောင်မှု Bot မှ ကြိုဆိုပါတယ်။", reply_markup=get_main_menu_keyboard(chat_id))

@bot.message_handler(commands=['start'])
def send_welcome(message):
    chat_id = message.chat.id
    save_user_id(chat_id)
    clear_all_states(chat_id)
    if not is_user_subscribed(chat_id):
        send_force_join_message(chat_id)
        return
    bot.reply_to(message, "👋 မင်္ဂလာပါ! H & E FEATURE PREMIUM VPN ဝန်ဆောင်မှု Bot မှ ကြိုဆိုပါတယ်။", reply_markup=get_main_menu_keyboard(chat_id))

# Plan Selection & Protocol Choice
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
            f"📱 KBZ Pay - 09699970092 (Htet Myat Aung)\n"
            f"📱 Wave Pay - 09699970092 (Htet Myat Aung)\n"
            f"━━━━━━━━━━━━━━━\n\n"
            f"🙏🏻 ငွေလွှဲပြီး Screenshot ပို့ပေးပါခင်ဗျာ🥰"
        )
        markup = InlineKeyboardMarkup()
        markup.row(InlineKeyboardButton("🔙 မူလ Menu သို့ ပြန်သွားရန်", callback_data="back_to_main"))
        bot.edit_message_text(payment_text, chat_id=chat_id, message_id=call.message.message_id, reply_markup=markup)

# Admin Approval Handler
@bot.callback_query_handler(func=lambda call: call.data.startswith("approve_"))
def handle_approve_callback(call):
    bot.answer_callback_query(call.id, "⏳ Key ထုတ်ပေးနေပါသည်...")
    if is_callback_processed(f"appr_{call.message.message_id}_{call.data}"):
        return
    if str(call.message.chat.id) not in [str(aid) for aid in ADMIN_CHAT_IDS]:
        return

    try:
        parts = call.data.split("_")
        target_srv = parts[1]  # srv1, srv2, xui
        target_chat_id = parts[2]
        plan_code = parts[3]
        months_count = int(parts[4]) if len(parts) > 4 else 1
        
        is_test_key = "test" in parts or plan_code == "test"

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
            srv_num = "1" if target_srv == "srv1" else "2"
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
                f"☝️ တစ်ချက်တည်း နှိပ်၍ Copy ယူ အသုံးပြုနိုင်ပါပြီခင်ဗျာ။"
            )
            bot.send_message(target_chat_id, success_msg, parse_mode="HTML")
            
            try:
                bot.edit_message_caption(chat_id=call.message.chat.id, message_id=call.message.message_id, caption=call.message.caption + f"\n\n✅ <b>DONE ({srv_title}) {'[TEST]' if is_test_key else ''}</b>", parse_mode="HTML")
            except:
                pass
    except Exception as e:
        print("Approve Callback Error:", e)

# Photo Payment Receipt Handler
@bot.message_handler(content_types=['photo'])
def handle_photo_receipt(message):
    chat_id = message.chat.id
    save_user_id(chat_id)
    if not is_user_subscribed(chat_id):
        send_force_join_message(chat_id)
        return

    user_plans = load_user_plans()
    if str(chat_id) not in user_plans:
        bot.reply_to(message, "⚠️ ခွင့်လွှတ်ပါ၊ '💳 Plan များ ကြည့်ရန်' ခလုတ်ကို အရင်နှိပ်ပြီး Plan ရွေးချယ်ပေးပါခင်ဗျာ။")
        return

    plan_info = user_plans.get(str(chat_id))
    plan_code = plan_info.get('code', 'starter')
    proto = plan_info.get('protocol', 'outline')
    
    admin_alert = (
        f"💰 <b>ငွေလွှဲပြေစာအသစ် [{proto.upper()}]</b>\n"
        f"👤 ဝယ်ယူသူ: {message.from_user.first_name} (@{message.from_user.username or 'N/A'})\n"
        f"📦 Plan: {plan_info['name']} ({plan_info.get('data', '')})\n"
        f"🆔 Chat ID: {chat_id}"
    )

    markup = InlineKeyboardMarkup()
    if proto == "vless":
        markup.row(InlineKeyboardButton("⚡️ Approve 3X-UI VLESS", callback_data=f"approve_xui_{chat_id}_{plan_code}_1"))
    else:
        markup.row(
            InlineKeyboardButton("📡 S1 Outline", callback_data=f"approve_srv1_{chat_id}_{plan_code}_1"),
            InlineKeyboardButton("📡 S2 Outline", callback_data=f"approve_srv2_{chat_id}_{plan_code}_1")
        )

    for aid in ADMIN_CHAT_IDS:
        try:
            bot.send_photo(aid, message.photo[-1].file_id, caption=admin_alert, parse_mode="HTML", reply_markup=markup)
        except:
            pass

    bot.reply_to(message, "💌 ငွေလွှဲပြေစာအား စစ်ဆေးနေပါသည်။ Admin အတည်ပြုပြီးပါက VPN Key ကို ပို့ပေးပါမည်။ 🙏")

# All Text Message Handler & Usage Checker
@bot.message_handler(func=lambda message: True)
def handle_all_text_messages(message):
    input_val = message.text.strip()
    chat_id = message.chat.id
    save_user_id(chat_id)

    if not is_user_subscribed(chat_id):
        send_force_join_message(chat_id)
        return

    if input_val in ["💳 Plan များ ကြည့်ရန်"]:
        bot.send_message(chat_id, "🧸 ဝယ်ယူလိုသော VPN Plan ကို ရွေးချယ်ပေးပါခင်ဗျာ:", reply_markup=get_plan_keyboard())
        return

    if input_val in ["⚡️ Data Usage စစ်ရန်"]:
        bot.send_message(chat_id, "👇 ဝယ်ယူထားသော VPN Key (ss:// သို့ vless://) ကို Paste ချ ပို့ပေးပါခင်ဗျာ:", reply_markup=get_back_inline_keyboard())
        return

    # Check VLESS Data Usage
    if input_val.startswith("vless://") or "xtls-rprx-vision" in input_val:
        xui_info = get_3xui_client_info(input_val)
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

    bot.reply_to(message, "💡 Refresh ပြုလုပ်လိုပါက /start ကို နှိပ်ပေးပါခင်ဗျာ။", reply_markup=get_main_menu_keyboard(chat_id))

# Webhook Server Index
@app.route('/', defaults={'path': ''}, methods=['POST', 'GET'])
@app.route('/<path:path>', methods=['POST', 'GET'])
def index(path):
    if request.method == 'POST':
        json_string = request.get_data().decode('utf-8')
        update = telebot.types.Update.de_json(json_string)
        bot.process_new_updates([update])
        return jsonify({"status": "ok"}), 200
    return "3X-UI & Outline Hybrid Bot is Running Smoothly!", 200
