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
from datetime import datetime, timedelta
from dateutil.relativedelta import relativedelta

app = Flask(__name__)

# Token & API Configuration
TELEGRAM_TOKEN = "8779558815:AAEaXF6rRqCVM-PFhbOlwgubSknk5xTiKvU"

# 📢 Force Join Channel Configuration
REQUIRED_CHANNEL = "@hefeature"

# 🌐 API Server ၁၊ ၂ နှင့် ၃ လင့်ခ်များ
OUTLINE_API_URL_1 = "https://64.120.94.164:49429/YkDBSn3KwUaICBvzDQtvxQ"
OUTLINE_API_URL_2 = "https://104.207.92.135:8443/o8a5SK1XlVXdrgXUX5Z24Q"
OUTLINE_API_URL_3 = "https://vip.h-e-feature.store:33300/E_LfjCh3-9u_jEFyQnZUfA"

# 🔑 Admin Telegram Chat IDs (Admin ၂ ယောက်လုံး ပါဝင်သည်)
ADMIN_CHAT_IDS = ["8778394176", "6297145771"]

# 🔍 OCR Space API Key Configuration
OCR_API_KEY = "K87641025188957"
MY_PAYMENT_PHONES = ["09699970092", "9699970092", "699970092"]

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
REPLACEMENT_MSG_MAP_FILE = "/tmp/replacement_msg_map.json"
BROADCAST_STATE_FILE = "/tmp/admin_broadcast_state.json"
ALL_USERS_FILE = "/tmp/all_users.json"
ORDERS_FILE = "/tmp/orders_data.json"
KEY_ORDERS_FILE = "/tmp/key_orders.json"
USER_HISTORY_FILE = "/tmp/user_purchases.json"
PROCESSED_CALLBACKS = set()

def is_callback_processed(call_id):
    if call_id in PROCESSED_CALLBACKS:
        return True
    PROCESSED_CALLBACKS.add(call_id)
    if len(PROCESSED_CALLBACKS) > 1000:
        PROCESSED_CALLBACKS.clear()
    return False

# 📇 Customer Purchase History Storage Helpers
def load_all_user_history():
    data = redis_get("user_purchases_data")
    if data is not None:
        return data
    if os.path.exists(USER_HISTORY_FILE):
        try:
            with open(USER_HISTORY_FILE, 'r') as f:
                return json.load(f)
        except:
            pass
    return {}

def save_user_purchase_record(chat_id, order_id, plan_name, disp_gb, months_count, price_str, server_num, expire_date, vpn_key):
    history_data = load_all_user_history()
    uid = str(chat_id)
    if uid not in history_data:
        history_data[uid] = []
        
    now = datetime.utcnow() + timedelta(hours=6, minutes=30)
    record = {
        "timestamp": now.strftime("%d/%m/%Y (%I:%M %p)"),
        "order_id": order_id if order_id else "N/A",
        "plan_name": plan_name,
        "disp_gb": disp_gb,
        "months": months_count,
        "price_str": price_str,
        "server": str(server_num),
        "expire_date": expire_date,
        "vpn_key": vpn_key
    }
    history_data[uid].append(record)
    redis_set("user_purchases_data", history_data)
    try:
        with open(USER_HISTORY_FILE, 'w') as f:
            json.dump(history_data, f)
    except:
        pass

def get_user_combined_purchase_records(chat_id):
    history_data = load_all_user_history()
    records = list(history_data.get(str(chat_id), []))
    
    known_orders = set(r.get("order_id") for r in records if r.get("order_id") and r.get("order_id") != "N/A")

    sales = load_sales_history()
    user_sales = [s for s in sales if str(s.get("chat_id")) == str(chat_id)]

    server_keys_cache = {}
    for srv_idx, api_url in [("1", OUTLINE_API_URL_1), ("2", OUTLINE_API_URL_2), ("3", OUTLINE_API_URL_3)]:
        try:
            res = requests.get(f"{api_url}/access-keys", verify=False, timeout=5)
            if res.status_code == 200:
                server_keys_cache[srv_idx] = res.json().get("accessKeys", [])
        except:
            server_keys_cache[srv_idx] = []

    for s in user_sales:
        s_ord = s.get("order_id", "N/A")
        if s_ord != "N/A" and s_ord in known_orders:
            continue
            
        srv_num = str(s.get("server", "1"))
        matched_key_link = "N/A"
        exp_date_found = "မသိရှိပါ"
        
        for k in server_keys_cache.get(srv_num, []):
            k_name = k.get("name", "")
            if f"({chat_id})" in k_name:
                raw_url = k.get("accessUrl", "")
                matched_key_link = f"{raw_url}#{k_name}"
                date_match = re.search(r'\d{1,2}\.\d{1,2}\.(\d{4}|\d{2})', k_name)
                if date_match:
                    exp_date_found = date_match.group(0)
                break

        p_info = PLANS.get(s.get("plan_code"), {})
        disp_gb = f"{int(p_info.get('data', '25 GB').split()[0]) * s.get('months', 1)} GB" if p_info else "N/A"

        legacy_rec = {
            "timestamp": s.get("timestamp", s.get("date", "N/A")),
            "order_id": s_ord,
            "plan_name": s.get("plan_name", "VPN Plan"),
            "disp_gb": disp_gb,
            "months": s.get("months", 1),
            "price_str": f"{s.get('price', 0):,} Ks",
            "server": srv_num,
            "expire_date": exp_date_found,
            "vpn_key": matched_key_link
        }
        records.append(legacy_rec)
        if s_ord != "N/A":
            known_orders.add(s_ord)
            
    return records

# 🔍 OCR Space Helper Functions
def parse_slip_ocr(file_path):
    try:
        file_url = f"https://api.telegram.org/file/bot{TELEGRAM_TOKEN}/{file_path}"
        img_resp = requests.get(file_url, timeout=12)
        if img_resp.status_code == 200:
            files = {'file': ('slip.jpg', img_resp.content, 'image/jpeg')}
            payload = {
                'apikey': OCR_API_KEY,
                'language': 'eng',
                'isOverlayRequired': False,
                'OCREngine': '2'
            }
            res = requests.post('https://api.ocr.space/parse/image', files=files, data=payload, timeout=20)
            if res.status_code == 200:
                result = res.json()
                if result.get("IsErroredOnProcessing") == False:
                    parsed_results = result.get("ParsedResults", [])
                    if parsed_results:
                        return parsed_results[0].get("ParsedText", "")
    except Exception as e:
        print("OCR API Error:", e)
    return ""

def clean_ocr_text_thoroughly(text):
    if not text:
        return ""
    mm_map = {
        '၀': '0', '၁': '1', '၂': '2', '၃': '3', '၄': '4',
        '၅': '5', '၆': '6', '၇': '7', '၈': '8', '၉': '9'
    }
    for mm_char, en_char in mm_map.items():
        text = text.replace(mm_char, en_char)
    return text

def extract_transaction_last6(ocr_text):
    if not ocr_text:
        return None
        
    normalized_text = clean_ocr_text_thoroughly(ocr_text)
    
    for ph in MY_PAYMENT_PHONES:
        normalized_text = normalized_text.replace(ph, "")

    lines = normalized_text.splitlines()

    for i, line in enumerate(lines):
        clean_l = line.replace(" ", "").replace("-", "")
        if any(k in clean_l.lower() for k in ["transaction", "trx", "လုပ်ဆောင်ချက်", "လုပ်ဆောင်မှု", "အိုင်ဒီ", "အမှတ်"]):
            digits = re.findall(r'\d{6,24}', clean_l)
            if digits:
                return digits[0][-6:]
            if i + 1 < len(lines):
                next_l = lines[i+1].replace(" ", "").replace("-", "")
                next_digits = re.findall(r'\d{6,24}', next_l)
                if next_digits:
                    return next_digits[0][-6:]

    kpay_match = re.search(r'\b(010\d{13,20})\b', normalized_text.replace(" ", ""))
    if kpay_match:
        return kpay_match.group(1)[-6:]

    all_numbers = re.findall(r'\b\d{8,15}\b', normalized_text.replace("-", " "))
    for num in all_numbers:
        if not num.startswith("09") and not num.startswith("9699"):
            return num[-6:]

    return None

def generate_order_id_from_slip(file_path=None):
    if file_path:
        ocr_text = parse_slip_ocr(file_path)
        last6 = extract_transaction_last6(ocr_text)
        if last6 and len(last6) == 6:
            return f"#{last6}"
            
    chars = string.ascii_uppercase + string.digits
    rand_part = ''.join(random.choices(chars, k=6))
    return f"#{rand_part}"

def load_orders():
    data = redis_get("orders_data")
    if data is not None:
        return data
    if os.path.exists(ORDERS_FILE):
        try:
            with open(ORDERS_FILE, 'r') as f:
                return json.load(f)
        except:
            pass
    return {}

def save_order(order_id, order_data):
    orders = load_orders()
    orders[str(order_id)] = order_data
    redis_set("orders_data", orders)
    try:
        with open(ORDERS_FILE, 'w') as f:
            json.dump(orders, f)
    except:
        pass

def load_key_orders():
    data = redis_get("key_orders")
    if data is not None:
        return data
    if os.path.exists(KEY_ORDERS_FILE):
        try:
            with open(KEY_ORDERS_FILE, 'r') as f:
                return json.load(f)
        except:
            pass
    return {}

def map_key_to_order(key_name, order_id):
    if not order_id or not key_name:
        return
    data = load_key_orders()
    clean_k = key_name.strip().lower()
    data[clean_k] = str(order_id)
    redis_set("key_orders", data)
    try:
        with open(KEY_ORDERS_FILE, 'w') as f:
            json.dump(data, f)
    except:
        pass

def get_order_id_for_key(key_name):
    data = load_key_orders()
    clean_k = key_name.strip().lower()
    return data.get(clean_k, "N/A")

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

def save_sale_transaction(server_num, chat_id, plan_code, plan_name, months_count, price_int, order_id=None):
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
        "price": int(price_int) if price_int else 0,
        "order_id": order_id or "N/A"
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

def save_replacement_msg_map(request_key, admin_msg_dict):
    try:
        data = redis_get("replacement_msg_map") or {}
        data[str(request_key)] = admin_msg_dict
        redis_set("replacement_msg_map", data)
    except:
        pass

def get_replacement_msg_map(request_key):
    try:
        data = redis_get("replacement_msg_map") or {}
        if not data and os.path.exists(REPLACEMENT_MSG_MAP_FILE):
            with open(REPLACEMENT_MSG_MAP_FILE, 'r') as f:
                data = json.load(f)
        return data.get(str(request_key), {})
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
    for api_url in [OUTLINE_API_URL_1, OUTLINE_API_URL_2, OUTLINE_API_URL_3]:
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
        print("Force Join Check Error:", e)
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
        f"Bot အား စတင်အသုံးပြုရန်အတွက် အောက်ပါ ကျွန်တော်ရဲ့Telegram Channel ကို အရင်ဆုံး Join ပေးရန် လိုအပ်ပါသည်ခင်ဗျာ။\n\n"
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
    btn_buy = KeyboardButton("🛍️ Plan များ ကြည့်ရန်")
    btn_history = KeyboardButton("📇 ဝယ်ယူမှုမှတ်တမ်း")
    btn_check = KeyboardButton("🧰 Data Usage စစ်ရန်")
    btn_replace = KeyboardButton("♻️ Key လဲရန်")
    btn_free = KeyboardButton("🎁 Public Free Key")
    btn_redeem = KeyboardButton("🎟️ Redeem Code")
    btn_admin = KeyboardButton("👨‍💻 Admin သို့ ဆက်သွယ်ရန်")
    btn_refresh = KeyboardButton("🤖 Bot Refresh")
    
    markup.add(btn_buy, btn_history)
    markup.add(btn_check, btn_replace)
    markup.add(btn_free, btn_redeem)
    markup.add(btn_admin, btn_refresh)
    
    if chat_id and str(chat_id) in [str(aid) for aid in ADMIN_CHAT_IDS]:
        btn_total_usage = KeyboardButton("📊 Total Data Usage")
        btn_monthly_income = KeyboardButton("💰 လစဉ် ဝင်ငွေ")
        btn_gen_code = KeyboardButton("🎟️ Gen RD Code")
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

def get_admin_server_keyboard():
    markup = InlineKeyboardMarkup()
    markup.row(
        InlineKeyboardButton("📡 Server 1 🇸🇬", callback_data="adm_srv_1"),
        InlineKeyboardButton("📡 Server 2 🇸🇬", callback_data="adm_srv_2")
    )
    markup.row(
        InlineKeyboardButton("📡 Server 3 🇸🇬", callback_data="adm_srv_3")
    )
    markup.row(InlineKeyboardButton("🔙 မူလ Menu သို့ ပြန်သွားရန်", callback_data="back_to_main"))
    return markup

def get_admin_gb_keyboard(srv):
    markup = InlineKeyboardMarkup()
    markup.row(
        InlineKeyboardButton("⚡️ 25 GB", callback_data=f"adm_gb_{srv}_25"),
        InlineKeyboardButton("⚡️ 50 GB", callback_data=f"adm_gb_{srv}_50")
    )
    markup.row(
        InlineKeyboardButton("⚡️ 75 GB", callback_data=f"adm_gb_{srv}_75"),
        InlineKeyboardButton("⚡️ 100 GB", callback_data=f"adm_gb_{srv}_100")
    )
    markup.row(
        InlineKeyboardButton("⚡️ 150 GB", callback_data=f"adm_gb_{srv}_150"),
        InlineKeyboardButton("⚡️ 200 GB", callback_data=f"adm_gb_{srv}_200")
    )
    markup.row(InlineKeyboardButton("🔙 Server ပြန်ရွေးရန်", callback_data="back_to_gen_rd"))
    return markup

def get_admin_days_keyboard(srv, gb):
    markup = InlineKeyboardMarkup()
    markup.row(
        InlineKeyboardButton("📅 1 ရက်", callback_data=f"adm_dur_{srv}_{gb}_1"),
        InlineKeyboardButton("📅 3 ရက်", callback_data=f"adm_dur_{srv}_{gb}_3")
    )
    markup.row(
        InlineKeyboardButton("📅 5 ရက်", callback_data=f"adm_dur_{srv}_{gb}_5"),
        InlineKeyboardButton("📅 7 ရက်", callback_data=f"adm_dur_{srv}_{gb}_7")
    )
    markup.row(InlineKeyboardButton("🔙 GB ပြန်ရွေးရန်", callback_data=f"adm_srv_{srv}"))
    return markup

def get_admin_count_keyboard(srv, gb, days):
    markup = InlineKeyboardMarkup()
    markup.row(
        InlineKeyboardButton("1 ခု", callback_data=f"adm_cnt_{srv}_{gb}_{days}_1"),
        InlineKeyboardButton("3 ခု", callback_data=f"adm_cnt_{srv}_{gb}_{days}_3")
    )
    markup.row(
        InlineKeyboardButton("5 ခု", callback_data=f"adm_cnt_{srv}_{gb}_{days}_5"),
        InlineKeyboardButton("10 ခု", callback_data=f"adm_cnt_{srv}_{gb}_{days}_10")
    )
    markup.row(InlineKeyboardButton("🔙 ရက်ပေါင်း ပြန်ရွေးရန်", callback_data=f"adm_gb_{srv}_{gb}"))
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
    s3_keys, s3_rev, s3_today_keys, s3_today_rev = 0, 0, 0, 0

    s1_plans = {}
    s2_plans = {}
    s3_plans = {}
    today_plans = {}

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

            if srv == "1":
                s1_keys += 1
                s1_rev += price
                s1_plans[p_key_str] = s1_plans.get(p_key_str, 0) + 1
                if is_today:
                    s1_today_keys += 1
                    s1_today_rev += price
            elif srv == "2":
                s2_keys += 1
                s2_rev += price
                s2_plans[p_key_str] = s2_plans.get(p_key_str, 0) + 1
                if is_today:
                    s2_today_keys += 1
                    s2_today_rev += price
            elif srv == "3":
                s3_keys += 1
                s3_rev += price
                s3_plans[p_key_str] = s3_plans.get(p_key_str, 0) + 1
                if is_today:
                    s3_today_keys += 1
                    s3_today_rev += price

    total_keys = s1_keys + s2_keys + s3_keys
    total_rev = s1_rev + s2_rev + s3_rev
    today_keys = s1_today_keys + s2_today_keys + s3_today_keys
    today_rev = s1_today_rev + s2_today_rev + s3_today_rev

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
        f"📡 <b>Server 1 🇸🇬 (This Month Sales):</b>\n"
        f"🔑 Total Paid Keys: <b>{s1_keys} ခု</b>\n"
        f"{format_sales_breakdown(s1_plans)}\n"
        f"💵 Server 1 လစဉ်ဝင်ငွေ: <b>{s1_rev:,} Ks</b>\n\n"
        f"📡 <b>Server 2 🇸🇬 (This Month Sales):</b>\n"
        f"🔑 Total Paid Keys: <b>{s2_keys} ခု</b>\n"
        f"{format_sales_breakdown(s2_plans)}\n"
        f"💵 Server 2 လစဉ်ဝင်ငွေ: <b>{s2_rev:,} Ks</b>\n\n"
        f"📡 <b>Server 3 🇸🇬 (This Month Sales):</b>\n"
        f"🔑 Total Paid Keys: <b>{s3_keys} ခု</b>\n"
        f"{format_sales_breakdown(s3_plans)}\n"
        f"💵 Server 3 လစဉ်ဝင်ငွေ: <b>{s3_rev:,} Ks</b>\n\n"
        f"━━━━━━━━━━━━━━━━━\n"
        f"🌐 <b>Total This Month Paid Keys:</b> <b>{total_keys} ခု</b>\n"
        f"💎 <b>ဒီလ စုစုပေါင်း ဝင်ငွေ:</b> <b>{total_rev:,} MMK</b>\n\n"
    )
    return report

def get_servers_total_usage():
    def get_server_stats(api_url):
        total_keys = 0
        total_bytes = 0

        try:
            keys_resp = requests.get(f"{api_url}/access-keys", verify=False, timeout=8)
            metrics_resp = requests.get(f"{api_url}/metrics/transfer", verify=False, timeout=8)

            if keys_resp.status_code == 200:
                keys_data = keys_resp.json().get("accessKeys", [])
                total_keys = len(keys_data)

            if metrics_resp.status_code == 200:
                bytes_dict = metrics_resp.json().get("bytesTransferredByUserId", {})
                total_bytes = sum(bytes_dict.values())
        except:
            pass

        return total_keys, total_bytes

    s1_total, s1_bytes = get_server_stats(OUTLINE_API_URL_1)
    s2_total, s2_bytes = get_server_stats(OUTLINE_API_URL_2)
    s3_total, s3_bytes = get_server_stats(OUTLINE_API_URL_3)

    s1_gb = bytes_to_gb(s1_bytes)
    s2_gb = bytes_to_gb(s2_bytes)
    s3_gb = bytes_to_gb(s3_bytes)
    
    overall_bytes = s1_bytes + s2_bytes + s3_bytes
    overall_gb = bytes_to_gb(overall_bytes)
    overall_tb = round(overall_gb / 1000, 2)

    report = (
        f"📊 <b>SERVER DATA STATS REPORT</b>\n\n"
        f"📡 <b>Server 1 🇸🇬</b>\n"
        f"🔑 Total Keys: <b>{s1_total}</b>\n"
        f"🧰 Total Usage: <b>{s1_gb} GB</b>\n\n"
        f"📡 <b>Server 2 🇸🇬</b>\n"
        f"🔑 Total Keys: <b>{s2_total}</b>\n"
        f"🧰 Total Usage: <b>{s2_gb} GB</b>\n\n"
        f"📡 <b>Server 3 🇸🇬</b>\n"
        f"🔑 Total Keys: <b>{s3_total}</b>\n"
        f"🧰 Total Usage: <b>{s3_gb} GB</b>\n\n"
        f"━━━━━━━━━━━━━━━━━\n"
        f"🌟 <b>Overall Total Usage:</b> <b>{overall_gb} GB (~{overall_tb} TB)</b>"
    )
    return report

def search_users_by_query(query):
    query_clean = query.strip().lower()
    markup = InlineKeyboardMarkup()
    found_matches = []
    key_orders_map = load_key_orders()

    for server_num, api_url in [("1", OUTLINE_API_URL_1), ("2", OUTLINE_API_URL_2), ("3", OUTLINE_API_URL_3)]:
        try:
            res = requests.get(f"{api_url}/access-keys", verify=False, timeout=8)
            if res.status_code == 200:
                keys = res.json().get("accessKeys", [])
                for k in keys:
                    k_name = k.get("name", "").strip()
                    k_name_lower = k_name.lower()
                    assigned_ord = key_orders_map.get(k_name_lower, "").lower()

                    if len(query_clean) == 1:
                        if k_name_lower.startswith(query_clean):
                            found_matches.append((server_num, str(k.get("id")), k_name))
                    else:
                        if query_clean in k_name_lower or (assigned_ord and query_clean in assigned_ord):
                            found_matches.append((server_num, str(k.get("id")), k_name))
        except:
            pass

    for server_num, key_id, k_name in found_matches[:30]:
        srv_icon = f"📡 S{server_num}🇸🇬"
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
        "🎟️ <b>Giveaway Redeem Code ထုတ်ရန်:</b>\n\nကျေးဇူးပြု၍ မည်သည့် <b>Server</b> အတွက် Code ထုတ်ယူမည်ကို အရင်ဆုံး ရွေးချယ်ပေးပါခင်ဗျာ:",
        chat_id=call.message.chat.id,
        message_id=call.message.message_id,
        parse_mode="HTML",
        reply_markup=get_admin_server_keyboard()
    )

# 🛠️ Read Timeout မဖြစ်အောင် Timeout 15s တိုးမြှင့်ထားပြီး Metrics Error ဖြစ်လျှင်တောင် Key အချက်အလက်များကို ဆက်ပြပေးမည့် Fixed Handler
@bot.callback_query_handler(func=lambda call: call.data.startswith("viewkey_"))
def handle_view_key_detail(call):
    bot.answer_callback_query(call.id)
    if str(call.message.chat.id) not in [str(aid) for aid in ADMIN_CHAT_IDS]:
        return
    
    parts = call.data.split("_")
    server_num = parts[1]
    key_id = parts[2]
    
    api_url = OUTLINE_API_URL_1 if server_num == "1" else (OUTLINE_API_URL_2 if server_num == "2" else OUTLINE_API_URL_3)
    api_url = api_url.rstrip('/')
    
    try:
        # Timeout ကို 15 စက္ကန့်အထိ တိုးမြှင့်ထားသည်
        keys_resp = requests.get(f"{api_url}/access-keys", verify=False, timeout=15)
        
        bytes_transferred = {}
        try:
            metrics_resp = requests.get(f"{api_url}/metrics/transfer", verify=False, timeout=15)
            if metrics_resp.status_code == 200:
                bytes_transferred = metrics_resp.json().get("bytesTransferredByUserId", {})
        except:
            bytes_transferred = {}
        
        if keys_resp.status_code == 200:
            keys_data = keys_resp.json().get("accessKeys", [])
            
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
                
                order_id_disp = get_order_id_for_key(full_name)
                order_line = f"🧾 <b>Order ID:</b> <code>{order_id_disp}</code>\n" if order_id_disp != "N/A" else ""
                
                server_name = f"Server {server_num} 🇸🇬"
                
                markup = InlineKeyboardMarkup()
                markup.add(InlineKeyboardButton("🗑️ Key ဖျက်ရန် (Delete)", callback_data=f"delkey_ask_{server_num}_{key_id}"))

                detail_msg = (
                    f"👤 <b>Customer Information✅ </b>\n\n"
                    f"🤖 <b>Name:</b> {html.escape(full_name)}\n"
                    f"{order_line}"
                    f"📡 <b>Server:</b> {server_name}\n"
                    f"🧰 <b>Data Usage :</b> <code>{usage_gb} GB</code> / <code>{plan_gb}</code>\n"
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
        api_url = OUTLINE_API_URL_1 if server_num == "1" else (OUTLINE_API_URL_2 if server_num == "2" else OUTLINE_API_URL_3)
        try:
            del_res = requests.delete(f"{api_url}/access-keys/{key_id}", verify=False, timeout=12)
            if del_res.status_code in [200, 204]:
                bot.edit_message_text(f"✅ <b>Server {server_num} ပေါ်မှ Key (ID: {key_id}) အား အောင်မြင်စွာ ဖျက်ဆီးပြီးပါပြီဗျာ။</b>", chat_id=call.message.chat.id, message_id=call.message.message_id, parse_mode="HTML")
            else:
                bot.edit_message_text(f"❌ Key ဖျက်ရာတွင် အမှားအယွင်း ရှိနေပါသည် (Status: {del_res.status_code})", chat_id=call.message.chat.id, message_id=call.message.message_id)
        except Exception as e:
            bot.edit_message_text(f"❌ Error: {str(e)}", chat_id=call.message.chat.id, message_id=call.message.message_id)

    elif action == "cancel":
        bot.edit_message_text("❌ Key ဖျက်ခြင်းကို ပယ်ဖျက်လိုက်ပါပြီခင်ဗျာ။", chat_id=call.message.chat.id, message_id=call.message.message_id)

def get_user_next_key_number(user_name, target_chat_id=None):
    max_num = 0
    found_any = False
    clean_user = user_name.strip().lower()

    for api_url in [OUTLINE_API_URL_1, OUTLINE_API_URL_2, OUTLINE_API_URL_3]:
        try:
            res = requests.get(f"{api_url}/access-keys", verify=False, timeout=6)
            if res.status_code == 200:
                keys = res.json().get("accessKeys", [])
                for k in keys:
                    k_name = k.get("name", "")
                    k_name_lower = k_name.lower()

                    if (target_chat_id and f"({target_chat_id})" in k_name) or (clean_user in k_name_lower):
                        found_any = True
                        num_match = re.search(r'\((\d+)\)\s*\d{1,2}\.\d{1,2}\.', k_name)
                        if not num_match:
                            num_match = re.search(r'\((\d+)\)', k_name)

                        if num_match:
                            try:
                                val = int(num_match.group(1))
                                if str(val) != str(target_chat_id):
                                    if val > max_num:
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

def renew_or_create_unlimited_key(server_num, user_name, target_chat_id, months_count=1, order_id=None):
    api_url = OUTLINE_API_URL_1 if str(server_num) == "1" else (OUTLINE_API_URL_2 if str(server_num) == "2" else OUTLINE_API_URL_3)
    today = datetime.now()
    new_expire_date = (today + relativedelta(months=months_count)).strftime("%d.%m.%Y")
    add_bytes = (1000 * months_count) * 1000**3
    
    try:
        keys_resp = requests.get(f"{api_url}/access-keys", verify=False, timeout=12)
        metrics_resp = requests.get(f"{api_url}/metrics/transfer", verify=False, timeout=12)
        
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
                
                if order_id:
                    map_key_to_order(updated_name, order_id)

                raw_access_url = k.get("accessUrl", "")
                final_key = f"{raw_access_url}#{updated_name}"
                return final_key, updated_name, new_expire_date, True
    except Exception as e:
        print("Unlimited Renewal Error:", e)

    vpn_key, key_name, expire_date = create_outline_key(server_num, user_name, plan_info={"bytes": add_bytes}, target_chat_id=target_chat_id, months_count=months_count, is_giveaway=False, order_id=order_id)
    return vpn_key, key_name, expire_date, False

def create_outline_key(server_num, user_name, plan_info=None, custom_gb=None, target_chat_id=None, custom_days=None, months_count=1, is_giveaway=False, custom_expire_date=None, order_id=None):
    today = datetime.now()
    if custom_expire_date:
        expire_date = custom_expire_date
    elif custom_days:
        expire_date = (today + timedelta(days=custom_days)).strftime("%d.%m.%Y")
    else:
        expire_date = (today + relativedelta(months=months_count)).strftime("%d.%m.%Y")
    
    curr_max, next_number = get_user_next_key_number(user_name, target_chat_id)
    id_str = f" ({target_chat_id})" if target_chat_id else ""
    gw_str = " [GW]" if is_giveaway else ""
    
    if curr_max == 0:
        key_name = f"{user_name}{id_str}{gw_str} {expire_date}"
    else:
        key_name = f"{user_name}{id_str}{gw_str} ({next_number}) {expire_date}"
    
    api_url = OUTLINE_API_URL_1 if str(server_num) == "1" else (OUTLINE_API_URL_2 if str(server_num) == "2" else OUTLINE_API_URL_3)
    
    try:
        res = requests.post(f"{api_url}/access-keys", verify=False, timeout=12)
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
            
            if order_id:
                map_key_to_order(key_name, order_id)

            raw_access_url = key_data.get("accessUrl", "")
            final_key = f"{raw_access_url}#{key_name}"
            return final_key, key_name, expire_date
    except Exception as e:
        print("Key Generation Error:", e)
    return None, None, None

def generate_random_redeem_code():
    chars = string.ascii_lowercase + string.digits
    return ''.join(random.choices(chars, k=10))

@bot.callback_query_handler(func=lambda call: call.data.startswith("adm_srv_"))
def handle_admin_srv_select(call):
    bot.answer_callback_query(call.id)
    if str(call.message.chat.id) not in [str(aid) for aid in ADMIN_CHAT_IDS]:
        return
    
    srv = call.data.replace("adm_srv_", "")
    bot.edit_message_text(
        f"🎟️ <b>Server {srv} 🇸🇬 အတွက် Giveaway GB ပမာဏ ရွေးချယ်ပေးပါ:</b>",
        chat_id=call.message.chat.id,
        message_id=call.message.message_id,
        parse_mode="HTML",
        reply_markup=get_admin_gb_keyboard(srv)
    )

@bot.callback_query_handler(func=lambda call: call.data.startswith("adm_gb_"))
def handle_admin_gb_select(call):
    bot.answer_callback_query(call.id)
    if str(call.message.chat.id) not in [str(aid) for aid in ADMIN_CHAT_IDS]:
        return
    
    parts = call.data.split("_")
    srv = parts[2]
    gb = parts[3]
    
    bot.edit_message_text(
        f"🎟️ <b>Server {srv} 🇸🇬 | {gb} GB</b> အတွက် သက်တမ်း (ရက်) ရွေးချယ်ပေးပါခင်ဗျာ:",
        chat_id=call.message.chat.id,
        message_id=call.message.message_id,
        parse_mode="HTML",
        reply_markup=get_admin_days_keyboard(srv, gb)
    )

@bot.callback_query_handler(func=lambda call: call.data.startswith("adm_dur_"))
def handle_admin_days_select(call):
    bot.answer_callback_query(call.id)
    if str(call.message.chat.id) not in [str(aid) for aid in ADMIN_CHAT_IDS]:
        return
    
    parts = call.data.split("_")
    srv = parts[2]
    gb = parts[3]
    days = parts[4]
    
    bot.edit_message_text(
        f"🎟️ <b>Server {srv} 🇸🇬 | {gb} GB ({days} ရက်)</b> အတွက် မည်မျှအရေအတွက် Code ထုတ်ယူလိုပါသလဲ?",
        chat_id=call.message.chat.id,
        message_id=call.message.message_id,
        parse_mode="HTML",
        reply_markup=get_admin_count_keyboard(srv, gb, days)
    )

@bot.callback_query_handler(func=lambda call: call.data.startswith("adm_cnt_"))
def handle_admin_code_generate(call):
    bot.answer_callback_query(call.id, "✅ Code များထုတ်ပြီးပါပြီ!")
    if is_callback_processed(f"admcode_{call.message.message_id}_{call.data}"):
        return

    if str(call.message.chat.id) not in [str(aid) for aid in ADMIN_CHAT_IDS]:
        return
    
    parts = call.data.split("_")
    srv = parts[2]
    gb_amount = int(parts[3])
    days_amount = int(parts[4])
    count = int(parts[5])
    
    codes = load_redeem_codes()
    generated_list = []
    
    for _ in range(count):
        code = generate_random_redeem_code()
        codes[code] = {"server": srv, "gb": gb_amount, "days": days_amount}
        generated_list.append(f"<code>{code}</code>")
        
    save_redeem_codes(codes)
    
    reply_msg = (
        f"🎉 <b>Server {srv} 🇸🇬 | {gb_amount} GB ({days_amount} ရက်) Giveaway Code ({count} ခု) ထုတ်ပြီးပါပြီ:</b>\n\n" +
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

        plan_data = {
            "code": plan_code,
            "name": plan["name"],
            "data": data_disp,
            "months": 1,
            "price_str": f"{amount:,} Ks",
            "price_int": amount
        }
        save_user_plan(chat_id, plan_data)

        markup = InlineKeyboardMarkup()
        markup.row(InlineKeyboardButton("🔙 Plan များသို့ ပြန်သွားရန်", callback_data="back_to_plans"))
        markup.row(InlineKeyboardButton("🔙 မူလ Menu သို့ ပြန်သွားရန်", callback_data="back_to_main"))

        payment_text = (
            f"✅ သင်ရွေးချယ်ထားသော Plan:\n"
            f"📌 {plan['name']} ({data_disp}) - 1 လစာ ({amount:,} Ks)\n\n"
            f"━━━━━━━━━━━━━━━\n"
            f"💰 ငွေလွှဲရမည့် အကောင့်အချက်အလက်များ:\n\n"
            f"📱 KBZ Pay - 09264041218\n"
            f"👤 Ma Ei Ei Nway\n\n"
            f"📱 Wave Pay - 09699970092\n"
            f"👤 Htet Myat Aung\n\n"
            f"📱 AYA Pay - 09699970092\n"
            f"👤 Htet Myat Aung\n\n"
            f"📱 Uab Pay - 09699970092\n"
            f"👤 Htet Myat Aung\n\n"
            f"📱 CB Pay - 09699970092\n"
            f"👤 Htet Myat Aung\n\n"
            f"━━━━━━━━━━━━━━━\n\n"
            f"🙏🏻 ငွေလွှဲပြီး 📸Screenshotလေး ပို့ပေးပါခင်ဗျာ🥰\n\n"
            f"ပြေစာစစ်ဆေးပြီးသည်နှင့် VPN Key ကို အမြန်ဆုံး ပို့ပေးပါမည်။\n\n"
            f"⚠️ Ultimate VIP - Unlimited Plan သက်တမ်းတိုးရန် Note မှာ Renew Key လို့ရေးပေးပါ။\n\n"
            f"ကျန် Plan များ ကီးသက်တမ်းတိုးမရပါ။\n\n"
        )

        bot.edit_message_text(
            payment_text,
            chat_id=chat_id,
            message_id=call.message.message_id,
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

# Admin Server 1 / Server 2 / Server 3 Approve Callback Handler
@bot.callback_query_handler(func=lambda call: call.data.startswith("approve_srv"))
def handle_approve_callback(call):
    lock_key = f"appr_{call.message.message_id}_{call.data}"
    if is_callback_processed(lock_key):
        try:
            bot.answer_callback_query(call.id, "⚠️ ဒီ Key ကို ထုတ်ပေးပြီးပါပြီ။")
        except:
            pass
        return

    if str(call.message.chat.id) not in [str(aid) for aid in ADMIN_CHAT_IDS]:
        return
        
    try:
        parts = call.data.split("_")
        server_num = parts[1].replace("srv", "")
        target_chat_id = parts[2]
        plan_code = parts[3]
        months_count = int(parts[4]) if len(parts) > 4 else 1
        action_type = parts[5] if len(parts) > 5 else "new"
        order_id = parts[6] if len(parts) > 6 else None
        
        plan_info = PLANS.get(plan_code, PLANS["starter"])
        
        user_plans = load_user_plans()
        u_plan = user_plans.get(str(target_chat_id), {})
        price_int = u_plan.get("price_int")
        price_str = u_plan.get("price_str", f"{price_int:,} Ks" if price_int else f"{plan_info['price']:,} Ks")
        
        if not price_int:
            price_int = plan_info["price"]

        chat_info = bot.get_chat(target_chat_id)
        user_first = chat_info.first_name if chat_info.first_name else ""
        user_last = chat_info.last_name if chat_info.last_name else ""
        user_name = f"{user_first} {user_last}".strip() or "HMA Customer"
        
        vpn_key = None
        key_name = None
        expire_date = None

        if plan_code == "ultimate" and action_type == "renew":
            vpn_key, key_name, expire_date, is_renew = renew_or_create_unlimited_key(server_num, user_name, target_chat_id, months_count=months_count, order_id=order_id)
            action_title = "🎉 <b>Unlimited Plan သက်တမ်း အောင်မြင်စွာ တိုးမြှင့်ပြီးပါပြီခင်ဗျာ။</b>"
            disp_gb = f"{1000 * months_count} GB"
        else:
            vpn_key, key_name, expire_date = create_outline_key(server_num, user_name, plan_info=plan_info, target_chat_id=target_chat_id, months_count=months_count, is_giveaway=False, order_id=order_id)
            action_title = "🎉 <b>ငွေလွှဲမှု အောင်မြင်စွာ အတည်ပြုပြီးပါပြီခင်ဗျာ။</b>"
            disp_gb = f"{1000 * months_count} GB" if plan_code == "ultimate" else f"{int(plan_info['data'].split()[0]) * months_count} GB"
        
        if vpn_key:
            if str(target_chat_id) not in [str(aid) for aid in ADMIN_CHAT_IDS]:
                save_sale_transaction(server_num, target_chat_id, plan_code, plan_info['name'], months_count, price_int, order_id=order_id)

            save_user_purchase_record(
                chat_id=target_chat_id,
                order_id=order_id,
                plan_name=plan_info['name'],
                disp_gb=disp_gb,
                months_count=months_count,
                price_str=price_str,
                server_num=server_num,
                expire_date=expire_date,
                vpn_key=vpn_key
            )

            ord_line = f"🧾 <b>Order ID:</b> <code>{order_id}</code>\n" if order_id else ""
            success_message = (
                f"{action_title}\n\n"
                f"{ord_line}"
                f"👤 <b>ဝယ်ယူသူ:</b> {user_name}\n"
                f"🛍️ <b>Plan:</b> {plan_info['name']} ({disp_gb}) - {months_count} လစာ\n"
                f"⏰ <b>သက်တမ်းကုန်ဆုံးရက်:</b> {expire_date}\n\n"
                f"🔑 <b>လူကြီးမင်း၏ VPN Key</b>\n\n"
                f"<code>{vpn_key}</code>\n\n"
                f"☝️ အပေါ်က Key  ကို <b>တစ်ချက်တည်း နှိပ်လိုက်ရုံဖြင့်</b> Auto Copy ကူးသွားပါလိမ့်မယ်ခင်ဗျာ။ V2BOX VPN App ထဲသို့ ထည့်သွင်းအသုံးပြုနိုင်ပါပြီ။"
            )
            bot.send_message(target_chat_id, success_message, parse_mode="HTML")
            
            clean_name = user_name.strip().lower()
            save_key_mapping(clean_name, target_chat_id)
            
            admin_msg_map = get_admin_msg_map(target_chat_id)
            updated_caption = call.message.caption + f"\n\n✅ <b>DONE (📡 Server {server_num} 🇸🇬)</b>\n\n🔑 {key_name}" if call.message.caption else f"✅ <b>DONE (📡 Server {server_num} 🇸🇬)</b>\n\n🔑 {key_name}"

            for aid, mid in admin_msg_map.items():
                try:
                    bot.edit_message_caption(
                        chat_id=aid,
                        message_id=mid,
                        caption=updated_caption,
                        parse_mode="HTML",
                        reply_markup=None
                    )
                except:
                    pass
            
            bot.answer_callback_query(call.id, "✅ Customer ထံသို့ VPN Keyအား အောင်မြင်စွာ ပို့ပေးလိုက်ပါပြီခင်ဗျာ။", show_alert=False)
    except Exception as e:
        print("Approve Error:", str(e))
        try:
            bot.answer_callback_query(call.id, f"❌ Error: {str(e)}", show_alert=True)
        except:
            pass

# 📸 Photo Message Handler (Screenshot & Broadcast Photo Support)
@bot.message_handler(content_types=['photo'])
def handle_photo_messages(message):
    chat_id = message.chat.id
    save_user_id(chat_id)

    if not is_user_subscribed(chat_id):
        send_force_join_message(chat_id)
        return

    # 📢 Admin Broadcast Photo Handler
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

    # 🛍️ Payment Screenshot Handler
    clear_all_states(chat_id)

    user_first = message.from_user.first_name if message.from_user.first_name else ""
    user_last = message.from_user.last_name if message.from_user.last_name else ""
    user_name = f"{user_first} {user_last}".strip() or "HMA User"
        
    username = f"@{message.from_user.username}" if message.from_user.username else "No Username"
    user_plans = load_user_plans()
    
    if str(chat_id) not in user_plans:
        bot.reply_to(message, "⚠️ ခွင့်လွှတ်ပါခင်ဗျာ၊ ကျေးဇူးပြု၍ '🛍️ Plan များ ကြည့်ရန်' ခလုတ်ကို အရင်နှိပ်ပြီး ဝယ်ယူလိုသော Plan ကို ရွေးချယ်ပေးပါဦးခင်ဗျာ။")
        return

    plan_info = user_plans.get(str(chat_id))
    plan_code = plan_info.get('code', 'starter')
    months_count = plan_info.get('months', 1)
    price_str = plan_info.get('price_str', f"{plan_info.get('price_int', 1000):,} Ks")
    current_date = datetime.fromtimestamp(message.date).strftime("%d/%m/%Y")

    photo_file = bot.get_file(message.photo[-1].file_id)
    order_id = generate_order_id_from_slip(photo_file.file_path)

    order_record = {
        "order_id": order_id,
        "chat_id": str(chat_id),
        "user_name": user_name,
        "username": username,
        "plan_code": plan_code,
        "plan_name": plan_info['name'],
        "months": months_count,
        "price_str": price_str,
        "date": current_date,
        "timestamp": (datetime.utcnow() + timedelta(hours=6, minutes=30)).strftime("%Y-%m-%d %H:%M:%S")
    }
    save_order(order_id, order_record)

    admin_alert_text = (
        f"💰 <b>ငွေလွှဲပြေစာအသစ်</b>\n"
        f"🧾 Order ID: <code>{order_id}</code>\n"
        f"👤 ဝယ်ယူသူနာမည်: {user_name} ({username})\n"
        f"🛍️ ရွေးချယ်ထားသော Plan: {plan_info['name']} ({plan_info.get('data', '')}) [{months_count} လစာ]\n"
        f"💵 ကျသင့်ငွေပမာဏ: {price_str}\n"
        f"📅 ပေးပို့သည့်ရက်စွဲ: {current_date}\n"
        f"🆔 User Chat ID: {chat_id}"
    )
    
    approve_markup = InlineKeyboardMarkup()
    if plan_code == "ultimate":
        approve_markup.row(
            InlineKeyboardButton("📡 S1 🇸🇬 Renew", callback_data=f"approve_srv1_{chat_id}_{plan_code}_{months_count}_renew_{order_id}"),
            InlineKeyboardButton("📡 S1 🇸🇬 New", callback_data=f"approve_srv1_{chat_id}_{plan_code}_{months_count}_new_{order_id}")
        )
        approve_markup.row(
            InlineKeyboardButton("📡 S2 🇸🇬 Renew", callback_data=f"approve_srv2_{chat_id}_{plan_code}_{months_count}_renew_{order_id}"),
            InlineKeyboardButton("📡 S2 🇸🇬 New", callback_data=f"approve_srv2_{chat_id}_{plan_code}_{months_count}_new_{order_id}")
        )
        approve_markup.row(
            InlineKeyboardButton("📡 S3 🇸🇬 Renew", callback_data=f"approve_srv3_{chat_id}_{plan_code}_{months_count}_renew_{order_id}"),
            InlineKeyboardButton("📡 S3 🇸🇬 New", callback_data=f"approve_srv3_{chat_id}_{plan_code}_{months_count}_new_{order_id}")
        )
    else:
        approve_markup.row(
            InlineKeyboardButton("📡 Server 1 🇸🇬", callback_data=f"approve_srv1_{chat_id}_{plan_code}_{months_count}_new_{order_id}"),
            InlineKeyboardButton("📡 Server 2 🇸🇬", callback_data=f"approve_srv2_{chat_id}_{plan_code}_{months_count}_new_{order_id}")
        )
        approve_markup.row(
            InlineKeyboardButton("📡 Server 3 🇸🇬", callback_data=f"approve_srv3_{chat_id}_{plan_code}_{months_count}_new_{order_id}")
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
        user_reply_text = (
            f"💌 <b>ငွေလွှဲပြေစာအား လက်ခံရရှိပါသည်ခင်ဗျာ။</b>\n\n"
            f"🧾 <b>Order ID:</b> <code>{order_id}</code>\n\n"
            f"🛍️ <b>Plan:</b> {plan_info['name']} ({plan_info.get('data', '')})\n\n"
            f"💵 <b>ပမာဏ:</b> {price_str}\n\n"
            f"<i>Admin မှ ပြေစာစစ်ဆေးအတည်ပြုပြီးသည်နှင့် VPN Key ကို ချက်ချင်း ပို့ပေးပါမည်။ ကျေးဇူးတင်ပါသည်ခင်ဗျာ။ 🙏</i>"
        )
        bot.reply_to(message, user_reply_text, parse_mode="HTML")
    except Exception as e:
        bot.reply_to(message, f"❌ Admin ထံ ပို့၍မရပါ - Bot အား အကောင့်မှ Start နှိပ်ထားရန် လိုအပ်ပါသည်။")

# ⚡️ Fetch Key From Server (Timeout 10s နှင့် Metrics Fallback ပါဝင်သည်)
def fetch_key_from_server(api_url, input_value):
    if not api_url or "dummyKey" in api_url:
        return None, None, None
        
    api_url = api_url.rstrip('/')
    
    try:
        keys_resp = requests.get(f"{api_url}/access-keys", verify=False, timeout=10)
        
        bytes_transferred = {}
        try:
            metrics_resp = requests.get(f"{api_url}/metrics/transfer", verify=False, timeout=5)
            if metrics_resp.status_code == 200:
                bytes_transferred = metrics_resp.json().get("bytesTransferredByUserId", {})
        except:
            bytes_transferred = {}
        
        if keys_resp.status_code != 200:
            return None, None, None
            
        keys_data = keys_resp.json().get("accessKeys", [])
        
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
            if api_url == OUTLINE_API_URL_1.rstrip('/'):
                server_num = "1"
            elif api_url == OUTLINE_API_URL_2.rstrip('/'):
                server_num = "2"
            else:
                server_num = "3"
            return target_key, bytes_transferred, server_num
    except Exception as e:
        print(f"Fetch Key Error on {api_url}:", e)
    return None, None, None

# 🔄 Admin Key Replacement Approval Callback Handler
@bot.callback_query_handler(func=lambda call: call.data.startswith("replace_"))
def handle_admin_replace_callback(call):
    lock_key = f"repl_{call.message.message_id}_{call.data}"
    if is_callback_processed(lock_key):
        try:
            bot.answer_callback_query(call.id, "⚠️ ဒီ တောင်းဆိုမှုကို လုပ်ဆောင်ပြီးပါပြီ။")
        except:
            pass
        return

    if str(call.message.chat.id) not in [str(aid) for aid in ADMIN_CHAT_IDS]:
        return

    parts = call.data.split("_")
    action = parts[1]

    if action == "reject":
        target_chat_id = parts[2]
        request_key = f"{target_chat_id}_{parts[3] if len(parts) > 3 else ''}"
        try:
            bot.send_message(target_chat_id, "❌ <b>လူကြီးမင်း တောင်းဆိုထားသော Key အစားထိုးခြင်းအား Admin မှ ငြင်းပယ်လိုက်ပါသည်ခင်ဗျာ။ အသေးစိတ် သိရှိလိုပါက Admin ထံ တိုက်ရိုက် ဆက်သွယ်ပေးပါ။</b>", parse_mode="HTML")
        except:
            pass
        
        repl_msg_map = get_replacement_msg_map(request_key)
        for aid, mid in repl_msg_map.items():
            try:
                bot.edit_message_text(
                    call.message.text + "\n\n❌ <b>REJECTED</b>",
                    chat_id=aid,
                    message_id=mid,
                    parse_mode="HTML",
                    reply_markup=None
                )
            except:
                pass
        
        try:
            bot.edit_message_text(call.message.text + "\n\n❌ <b>REJECTED</b>", chat_id=call.message.chat.id, message_id=call.message.message_id, parse_mode="HTML", reply_markup=None)
        except:
            pass
            
        bot.answer_callback_query(call.id, "❌ Key အစားထိုးခြင်းကို ငြင်းပယ်လိုက်ပါပြီ။", show_alert=False)
        return

    new_server_num = parts[1].replace("srv", "")
    old_server_num = parts[2]
    old_key_id = parts[3]
    target_chat_id = parts[4]
    rem_gb = float(parts[5])
    exp_date = parts[6]

    request_key = f"{target_chat_id}_{old_key_id}"
    api_url_old = OUTLINE_API_URL_1 if old_server_num == "1" else (OUTLINE_API_URL_2 if old_server_num == "2" else OUTLINE_API_URL_3)
    
    try:
        requests.delete(f"{api_url_old}/access-keys/{old_key_id}", verify=False, timeout=8)

        chat_info = bot.get_chat(target_chat_id)
        user_first = chat_info.first_name if chat_info.first_name else ""
        user_last = chat_info.last_name if chat_info.last_name else ""
        user_name = f"{user_first} {user_last}".strip() or "HMA Customer"

        new_key, new_key_name, expire_date = create_outline_key(
            new_server_num, 
            user_name, 
            custom_gb=rem_gb, 
            target_chat_id=target_chat_id, 
            custom_expire_date=exp_date
        )

        if new_key:
            success_msg = (
                f"🎉 <b>လူကြီးမင်း၏ VPN Key ကို အဆင်ပြေစွာ အသစ် လဲလှယ်ပေးလိုက်ပါပြီခင်ဗျာ!</b>\n\n"
                f"👤 <b>အသုံးပြုသူ:</b> {user_name}\n\n"
                f"📡 <b>Server အသစ်:</b> Server {new_server_num} 🇸🇬\n\n"
                f"🧰 <b>ကျန်ရှိသော Data:</b> {rem_gb} GB\n\n"
                f"⏰ <b>သက်တမ်းကုန်ဆုံးရက်:</b> {expire_date}\n\n"
                f"🔑 <b>VPN Key အသစ်:</b>\n\n"
                f"<code>{new_key}</code>\n\n"
                f"☝️ အပေါ်က Key ကို <b>တစ်ချက်တည်း နှိပ်လိုက်ရုံဖြင့်</b> Auto Copy ကူးသွားပါလိမ့်မယ်ခင်ဗျာ။"
            )
            bot.send_message(target_chat_id, success_msg, parse_mode="HTML")
            
            repl_msg_map = get_replacement_msg_map(request_key)
            for aid, mid in repl_msg_map.items():
                try:
                    bot.edit_message_text(
                        call.message.text + f"\n\n✅ <b>REPLACED (Server {new_server_num} 🇸🇬)</b>",
                        chat_id=aid,
                        message_id=mid,
                        parse_mode="HTML",
                        reply_markup=None
                    )
                except:
                    pass

            try:
                bot.edit_message_text(call.message.text + f"\n\n✅ <b>REPLACED (Server {new_server_num} 🇸🇬)</b>", chat_id=call.message.chat.id, message_id=call.message.message_id, parse_mode="HTML", reply_markup=None)
            except:
                pass

            bot.answer_callback_query(call.id, "✅ Key အသစ် အစားထိုး ပို့ပေးလိုက်ပါပြီခင်ဗျာ။", show_alert=False)
    except Exception as e:
        print("Replace Approve Error:", str(e))
        try:
            bot.answer_callback_query(call.id, f"❌ Error: {str(e)}", show_alert=True)
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

    # 📢 Admin Broadcast Text Handler
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

    if input_value in ["🛍️ Plan များ ကြည့်ရန်", "Plan များ ကြည့်ရန်", "🛍️ Plan ကြည့်ရန်"]:
        clear_all_states(chat_id)
        bot.send_message(chat_id, "🧸  လူကြီးမင်း ဝယ်ယူလိုသော VPN Plan ကို ရွေးချယ်ပေးပါခင်ဗျာ:", reply_markup=get_plan_keyboard())
        return

    # 📇 Customer Purchase History Handler
    if input_value in ["📇 ဝယ်ယူမှုမှတ်တမ်း", "ဝယ်ယူမှုမှတ်တမ်း"]:
        clear_all_states(chat_id)
        records = get_user_combined_purchase_records(chat_id)
        if not records:
            empty_msg = (
                "📇 <b>လူကြီးမင်း၏ ဝယ်ယူမှုမှတ်တမ်း</b>\n\n"
                "<i>လက်ရှိတွင် ဝယ်ယူထားသော မှတ်တမ်း မရှိသေးပါခင်ဗျာ။ '🛍️ Plan များ ကြည့်ရန်' မှတစ်ဆင့် စတင်ဝယ်ယူနိုင်ပါသည်ခင်ဗျာ။</i>"
            )
            bot.send_message(chat_id, empty_msg, parse_mode="HTML", reply_markup=get_back_inline_keyboard())
            return

        history_texts = []
        for idx, rec in enumerate(reversed(records), 1):
            srv_name = f"Singapore Server {rec.get('server', '1')} 🇸🇬"
            vpn_k = rec.get('vpn_key', '')
            key_block = f"<code>{vpn_k}</code>" if vpn_k != "N/A" else "<i>(Server Maintenance ဖြစ်နေပါသဖြင့် အထက်ပါ Menu ရှိ '♻️ Key လဲရန်' ဖြင့် အသစ်လဲလှယ်နိုင်ပါသည်)</i>"
            
            item_txt = (
                f"<b>#{idx} | ဝယ်ယူမှု အချက်အလက်</b>\n\n"
                f"🧾 <b>Order ID:</b> <code>{rec.get('order_id', 'N/A')}</code>\n\n"
                f"📅 <b>ဝယ်ယူသည့် အချိန်:</b> <code>{rec.get('timestamp', 'N/A')}</code>\n\n"
                f"🛍️ <b>Plan:</b> {rec.get('plan_name', '')} ({rec.get('disp_gb', '')}) [{rec.get('months', 1)} လစာ]\n\n"
                f"💵 <b>ကျသင့်ငွေ:</b> {rec.get('price_str', '')}\n\n"
                f"📡 <b>Server:</b> {srv_name}\n\n"
                f"⏰ <b>သက်တမ်းကုန်ရက်:</b> <code>{rec.get('expire_date', 'N/A')}</code>\n\n"
                f"🔑 <b>VPN Key:</b>\n\n"
                f"{key_block}"
            )
            history_texts.append(item_txt)

        final_history_msg = (
            f"📇 <b>လူကြီးမင်း ဝယ်ယူခဲ့သော VPN Key များ ({len(records)} ခု):</b>\n\n" +
            "\n\n━━━━━━━━━━━━━━━━━\n\n".join(history_texts) +
            "\n\n☝️ <i>Key Link ကို တစ်ချက်နှိပ်လိုက်ရုံဖြင့် Auto Copy ကူးယူနိုင်ပါသည်ခင်ဗျာ။</i>"
        )
        
        if len(final_history_msg) > 4000:
            for piece in [final_history_msg[i:i+4000] for i in range(0, len(final_history_msg), 4000)]:
                bot.send_message(chat_id, piece, parse_mode="HTML")
        else:
            bot.send_message(chat_id, final_history_msg, parse_mode="HTML", reply_markup=get_back_inline_keyboard())
        return
        
    if input_value in ["🧰 Data Usage စစ်ရန်", "Data Usage စစ်ရန်", "⚡ Data Usage စစ်ရန်"]:
        clear_all_states(chat_id)
        check_guide = (
            "👇 ဝယ်ယူထားသော VPN Key ကို ဒီမှာ Paste ချပေးပါ:\n\n"
            " 🫶 Key ကို Copy ယူလာတဲ့ ss://... နဲ့စတဲ့ Key တစ်ခုလုံးကို ဒီ Chat ထဲသို့ တန်းပြီး Paste ချပို့ပြီး စစ်ဆေးနိုင်ပါတယ်ခင်ဗျာ။"
        )
        bot.send_message(chat_id, check_guide, reply_markup=get_back_inline_keyboard())
        return

    if input_value in ["♻️ Key လဲရန်", "Key အဆင်မပြေပါက လဲရန်"]:
        clear_all_states(chat_id)
        set_replacement_state(chat_id, True)
        replace_guide = (
            "♻️ <b>VPN Key အစားထိုး လဲလှယ်ရန်:</b>\n\n"
            "👇 အဆင်မပြေ ဖြစ်နေသော VPN Key (<code>ss://...</code>) ကို ဒီ Chat ထဲသို့ Paste ချ ပေးပို့ပေးပါခင်ဗျာ။\n"
            "<i>(Bot မှ ကျန်ရှိသော ရက်/Data များကို စစ်ဆေး၍ Admin ထံ အစားထိုး တောင်းဆိုပေးပါမည်။)</i>"
        )
        bot.send_message(chat_id, replace_guide, parse_mode="HTML", reply_markup=get_back_inline_keyboard())
        return

    if input_value in ["🎁 Public Free Key", "Public Free Key"]:
        clear_all_states(chat_id)
        free_key = "ss://Y2hhY2hhMjAtaWV0Zi1wb2x5MTMwNTpmck9iNk9hcHQ3TXNnaWZNbE14a0JX@h.e.feature.hma.qzz.io:443/?outline=1##🚀🌩️ HMA | Thunder Strike ⚡️"
        free_text = (
            f"🎁 <b>H & E FEATURE PREMIUM VPN မှ လူအများအတွက် 1.5TB အထိ အခမဲ့သုံးစွဲနိုင်သော Premium Key ဖြစ်ပါတယ်ခင်ဗျာ။</b>\n\n"
            f"<code>{free_key}</code>\n\n"
            f"☝️ အပေါ်က ကီးလေးကို <b>တစ်ချက်တည်း နှိပ်လိုက်ရုံဖြင့်</b> Auto Copy ကူးသွားပါလိမ့်မယ်ခင်ဗျာ။"
        )
        bot.send_message(chat_id, free_text, parse_mode="HTML", reply_markup=get_back_inline_keyboard())
        return

    if input_value in ["🎟️ Redeem Code", "Redeem Code"]:
        clear_all_states(chat_id)
        
        if has_active_giveaway_key(chat_id) and str(chat_id) not in [str(aid) for aid in ADMIN_CHAT_IDS]:
            bot.send_message(chat_id, "⚠️ <b>ခွင့်လွှတ်ပါခင်ဗျာ၊ လူကြီးမင်းတွင် လက်ရှိ အသုံးပြုနေဆဲ Giveaway Key ရှိနေပါသေးသည်။ အဆိုပါ Key သက်တမ်းကုန်ဆုံးမှသာ Redeem Code အသစ် ပြန်လည် ထုတ်ယူနိုင်ပါမည်ခင်ဗျာ။</b>", parse_mode="HTML", reply_markup=get_back_inline_keyboard())
            return

        set_redeem_state(chat_id, True)
        redeem_guide = (
            "🎟️ <b>Giveaway Redeem Code အသုံးပြုရန်:</b>\n\n"
            "👇 Admin ထံမှ ရရှိထားသော Redeem Code (ဥပမာ- <code>a8k2m9x4p1</code>) ကို ဒီ Chat ထဲသို့ Paste ချပို့ပေးပါခင်ဗျာ။"
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
        bot.send_message(
            chat_id, 
            "🔍 <b>Customer ရှာဖွေရန်:</b>\n\n👇 ရှာဖွေလိုသော <b>Cus နာမည်အစ စာလုံး (ဥပမာ - H, T, A) သို့မဟုတ် Order ID</b> ကို ဒီ Chat ထဲသို့ ရိုက်ပို့ပေးပါခင်ဗျာ:", 
            parse_mode="HTML",
            reply_markup=get_back_inline_keyboard()
        )
        return

    if input_value == "🎟️ Gen RD Code":
        clear_all_states(chat_id)
        if str(chat_id) not in [str(aid) for aid in ADMIN_CHAT_IDS]:
            bot.reply_to(message, "❌ ခွင့်လွှတ်ပါ၊ ဒီ ခလုတ်သည် Admin သီးသန့် အသုံးပြုနိုင်သော ခလုတ်ဖြစ်ပါသည်။")
            return
        
        bot.send_message(
            chat_id, 
            "🎟️ <b>Giveaway Redeem Code ထုတ်ရန်:</b>\n\nကျေးဇူးပြု၍ မည်သည့် <b>Server</b> အတွက် Code ထုတ်ယူမည်ကို အရင်ဆုံး ရွေးချယ်ပေးပါခင်ဗျာ:", 
            parse_mode="HTML", 
            reply_markup=get_admin_server_keyboard()
        )
        return

    if input_value == "📢 Broadcast စာပို့ရန်":
        clear_all_states(chat_id)

        if str(chat_id) not in [str(aid) for aid in ADMIN_CHAT_IDS]:
            bot.reply_to(message, "❌ ခွင့်လွှတ်ပါ၊ ဒီ ခလုတ်သည် Admin သီးသန့် အသုံးပြုနိုင်သော ခလုတ်ဖြစ်ပါသည်။")
            return

        all_users = load_all_users()
        set_broadcast_state(chat_id, True)

        bot.send_message(
            chat_id,
            f"📢 <b>Broadcast Announcement စာပို့ရန်:</b>\n\n"
            f"👥 လက်ရှိ Bot သုံးစွဲသူ စုစုပေါင်း: <b>{len(all_users)} ယောက်</b>\n\n"
            f"👇 လူတိုင်းဆီ ကြေညာလိုသော <b>စာသား (သို့မဟုတ်) ဓာတ်ပုံ (Caption ပါရှိနိုင်သည်)</b> ကို ဒီ Chat ထဲသို့ Paste ချ ပေးပို့ပေးပါခင်ဗျာ:",
            parse_mode="HTML",
            reply_markup=get_back_inline_keyboard()
        )
        return

    if str(chat_id) in [str(aid) for aid in ADMIN_CHAT_IDS] and get_search_state(chat_id):
        set_search_state(chat_id, False)
        bot.send_message(chat_id, f"⏳ <b>'{input_value}'</b> ဖြင့် ရှာဖွေနေပါသည်...", parse_mode="HTML")
        
        matches, search_markup = search_users_by_query(input_value)
        if matches:
            search_markup.add(InlineKeyboardButton("🔙 မူလ Menu သို့ ပြန်သွားရန်", callback_data="back_to_main"))
            bot.send_message(
                chat_id, 
                f"🔎 <b>ရှာဖွေတွေ့ရှိသော Customer စာရင်း ({len(matches)} ခု):</b>\n\n👇 အောက်ပါ ခလုတ်များထဲမှ အသေးစိတ်ကြည့်လိုသော Cus ကို နှိပ်ပါ -", 
                parse_mode="HTML", 
                reply_markup=search_markup
            )
        else:
            bot.send_message(chat_id, f"❌ <b>'{input_value}'</b> ဖြင့် ရှာဖွေ၍ မတွေ့ပါခင်ဗျာ။", parse_mode="HTML", reply_markup=get_back_inline_keyboard())
        return

    if get_replacement_state(chat_id):
        set_replacement_state(chat_id, False)
        
        bot.send_message(chat_id, "⏳ လူကြီးမင်း ပေးပို့ထားသော Key အား စစ်ဆေးနေပါသည်...")
        
        target_key, bytes_transferred, server_num = fetch_key_from_server(OUTLINE_API_URL_1, input_value)
        if not target_key:
            target_key, bytes_transferred, server_num = fetch_key_from_server(OUTLINE_API_URL_2, input_value)
        if not target_key:
            target_key, bytes_transferred, server_num = fetch_key_from_server(OUTLINE_API_URL_3, input_value)

        if target_key:
            full_name = target_key.get("name", "HMA User")
            key_id = str(target_key.get("id"))
            
            date_match = re.search(r'\d{1,2}\.\d{1,2}\.(\d{4}|\d{2})', full_name)
            exp_date = date_match.group(0) if date_match else "30.09.2026"

            order_id_disp = get_order_id_for_key(full_name)
            order_line = f"🧾 Order ID: <code>{order_id_disp}</code>\n" if order_id_disp != "N/A" else ""
            
            limit_bytes = target_key.get("dataLimit", {}).get("bytes", 0)
            usage_bytes = bytes_transferred.get(key_id, 0)
            
            total_gb = bytes_to_gb(limit_bytes) if limit_bytes else 1000
            used_gb = bytes_to_gb(usage_bytes)
            rem_gb = max(0, round(total_gb - used_gb, 2))

            user_first = message.from_user.first_name if message.from_user.first_name else ""
            user_last = message.from_user.last_name if message.from_user.last_name else ""
            user_name = f"{user_first} {user_last}".strip() or "Customer"
            username = f"@{message.from_user.username}" if message.from_user.username else "No Username"

            alert_text = (
                f"♻️ <b>KEY REPLACEMENT REQUEST</b>\n\n"
                f"{order_line}"
                f"👤 ဝယ်ယူသူ: {user_name} ({username})\n"
                f"🆔 Chat ID: <code>{chat_id}</code>\n"
                f"📡 လက်ရှိ Server: Server {server_num}\n"
                f"🔑 Key အဟောင်း: {full_name}\n"
                f"🧰 ကျန်ရှိ Data: <b>{rem_gb} GB</b> / {total_gb} GB\n"
                f"⏰ သက်တမ်းကုန်ရက်: <b>{exp_date}</b>"
            )

            markup = InlineKeyboardMarkup()
            markup.row(
                InlineKeyboardButton("📡 S1 သို့", callback_data=f"replace_srv1_{server_num}_{key_id}_{chat_id}_{rem_gb}_{exp_date}"),
                InlineKeyboardButton("📡 S2 သို့", callback_data=f"replace_srv2_{server_num}_{key_id}_{chat_id}_{rem_gb}_{exp_date}"),
                InlineKeyboardButton("📡 S3 သို့", callback_data=f"replace_srv3_{server_num}_{key_id}_{chat_id}_{rem_gb}_{exp_date}")
            )
            markup.row(InlineKeyboardButton("❌ Reject (ငြင်းပယ်မည်)", callback_data=f"replace_reject_{chat_id}_{key_id}"))

            request_key = f"{chat_id}_{key_id}"
            repl_msg_dict = {}

            for aid in ADMIN_CHAT_IDS:
                try:
                    sent_msg = bot.send_message(aid, alert_text, parse_mode="HTML", reply_markup=markup)
                    if sent_msg:
                        repl_msg_dict[str(aid)] = sent_msg.message_id
                except:
                    pass

            save_replacement_msg_map(request_key, repl_msg_dict)

            bot.send_message(chat_id, "✅ <b>Key အချက်အလက်များ တောင်းဆိုမှု အောင်မြင်ပါသည်။ Admin မှ စစ်ဆေး၍ Key အသစ် အမြန်ဆုံး လဲလှယ်ပေးပါမည်။</b>", parse_mode="HTML", reply_markup=get_back_inline_keyboard())
            return
        else:
            bot.send_message(chat_id, "❌ <b>ပေးပို့ထားသော Key ကို Server ပေါ်တွင် ရှာမတွေ့ပါခင်ဗျာ။ မှန်ကန်သော Key Link ကို Paste ချပို့ပေးပါ။</b>", parse_mode="HTML", reply_markup=get_back_inline_keyboard())
            return

    if get_redeem_state(chat_id):
        set_redeem_state(chat_id, False)
        
        if has_active_giveaway_key(chat_id) and str(chat_id) not in [str(aid) for aid in ADMIN_CHAT_IDS]:
            bot.send_message(chat_id, "⚠️ <b>ခွင့်လွှတ်ပါခင်ဗျာ၊ လူကြီးမင်းတွင် လက်ရှိ အသုံးပြုနေဆဲ Giveaway Key ရှိနေပါသေးသည်။ အဆိုပါ Key သက်တမ်းကုန်ဆုံးမှသာ Redeem Code အသစ် ပြန်လည် ထုတ်ယူနိုင်ပါမည်ခင်ဗျာ။</b>", parse_mode="HTML", reply_markup=get_back_inline_keyboard())
            return

        codes = load_redeem_codes()
        code_input = input_value.strip().lower()
        
        matched_code_key = None
        for c_k in codes.keys():
            if c_k.strip().lower() == code_input:
                matched_code_key = c_k
                break

        if matched_code_key:
            code_info = codes[matched_code_key]
            if isinstance(code_info, dict):
                target_srv = str(code_info.get("server", "1"))
                gb_val = code_info.get("gb", 25)
                days_val = code_info.get("days", 1)
            else:
                target_srv = "1"
                gb_val = int(code_info)
                days_val = 1

            user_name = message.from_user.first_name if message.from_user.first_name else "Giveaway Winner"
            
            del codes[matched_code_key]
            save_redeem_codes(codes)

            bot.send_message(chat_id, f"🎟️ Redeem Code မှန်ကန်ပါသည်။ Server {target_srv} ပေါ်မှ VPN Key ကို ထုတ်ပေးနေပါသည်...")
            
            vpn_key, key_name, expire_date = create_outline_key(target_srv, user_name, custom_gb=gb_val, target_chat_id=chat_id, custom_days=days_val, is_giveaway=True)
            if not vpn_key:
                for alt_srv in ["1", "2", "3"]:
                    if alt_srv != target_srv:
                        vpn_key, key_name, expire_date = create_outline_key(alt_srv, user_name, custom_gb=gb_val, target_chat_id=chat_id, custom_days=days_val, is_giveaway=True)
                        if vpn_key:
                            target_srv = alt_srv
                            break

            if vpn_key:
                success_msg = (
                    f"🎉 <b>ဂုဏ်ယူပါတယ်ခင်ဗျာ! Redeem Code အောင်မြင်စွာ အသုံးပြုပြီးပါပြီ။</b>\n\n"
                    f"👤 <b>အသုံးပြုသူ:</b> {user_name}\n\n"
                    f"📡 <b>Server:</b> Server {target_srv} 🇸🇬\n\n"
                    f"🎟️ <b>ရရှိသော Data GB:</b> {gb_val} GB\n\n"
                    f"⏰ <b>သက်တမ်းကုန်ဆုံးရက်:</b> {expire_date}\n\n"
                    f"🔑 <b>လူကြီးမင်း၏ VPN Key</b>\n\n"
                    f"<code>{vpn_key}</code>\n\n"
                    f"☝️ အပေါ်က Key ကို <b>တစ်ချက်တည်း နှိပ်လိုက်ရုံဖြင့်</b> Auto Copy ကူးသွားပါလိမ့်မယ်ခင်ဗျာ။"
                )
                bot.send_message(chat_id, success_msg, parse_mode="HTML", reply_markup=get_back_inline_keyboard())
                
                clean_name = user_name.strip().lower()
                save_key_mapping(clean_name, chat_id)

                for aid in ADMIN_CHAT_IDS:
                    try:
                        bot.send_message(
                            aid, 
                            f"🎟️ <b>Redeem Code Alert:</b>\n\nCustomer: {user_name} (ID: {chat_id}) သည် Server {target_srv} Code: <code>{matched_code_key}</code> ကို အသုံးပြု၍ {gb_val} GB Key ({days_val} ရက်) ရယူသွားပါပြီခင်ဗျာ။",
                            parse_mode="HTML"
                        )
                    except:
                        pass
                return
            else:
                bot.send_message(chat_id, "❌ Key မွေးရာတွင် အမှားအယွင်း ရှိနေပါသည်။ Admin ထံ ဆက်သွယ်ပေးပါခင်ဗျာ။", reply_markup=get_back_inline_keyboard())
                return
        else:
            bot.send_message(chat_id, "❌ <b>ထည့်သွင်းထားသော Redeem Code မှားယွင်းနေပါသည် (သို့မဟုတ်) အသုံးပြုပြီးသား ဖြစ်နေပါသည်ခင်ဗျာ။</b>", parse_mode="HTML", reply_markup=get_back_inline_keyboard())
            return

    if input_value == "📊 Total Data Usage":
        clear_all_states(chat_id)
        if str(chat_id) not in [str(aid) for aid in ADMIN_CHAT_IDS]:
            bot.reply_to(message, "❌ ခွင့်လွှတ်ပါ၊ ဒီ ခလုတ်သည် Admin သီးသန့် အသုံးပြုနိုင်သော ခလုတ်ဖြစ်ပါသည်။")
            return
        
        bot.send_message(chat_id, "📡 Server 1, 2 & 3 🇸🇬 Data Usage များကို တွက်ချက်နေပါသည်...")
        report_text = get_servers_total_usage()
        bot.send_message(chat_id, report_text, parse_mode="HTML", reply_markup=get_back_inline_keyboard())
        return

    if input_value in ["💰 လစဉ် ဝင်ငွေ", "လစဉ် ဝင်ငွေ"]:
        clear_all_states(chat_id)
        if str(chat_id) not in [str(aid) for aid in ADMIN_CHAT_IDS]:
            bot.reply_to(message, "❌ ခွင့်လွှတ်ပါ၊ ဒီ ခလုတ်သည် Admin သီးသန့် အသုံးပြုနိုင်သော ခလုတ်ဖြစ်ပါသည်။")
            return
        
        bot.send_message(chat_id, "💰 ရောင်းရငွေ စာရင်းများကို အတိအကျ စစ်ဆေးတွက်ချက်နေပါသည်...")
        rev_report = get_monthly_revenue_report()
        bot.send_message(chat_id, rev_report, parse_mode="HTML", reply_markup=get_back_inline_keyboard())
        return

    if input_value in ["🤖 Bot Refresh", "/refresh"]:
        clear_all_states(chat_id)
        refresh_text = (
            "🤖 <b>Bot စနစ်အား Refresh ပြုလုပ်ပြီးပါပြီခင်ဗျာ!</b>\n\n"
            "✨ Update စနစ်သစ်ဖြင့် စတင် အသုံးပြုနိုင်ပါပြီ။"
        )
        bot.send_message(chat_id, refresh_text, parse_mode="HTML", reply_markup=get_main_menu_keyboard(chat_id))
        return

    if str(chat_id) in [str(aid) for aid in ADMIN_CHAT_IDS] and message.reply_to_message:
        reply_caption = message.reply_to_message.caption
        if reply_caption and "User Chat ID:" in reply_caption:
            try:
                target_user_id = re.search(r'User Chat ID:\s*(\d+)', reply_caption).group(1)
                
                success_message = (
                    f"🎉 <b>ငွေလွှဲမှု အောင်မြင်စွာ အတည်ပြုပြီးပါပြီခင်ဗျာ။</b>\n\n"
                    f"🔑 <b>လူကြီးမင်း ဝယ်ယူထားသော VPN Key ကို အောက်တွင် ရယူနိုင်ပါပြီ။</b>\n\n"
                    f"<code>{input_value}</code>\n\n"
                    f"☝️အပေါ်က ကီးကို <b>တစ်ချက်တည်း နှိပ်လိုက်ရုံဖြင့်</b> Auto Copy ကူးသွားပါလိမ့်မယ်ခင်ဗျာ။ V2BOX VPN App ထဲသို့ ထည့်သွင်းအသုံးပြုနိုင်ပါပြီခင်ဗျာ။"
                )
                bot.send_message(target_user_id, success_message, parse_mode="HTML")
                bot.reply_to(message, "✅ Customer ထံသို့ VPN Keyအား အောင်မြင်စွာ ပို့ပေးလိုက်ပါပြီခင်ဗျာ။")
                return
            except Exception as e:
                bot.reply_to(message, f"❌ ကီးပို့ရာတွင် အမှားအယွင်းရှိပါသည်- {str(e)}")
                return

    if input_value.startswith('/'):
        return

    # ⚡️ Data Usage Check (Server 1, 2, 3 အားလုံးစစ်ဆေးခြင်း)
    target_key, bytes_transferred, server_num = fetch_key_from_server(OUTLINE_API_URL_1, input_value)
    if not target_key:
        target_key, bytes_transferred, server_num = fetch_key_from_server(OUTLINE_API_URL_2, input_value)
    if not target_key:
        target_key, bytes_transferred, server_num = fetch_key_from_server(OUTLINE_API_URL_3, input_value)

    if target_key:
        try:
            full_name = target_key.get("name", "HMA User")
            key_id = str(target_key.get("id"))
            
            date_matches = list(re.finditer(r'(\d{1,2})\.(\d{1,2})\.(\d{2,4})', full_name))
            
            display_name = full_name
            date_match_str = None
            for m in re.finditer(r'\d{1,2}\.\d{1,2}\.(\d{4}|\d{2})', full_name):
                date_match_str = m.group(0)

            if date_match_str:
                display_name = display_name.replace(date_match_str, "")
            
            display_name = display_name.replace("[GW]", "").replace("[gw]", "")
            display_name = display_name.split("tg")[0].split("Tg")[0].split("mess")[0].replace("_", " ").strip()
            
            if not display_name:
                display_name = "HMA Customer"
            
            if str(chat_id) not in [str(aid) for aid in ADMIN_CHAT_IDS]:
                clean_mapping_name = display_name.strip().lower()
                save_key_mapping(clean_mapping_name, chat_id)

            if date_match_str:
                try:
                    e_parts = date_match_str.split('.')
                    day = int(e_parts[0])
                    month = int(e_parts[1])
                    year_str = e_parts[2]
                    
                    if len(year_str) == 2:
                        year = int("20" + year_str)
                    else:
                        year = int(year_str)
                        
                    end_date = f"{day}.{month}.{year}"
                    has_date = True
                except:
                    has_date = False
            else:
                has_date = False

            limit_bytes = target_key.get("dataLimit", {}).get("bytes")
            plan_gb_val = bytes_to_gb(limit_bytes) if limit_bytes else 1000
            plan_gb = f"{plan_gb_val} GB" if limit_bytes else "Unlimited"
            
            usage_bytes = bytes_transferred.get(str(key_id), 0)
            usage_gb = bytes_to_gb(usage_bytes)
            
            # 🗃️ ကျန်ရှိသော Data တွက်ချက်ခြင်း
            if limit_bytes:
                rem_gb_val = max(0, round(plan_gb_val - usage_gb, 2))
                rem_gb_str = f"{rem_gb_val} GB"
            else:
                rem_gb_str = "Unlimited"
            
            order_id_disp = get_order_id_for_key(full_name)
            ord_line = f"🧾 Order ID : <code>{order_id_disp}</code>\n" if order_id_disp != "N/A" else ""

            server_disp = f"Singapore Server {server_num} 🇸🇬"

            if has_date:
                result_text = (
                    f"👤 အသုံးပြုသူ : {display_name}\n\n"
                    f"{ord_line}"
                    f"📡 Server : {server_disp}\n\n"
                    f"🛍️ ဝယ်ယူထားသော Plan : {plan_gb}\n\n"
                    f"🧰 အသုံးပြုပြီးသား Data : {usage_gb} GB\n\n"
                    f"🗃️ ကျန်ရှိသော Data : {rem_gb_str}\n\n"
                    f"⏰ သက်တမ်းကုန်ဆုံးရက်: {end_date}"
                )
            else:
                result_text = (
                    f"👤 အသုံးပြုသူ : {display_name}\n\n"
                    f"{ord_line}"
                    f"📡 Server : {server_disp}\n\n"
                    f"🛍️ ဝယ်ယူထားသော Plan : {plan_gb}\n\n"
                    f"🧰 အသုံးပြုပြီးသား Data : {usage_gb} GB\n\n"
                    f"🗃️ ကျန်ရှိသော Data : {rem_gb_str}"
                )
                
            bot.reply_to(message, result_text, reply_markup=get_back_inline_keyboard())
            return

        except Exception as e:
            bot.reply_to(message, f"❌ ဒေတာတွက်ချက်မှု မှားယွင်းနေပါသည်- {str(e)}")
            return

    not_found_msg = (
        "❌ <b>ခွင့်လွှတ်ပါဗျာ၊ တစ်ခုခုမှားနေပါတယ်ခင်ဗျာ။</b>\n\n"
        "💡 <i> Menu ခလုတ်များ အလုပ်မလုပ်ပါက သို့မဟုတ် Refresh လုပ်လိုပါက အောက်ပါ '🤖 Bot Refresh' ခလုတ် သို့မဟုတ် /start ကို နှိပ်ပေးပါခင်ဗျာ။</i>"
    )
    bot.reply_to(message, not_found_msg, parse_mode="HTML", reply_markup=get_main_menu_keyboard(chat_id))

@app.route('/cron-check', methods=['GET', 'POST'])
def cron_check():
    today = (datetime.utcnow() + timedelta(hours=6, minutes=30)).date()
    
    key_mappings = load_key_mappings()
    notified_count = 0
    deleted_count = 0

    for api_url in [OUTLINE_API_URL_1, OUTLINE_API_URL_2, OUTLINE_API_URL_3]:
        try:
            keys_resp = requests.get(f"{api_url}/access-keys", verify=False, timeout=12)
            metrics_resp = requests.get(f"{api_url}/metrics/transfer", verify=False, timeout=12)
            
            if keys_resp.status_code != 200:
                continue
                
            keys_data = keys_resp.json().get("accessKeys", [])
            bytes_transferred = metrics_resp.json().get("bytesTransferredByUserId", {}) if metrics_resp.status_code == 200 else {}

            for key in keys_data:
                full_name = key.get("name", "")
                key_id = str(key.get("id"))
                limit_bytes = key.get("dataLimit", {}).get("bytes")
                usage_bytes = bytes_transferred.get(key_id, 0)
                
                is_gb_full = False
                if limit_bytes and usage_bytes >= limit_bytes:
                    is_gb_full = True

                is_expired_today = False
                should_delete = False
                
                date_matches = list(re.finditer(r'(\d{1,2})\.(\d{1,2})\.(\d{2,4})', full_name))
                
                if date_matches:
                    date_match = date_matches[-1]
                    try:
                        k_day = int(date_match.group(1))
                        k_month = int(date_match.group(2))
                        k_year_raw = date_match.group(3)
                        k_year = int("20" + k_year_raw) if len(k_year_raw) == 2 else int(k_year_raw)
                        
                        key_expire_date = datetime(k_year, k_month, k_day).date()
                        
                        if key_expire_date == today:
                            is_expired_today = True
                        elif today > key_expire_date:
                            should_delete = True
                    except:
                        pass

                order_id_tag = get_order_id_for_key(full_name)

                if should_delete:
                    try:
                        del_res = requests.delete(f"{api_url}/access-keys/{key_id}", verify=False, timeout=8)
                        if del_res.status_code in [200, 204]:
                            deleted_count += 1
                            ord_txt = f"🧾 <b>Order ID:</b> <code>{order_id_tag}</code>\n" if order_id_tag != "N/A" else ""
                            for aid in ADMIN_CHAT_IDS:
                                try:
                                    bot.send_message(
                                        aid, 
                                        f"🗑️ <b>Auto Delete Alert:</b>\n\n{ord_txt}Key: <code>{full_name}</code> သည် သက်တမ်းကုန်ဆုံးပြီး ၁ ရက်ကျော်လွန်သွားပါသဖြင့် Server ပေါ်မှ အလိုအလျောက် ဖျက်ဆီးလိုက်ပါပြီခင်ဗျာ။", 
                                        parse_mode="HTML"
                                    )
                                except:
                                    pass
                    except:
                        pass
                    continue 

                if is_gb_full or is_expired_today:
                    target_chat_id = None
                    
                    id_match = re.search(r'\((\d+)\)', full_name)
                    if id_match:
                        target_chat_id = id_match.group(1)
                    
                    if not target_chat_id:
                        clean_name = full_name
                        if date_matches:
                            clean_name = clean_name.replace(date_matches[-1].group(0), "")
                        clean_name = re.sub(r'\b(tg|viber|mess|fb)\b', '', clean_name, flags=re.IGNORECASE)
                        clean_name = clean_name.replace("[GW]", "").replace("[gw]", "")
                        clean_name = clean_name.strip().lower()

                        target_chat_id = key_mappings.get(clean_name)
                        if not target_chat_id:
                            for mapped_name, cid in key_mappings.items():
                                if mapped_name in clean_name or clean_name in mapped_name:
                                    target_chat_id = cid
                                    break

                    if is_gb_full:
                        reason_text = "ဝယ်ယူထားသော Data GB ပြည့်သွားပါပြီ"
                        user_warning = "ဝယ်ယူထားသော Data GB ပြည့်သွားပါပြီ ခင်ဗျာ။"
                    else:
                        reason_text = "ယနေ့ သက်တမ်းကုန်ဆုံးပါပြီ"
                        user_warning = "ယနေ့ သက်တမ်းကုန်ဆုံးပါပြီ ခင်ဗျာ။ (မနက်ဖြန်တွင် အသုံးပြုခွင့် ပိတ်သိမ်းပါမည်)"

                    if target_chat_id:
                        try:
                            ord_txt = f"🧾 <b>Order ID:</b> <code>{order_id_tag}</code>\n" if order_id_tag != "N/A" else ""
                            user_noti = (
                                f"⚠️ <b>သတိပေးချက်:</b>\n\n"
                                f"{ord_txt}"
                                f"လူကြီးမင်း အသုံးပြုနေသော VPN Key ({full_name}) သည် <b>{user_warning}</b>\n\n"
                                f"ဆက်လက် အသုံးပြုလိုပါက Bot ၏ '🛍️ Plan များ ကြည့်ရန်' မှတစ်ဆင့် ပြန်လည် ဝယ်ယူနိုင်ပါတယ်ဗျာ။ 🙏"
                            )
                            bot.send_message(target_chat_id, user_noti, parse_mode="HTML")
                            notified_count += 1
                        except:
                            pass

                    admin_noti = (
                        f"📢 <b>Notification Alert</b>\n\n"
                        f"{f'🧾 <b>Order ID:</b>{order_id_tag}' + chr(10) if order_id_tag != 'N/A' else ''}"
                        f"👤 အသုံးပြုသူ: {full_name}\n\n"
                        f"⚠️ အခြေအနေ: {reason_text}\n\n"
                        f"🆔 User ID: {target_chat_id if target_chat_id else 'မသိရှိပါ'}"
                    )
                    
                    for aid in ADMIN_CHAT_IDS:
                        try:
                            bot.send_message(aid, admin_noti, parse_mode="HTML")
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
