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

# 🌐 API Server ၁ နှင့် ၂ လင့်ခ်များ
OUTLINE_API_URL_1 = "https://h.e.feature.hma.qzz.io:49429/YkDBSn3KwUaICBvzDQtvxQ"
OUTLINE_API_URL_2 = "https://104.207.77.147:5714/UrZDutqOIvK931jb3x7hLA"

# 🔑 Admin Telegram Chat ID
ADMIN_CHAT_ID = "8778394176"  

bot = telebot.TeleBot(TELEGRAM_TOKEN, threaded=False)
requests.packages.urllib3.disable_warnings()

# Temp Files ဖြင့် Plan, Key Map, Redeem Code, Sales History နှင့် State များ သိမ်းဆည်းသည့်စနစ်
STATE_FILE = "/tmp/user_plans.json"
MAPPING_FILE = "/tmp/key_mappings.json"
REDEEM_FILE = "/tmp/redeem_codes.json"
USED_REDEEMERS_FILE = "/tmp/used_redeemers.json"
SEARCH_STATE_FILE = "/tmp/admin_search_state.json"
REDEEM_STATE_FILE = "/tmp/user_redeem_state.json"
REPLY_STATE_FILE = "/tmp/admin_reply_target.json"
SALES_FILE = "/tmp/sales_history.json"

def load_user_plans():
    if os.path.exists(STATE_FILE):
        try:
            with open(STATE_FILE, 'r') as f:
                return json.load(f)
        except:
            return {}
    return {}

def save_user_plan(chat_id, plan_data):
    plans = load_user_plans()
    plans[str(chat_id)] = plan_data
    try:
        with open(STATE_FILE, 'w') as f:
            json.dump(plans, f)
    except:
        pass

def load_key_mappings():
    if os.path.exists(MAPPING_FILE):
        try:
            with open(MAPPING_FILE, 'r') as f:
                return json.load(f)
        except:
            return {}
    return {}

def save_key_mapping(clean_name, chat_id):
    mappings = load_key_mappings()
    mappings[clean_name.strip().lower()] = str(chat_id)
    try:
        with open(MAPPING_FILE, 'w') as f:
            json.dump(mappings, f)
    except:
        pass

# 💵 ရောင်းရငွေ သီးသန့် အတိအကျ သိမ်းဆည်းသည့် စနစ်
def load_sales_history():
    if os.path.exists(SALES_FILE):
        try:
            with open(SALES_FILE, 'r') as f:
                return json.load(f)
        except:
            return []
    return []

def save_sale_transaction(server_num, chat_id, plan_code, plan_name, months_count, price_int):
    sales = load_sales_history()
    now = datetime.now()
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
        "price": price_int
    }
    sales.append(sale_data)
    try:
        with open(SALES_FILE, 'w') as f:
            json.dump(sales, f)
    except:
        pass

def set_reply_target(admin_chat_id, target_chat_id):
    try:
        states = {}
        if os.path.exists(REPLY_STATE_FILE):
            with open(REPLY_STATE_FILE, 'r') as f:
                states = json.load(f)
        states[str(admin_chat_id)] = str(target_chat_id)
        with open(REPLY_STATE_FILE, 'w') as f:
            json.dump(states, f)
    except:
        pass

def get_reply_target(admin_chat_id):
    if os.path.exists(REPLY_STATE_FILE):
        try:
            with open(REPLY_STATE_FILE, 'r') as f:
                states = json.load(f)
                return states.get(str(admin_chat_id), None)
        except:
            return None
    return None

# 🎁 Redeem Code သိမ်းဆည်း/ခေါ်ယူသည့် စနစ်
def load_redeem_codes():
    if os.path.exists(REDEEM_FILE):
        try:
            with open(REDEEM_FILE, 'r') as f:
                return json.load(f)
        except:
            return {}
    return {}

def save_redeem_codes(codes):
    try:
        with open(REDEEM_FILE, 'w') as f:
            json.dump(codes, f)
    except:
        pass

# 🛑 Redeem Code အသုံးပြုပြီးသား User ID များအား မှတ်သားသည့် စနစ်
def load_used_redeemers():
    if os.path.exists(USED_REDEEMERS_FILE):
        try:
            with open(USED_REDEEMERS_FILE, 'r') as f:
                return json.load(f)
        except:
            return []
    return []

def save_used_redeemer(chat_id):
    used_list = load_used_redeemers()
    if str(chat_id) not in used_list:
        used_list.append(str(chat_id))
        try:
            with open(USED_REDEEMERS_FILE, 'w') as f:
                json.dump(used_list, f)
        except:
            pass

# 🛑 User တစ်ဦးတွင် Active ဖြစ်နေသော Giveaway Key ရှိမရှိ စစ်ဆေးသည့် Function
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

# 🔍 Admin Search State
def set_search_state(chat_id, is_searching=True):
    try:
        states = {}
        if os.path.exists(SEARCH_STATE_FILE):
            with open(SEARCH_STATE_FILE, 'r') as f:
                states = json.load(f)
        states[str(chat_id)] = is_searching
        with open(SEARCH_STATE_FILE, 'w') as f:
            json.dump(states, f)
    except:
        pass

def get_search_state(chat_id):
    if os.path.exists(SEARCH_STATE_FILE):
        try:
            with open(SEARCH_STATE_FILE, 'r') as f:
                states = json.load(f)
                return states.get(str(chat_id), False)
        except:
            return False
    return False

# 🎁 User Redeem State
def set_redeem_state(chat_id, is_waiting=True):
    try:
        states = {}
        if os.path.exists(REDEEM_STATE_FILE):
            with open(REDEEM_STATE_FILE, 'r') as f:
                states = json.load(f)
        states[str(chat_id)] = is_waiting
        with open(REDEEM_STATE_FILE, 'w') as f:
            json.dump(states, f)
    except:
        pass

def get_redeem_state(chat_id):
    if os.path.exists(REDEEM_STATE_FILE):
        try:
            with open(REDEEM_STATE_FILE, 'r') as f:
                states = json.load(f)
                return states.get(str(chat_id), False)
        except:
            return False
    return False

# 📢 Force Join Verification Helper Functions
def is_user_subscribed(user_id):
    if str(user_id) == str(ADMIN_CHAT_ID):
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

# 🔄 Main Menu Keyboard (💰 လစဉ် ဝင်ငွေ ခလုတ် ပါဝင်သည်)
def get_main_menu_keyboard(chat_id=None):
    markup = ReplyKeyboardMarkup(resize_keyboard=True, row_width=2)
    btn_buy = KeyboardButton("💳 Plan များ ကြည့်ရန်")
    btn_check = KeyboardButton("⚡️ Data Usage စစ်ရန်")
    btn_free = KeyboardButton("🎁 Public Free Key")
    btn_redeem = KeyboardButton("🎁 Redeem Code")
    btn_admin = KeyboardButton("👨‍💻 Admin သို့ ဆက်သွယ်ရန်")
    btn_refresh = KeyboardButton("🔄 Bot Refresh")
    
    markup.add(btn_buy, btn_check)
    markup.add(btn_refresh)
    markup.add(btn_free, btn_redeem)
    markup.add(btn_admin)
    
    if chat_id and str(chat_id) == str(ADMIN_CHAT_ID):
        btn_total_usage = KeyboardButton("📊 Total Data Usage")
        btn_monthly_income = KeyboardButton("💰 လစဉ် ဝင်ငွေ")
        btn_gen_code = KeyboardButton("🎁 Gen RD Code")
        btn_search_user = KeyboardButton("🔍 Cus ရှာရန်")
        markup.add(btn_total_usage, btn_gen_code)
        markup.add(btn_monthly_income, btn_search_user)
        
    return markup

def get_plan_keyboard():
    markup = InlineKeyboardMarkup()
    markup.row(InlineKeyboardButton("🌟 Starter (25 GB)", callback_data="selectplan_starter"))
    markup.row(InlineKeyboardButton("💎 Basic (50 GB)", callback_data="selectplan_basic"))
    markup.row(InlineKeyboardButton("⚡ Standard (75 GB)", callback_data="selectplan_standard"))
    markup.row(InlineKeyboardButton("🔥 Premium (100 GB)", callback_data="selectplan_premium"))
    markup.row(InlineKeyboardButton("👑 VIP (150 GB)", callback_data="selectplan_vip"))
    markup.row(InlineKeyboardButton("🚀 Pro (200 GB)", callback_data="selectplan_pro"))
    markup.row(InlineKeyboardButton("🌌 Ultimate VIP - Unlimited (1000 GB/လစဉ်)", callback_data="selectplan_ultimate"))
    return markup

# 📅 Plan အတွက် သက်တမ်း (၁ လ၊ ၂ လ၊ ၃ လ) ရွေးချယ်သည့် Keyboard
def get_duration_keyboard(plan_code):
    plan = PLANS.get(plan_code)
    base_price = plan["price"]
    
    # Discount တွက်ချက်ခြင်း (၂ လ = 5% off, ၃ လ = 10% off)
    price_1m = base_price
    price_2m = int(base_price * 2 * 0.95)
    price_3m = int(base_price * 3 * 0.90)

    markup = InlineKeyboardMarkup()
    if plan_code == "ultimate":
        markup.row(InlineKeyboardButton(f"📅 1 လ (1000 GB) - {price_1m:,} Ks", callback_data=f"buy_{plan_code}_1"))
        markup.row(InlineKeyboardButton(f"📅 2 လ (2000 GB) - {price_2m:,} Ks (5% Off 🔥)", callback_data=f"buy_{plan_code}_2"))
        markup.row(InlineKeyboardButton(f"📅 3 လ (3000 GB) - {price_3m:,} Ks (10% Off 🌟)", callback_data=f"buy_{plan_code}_3"))
    else:
        markup.row(InlineKeyboardButton(f"📅 1 လ - {price_1m:,} Ks", callback_data=f"buy_{plan_code}_1"))
        markup.row(InlineKeyboardButton(f"📅 2 လ - {price_2m:,} Ks (5% Off 🔥)", callback_data=f"buy_{plan_code}_2"))
        markup.row(InlineKeyboardButton(f"📅 3 လ - {price_3m:,} Ks (10% Off 🌟)", callback_data=f"buy_{plan_code}_3"))
    return markup

# 🎁 Admin အတွက် GB ရွေးချယ်သည့် Keyboard
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
    return markup

# 🎁 Admin အတွက် သက်တမ်း (ရက်) ရွေးချယ်သည့် Keyboard
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
    return markup

# 🎁 Admin အတွက် အရေအတွက် ရွေးချယ်သည့် Keyboard
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
    return markup

# 💰 လစဉ် ဝင်ငွေ သီးသန့် အတိအကျ တွက်ချက်ပေးသည့် Function
def get_monthly_revenue_report():
    now = datetime.now()
    now_str = now.strftime("%d/%m/%Y (%I:%M %p)")
    current_year = now.year
    current_month = now.month
    today_str = now.strftime("%Y-%m-%d")

    sales_history = load_sales_history()

    s1_keys, s1_rev, s1_today_keys, s1_today_rev = 0, 0, 0, 0
    s2_keys, s2_rev, s2_today_keys, s2_today_rev = 0, 0, 0, 0

    s1_plans = {}
    s2_plans = {}
    today_plans = {}

    for item in sales_history:
        if item.get("year") == current_year and item.get("month") == current_month:
            srv = str(item.get("server", "1"))
            price = item.get("price", 0)
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
            else:
                s2_keys += 1
                s2_rev += price
                s2_plans[p_key_str] = s2_plans.get(p_key_str, 0) + 1
                if is_today:
                    s2_today_keys += 1
                    s2_today_rev += price

    total_keys = s1_keys + s2_keys
    total_rev = s1_rev + s2_rev
    today_keys = s1_today_keys + s2_today_keys
    today_rev = s1_today_rev + s2_today_rev

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
        f"━━━━━━━━━━━━━━━━━\n"
        f"🌐 <b>Total This Month Paid Keys:</b> <b>{total_keys} ခု</b>\n"
        f"💎 <b>ဒီလ စုစုပေါင်း ဝင်ငွေ:</b> <b>{total_rev:,} MMK</b>\n\n"
        f"<i>* မှတ်ချက်: မည်သည့် Discount စျေးနှုန်းမဆို ငွေလွှဲခဲ့သည့် အမှန်တကယ် ပမာဏအတိုင်း အတိအကျ ပေါင်းစပ်ထားပါသည်ခင်ဗျာ။</i>"
    )
    return report

# 📊 Server 1 နှင့် Server 2 Total Data Usage တွက်ချက်ပေးသည့် Function
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

    s1_gb = bytes_to_gb(s1_bytes)
    s2_gb = bytes_to_gb(s2_bytes)
    
    overall_bytes = s1_bytes + s2_bytes
    overall_gb = bytes_to_gb(overall_bytes)
    overall_tb = round(overall_gb / 1000, 2)

    report = (
        f"📊 <b>SERVER DATA STATS REPORT</b>\n\n"
        f"📡 <b>Server 1 🇸🇬</b>\n"
        f"🔑 Total Keys: <b>{s1_total}</b>\n"
        f"⚡️ Total Usage: <b>{s1_gb} GB</b>\n\n"
        f"📡 <b>Server 2 🇸🇬</b>\n"
        f"🔑 Total Keys: <b>{s2_total}</b>\n"
        f"⚡️ Total Usage: <b>{s2_gb} GB</b>\n"
        f"━━━━━━━━━━━━━━━━━\n"
        f"🌟 <b>Overall Total Usage:</b> <b>{overall_gb} GB (~{overall_tb} TB)</b>"
    )
    return report

# 🔍 User နာမည်အစ (Initial Letter e.g., 'H', 'T', 'A') ဖြင့် ရှာဖွေပေးသည့် Function
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
        btn_text = f"{srv_icon} | {k_name}"
        markup.add(InlineKeyboardButton(btn_text, callback_data=f"viewkey_{server_num}_{key_id}"))

    return found_matches, markup

# 🔑 ရွေးချယ်ထားသော User ၏ အသေးစိတ် အချက်အလက် ထုတ်ပြသည့် Callback Handler
@bot.callback_query_handler(func=lambda call: call.data.startswith("viewkey_"))
def handle_view_key_detail(call):
    if str(call.message.chat.id) != str(ADMIN_CHAT_ID):
        bot.answer_callback_query(call.id, "❌ Admin သီးသန့်ဖြစ်ပါသည်။")
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
                
                detail_msg = (
                    f"👤 <b>Customer Information✅ </b>\n\n"
                    f"🤖 <b>Name:</b> {html.escape(full_name)}\n"
                    f"📡 <b>Server:</b> {server_name}\n"
                    f"⚡️ <b>Data Usage :</b> <code>{usage_gb} GB</code> / <code>{plan_gb}</code>\n"
                    f"⏰ <b>Expired Date:</b> {end_date}\n"
                    f"🔑 <b>VPN Key Link:</b>\n\n"
                    f"<code>{final_key}</code>"
                )
                bot.send_message(call.message.chat.id, detail_msg, parse_mode="HTML")
                bot.answer_callback_query(call.id)
                return
    except Exception as e:
        bot.send_message(call.message.chat.id, f"❌ Error: {str(e)}")
        bot.answer_callback_query(call.id)

# 🔍 Customer ဝယ်ယူထားသော Key အရေအတွက် စစ်ပေးသည့် Function
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

# 🔄 Unlimited Key တစ်ခုတည်းအတွက် သက်တမ်းတိုးပေးသည့် Function (Used Data + 1000 GB FUP စနစ်ပါဝင်သည်)
def renew_or_create_unlimited_key(server_num, user_name, target_chat_id, months_count=1):
    api_url = OUTLINE_API_URL_1 if str(server_num) == "1" else OUTLINE_API_URL_2
    today = datetime.now()
    new_expire_date = (today + relativedelta(months=months_count)).strftime("%d.%m.%Y")
    add_bytes = (1000 * months_count) * 1000**3  # တိုးပေးမည့် Data (1000 GB x လ)
    
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
                # ⚡️ လက်ရှိ သုံးထားပြီးသား Data ကို ယူပြီး +1000 GB ပေါင်းပေးမည်
                used_bytes = bytes_transferred.get(str(target_key_id), 0)
                new_fup_limit = used_bytes + add_bytes

                updated_name = re.sub(r'\d{1,2}\.\d{1,2}\.(\d{4}|\d{2})$', new_expire_date, target_key_name)
                if updated_name == target_key_name:
                    updated_name = f"{target_key_name.split('(')[0].strip()} ({target_chat_id}) {new_expire_date}"
                
                # Name နှင့် Data Limit သစ် ပြင်ဆင်မည်
                requests.put(f"{api_url}/access-keys/{target_key_id}/name", data={"name": updated_name}, verify=False, timeout=8)
                requests.put(f"{api_url}/access-keys/{target_key_id}/data-limit", json={"limit": {"bytes": new_fup_limit}}, verify=False, timeout=8)
                
                raw_access_url = k.get("accessUrl", "")
                final_key = f"{raw_access_url}#{updated_name}"
                return final_key, updated_name, new_expire_date, True
    except Exception as e:
        print("Unlimited Renewal Error:", e)

    # ကီးအသစ်မွေးလျှင် 1000 GB Limit ဖြင့် စတင်မည်
    vpn_key, key_name, expire_date = create_outline_key(server_num, user_name, plan_info={"bytes": add_bytes}, target_chat_id=target_chat_id, months_count=months_count, is_giveaway=False)
    return vpn_key, key_name, expire_date, False

# ⚡ Key အသစ် မွေးပေးသည့် Function (GB Plan များအတွက် အမြဲတမ်း ကီးအသစ် ထွက်ပါမည်)
def create_outline_key(server_num, user_name, plan_info=None, custom_gb=None, target_chat_id=None, custom_days=None, months_count=1, is_giveaway=False):
    today = datetime.now()
    if custom_days:
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
                limit_bytes = custom_gb * 1000**3
            elif plan_info:
                limit_bytes = plan_info.get("bytes")

            if limit_bytes:
                requests.put(f"{api_url}/access-keys/{key_id}/data-limit", json={"limit": {"bytes": limit_bytes}}, verify=False, timeout=8)
            
            raw_access_url = key_data.get("accessUrl", "")
            final_key = f"{raw_access_url}#{key_name}"
            return final_key, key_name, expire_date
    except Exception as e:
        print("Key Generation Error:", e)
    return None, None, None

# 🎁 Admin GB ရွေးချယ်မှု Callback
@bot.callback_query_handler(func=lambda call: call.data.startswith("adm_gb_"))
def handle_admin_gb_select(call):
    if str(call.message.chat.id) != str(ADMIN_CHAT_ID):
        bot.answer_callback_query(call.id, "❌ Admin သီးသန့်ဖြစ်ပါသည်။")
        return
    
    gb = call.data.replace("adm_gb_", "")
    bot.edit_message_text(
        f"🎁 <b>{gb} GB</b> အတွက် သက်တမ်း (ရက်) ရွေးချယ်ပေးပါခင်ဗျာ:",
        chat_id=ADMIN_CHAT_ID,
        message_id=call.message.message_id,
        parse_mode="HTML",
        reply_markup=get_admin_days_keyboard(gb)
    )
    bot.answer_callback_query(call.id)

# 🎁 Admin သက်တမ်း (ရက်) ရွေးချယ်မှု Callback
@bot.callback_query_handler(func=lambda call: call.data.startswith("adm_dur_"))
def handle_admin_days_select(call):
    if str(call.message.chat.id) != str(ADMIN_CHAT_ID):
        bot.answer_callback_query(call.id, "❌ Admin သီးသန့်ဖြစ်ပါသည်။")
        return
    
    parts = call.data.split("_")
    gb = parts[2]
    days = parts[3]
    
    bot.edit_message_text(
        f"🎁 <b>{gb} GB ({days} ရက်)</b> အတွက် မည်မျှအရေအတွက် Code ထုတ်ယူလိုပါသလဲ?",
        chat_id=ADMIN_CHAT_ID,
        message_id=call.message.message_id,
        parse_mode="HTML",
        reply_markup=get_admin_count_keyboard(gb, days)
    )
    bot.answer_callback_query(call.id)

# 🎁 Admin Code မွေးထုတ်ပေးမှု Callback
@bot.callback_query_handler(func=lambda call: call.data.startswith("adm_cnt_"))
def handle_admin_code_generate(call):
    if str(call.message.chat.id) != str(ADMIN_CHAT_ID):
        bot.answer_callback_query(call.id, "❌ Admin သီးသန့်ဖြစ်ပါသည်။")
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
    bot.edit_message_text(reply_msg, chat_id=ADMIN_CHAT_ID, message_id=call.message.message_id, parse_mode="HTML")
    bot.answer_callback_query(call.id, "✅ Code များထုတ်ပြီးပါပြီ!")

# ✉️ Admin မှ "ဤ Cus ထံ စာပို့ရန်" ခလုတ်ကို နှိပ်လိုက်သောအခါ
@bot.callback_query_handler(func=lambda call: call.data.startswith("reply_cus_"))
def handle_reply_cus_callback(call):
    if str(call.message.chat.id) != str(ADMIN_CHAT_ID):
        bot.answer_callback_query(call.id, "❌ Admin သီးသန့်ဖြစ်ပါသည်။")
        return
        
    target_id = call.data.replace("reply_cus_", "")
    set_reply_target(ADMIN_CHAT_ID, target_id)
    
    bot.answer_callback_query(call.id, "✍️ အဆင်သင့်ဖြစ်ပါပြီ။ ဤ Cus ထံ ပို့လိုသော စာကို ဒီ Chat ထဲသို့ ရိုက်ပို့ပေးပါဗျာ။")
    bot.send_message(
        ADMIN_CHAT_ID, 
        f"📩 <b>Target Customer ID: <code>{target_id}</code></b>\n\n👇 ဤသူ့ထံ ပို့လိုသော စာသား (သို့မဟုတ်) ကြော်ငြာကို ဆက်လက် ရိုက်ပို့ပေးပါခင်ဗျာ:", 
        parse_mode="HTML"
    )

# 📢 Force Join Verification Callback Handler
@bot.callback_query_handler(func=lambda call: call.data == "verify_subscription")
def handle_verify_subscription(call):
    chat_id = call.message.chat.id
    if is_user_subscribed(chat_id):
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

# /start Command
@bot.message_handler(commands=['start'])
def send_welcome(message):
    chat_id = message.chat.id
    set_search_state(chat_id, False)
    set_redeem_state(chat_id, False)

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

# /buy Command
@bot.message_handler(commands=['buy'])
def send_plans(message):
    chat_id = message.chat.id
    if not is_user_subscribed(chat_id):
        send_force_join_message(chat_id)
        return

    set_search_state(chat_id, False)
    set_redeem_state(chat_id, False)
    bot.reply_to(message, "🧸 ကျေးဇူးပြု၍ ဝယ်ယူလိုသော VPN Plan ကို ရွေးချယ်ပေးပါခင်ဗျာ:", reply_markup=get_plan_keyboard())

# 📌 Plan အလိုက် သက်တမ်း ရွေးချယ်ခိုင်းသည့် Callback Handler
@bot.callback_query_handler(func=lambda call: call.data.startswith("selectplan_"))
def handle_select_plan(call):
    chat_id = call.message.chat.id
    if not is_user_subscribed(chat_id):
        send_force_join_message(chat_id)
        return

    plan_code = call.data.replace("selectplan_", "")
    plan = PLANS.get(plan_code)
    
    if plan:
        bot.edit_message_text(
            f"📌 <b>{plan['name']} ({plan['data']})</b>\n\n"
            f"👇 ကျေးဇူးပြု၍ ဝယ်ယူလိုသော <b>သက်တမ်း (Duration)</b> ကို ရွေးချယ်ပေးပါခင်ဗျာ:\n"
            f"<i>(၂ လ သို့မဟုတ် ၃ လ ဝယ်ယူပါက Discount ပရိုမိုးရှင်း ရရှိပါမည်)</i>",
            chat_id=chat_id,
            message_id=call.message.message_id,
            parse_mode="HTML",
            reply_markup=get_duration_keyboard(plan_code)
        )
    bot.answer_callback_query(call.id)

# 💳 Plan + Duration ရွေးပြီး ပေးချေရန် လမ်းညွှန်မှု ပြသပေးသည့် Callback
@bot.callback_query_handler(func=lambda call: call.data.startswith("buy_"))
def handle_buy_callback(call):
    chat_id = call.message.chat.id
    if not is_user_subscribed(chat_id):
        send_force_join_message(chat_id)
        return

    parts = call.data.split("_")
    plan_code = parts[1]
    months_count = int(parts[2]) if len(parts) > 2 else 1
    
    plan = PLANS.get(plan_code)
    
    if plan:
        base_price = plan["price"]
        if months_count == 1:
            total_price = base_price
            data_disp = plan['data']
        elif months_count == 2:
            total_price = int(base_price * 2 * 0.95)
            data_disp = "2000 GB" if plan_code == "ultimate" else plan['data']
        elif months_count == 3:
            total_price = int(base_price * 3 * 0.90)
            data_disp = "3000 GB" if plan_code == "ultimate" else plan['data']

        plan_data = {
            "code": plan_code,
            "name": plan["name"],
            "data": data_disp,
            "months": months_count,
            "price_str": f"{total_price:,} Ks",
            "price_int": total_price
        }
        
        save_user_plan(chat_id, plan_data)
        
        payment_text = (
            f"✅ သင်ရွေးချယ်ထားသော Plan:\n"
            f"📌 {plan['name']} ({data_disp}) - {months_count} လစာ ({total_price:,} Ks)\n\n"
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
        bot.send_message(chat_id, payment_text)
        bot.answer_callback_query(call.id)

# Admin Server 1 / Server 2 Approve Callback Handler
@bot.callback_query_handler(func=lambda call: call.data.startswith("approve_srv"))
def handle_approve_callback(call):
    if str(call.message.chat.id) != str(ADMIN_CHAT_ID):
        bot.answer_callback_query(call.id, "❌ Admin သီးသန့် အသုံးပြုနိုင်သော ခလုတ်ဖြစ်ပါသည်။")
        return
        
    try:
        parts = call.data.split("_")
        server_num = "1" if parts[1] == "srv1" else "2"
        target_chat_id = parts[2]
        plan_code = parts[3]
        months_count = int(parts[4]) if len(parts) > 4 else 1
        
        plan_info = PLANS.get(plan_code, PLANS["starter"])
        
        user_plans = load_user_plans()
        u_plan = user_plans.get(str(target_chat_id), {})
        price_int = u_plan.get("price_int")
        
        if not price_int:
            base_p = plan_info["price"]
            if months_count == 1: price_int = base_p
            elif months_count == 2: price_int = int(base_p * 2 * 0.95)
            elif months_count == 3: price_int = int(base_p * 3 * 0.90)

        chat_info = bot.get_chat(target_chat_id)
        user_first = chat_info.first_name if chat_info.first_name else ""
        user_last = chat_info.last_name if chat_info.last_name else ""
        user_name = f"{user_first} {user_last}".strip()
        if not user_name:
            user_name = "HMA Customer"
        
        # 🌟 Unlimited Plan တစ်ခုတည်းသာ Renew ပြုလုပ်ပြီး၊ ကျန် GB Plan များသည် အမြဲ Key အသစ် မွေးထုတ်မည်
        if plan_code == "ultimate":
            vpn_key, key_name, expire_date, is_renew = renew_or_create_unlimited_key(server_num, user_name, target_chat_id, months_count=months_count)
            if is_renew:
                action_title = "🎉 <b>Unlimited Plan သက်တမ်း အောင်မြင်စွာ တိုးမြှင့်ပြီးပါပြီခင်ဗျာ။</b>"
            else:
                action_title = "🎉 <b>ငွေလွှဲမှု အောင်မြင်စွာ အတည်ပြုပြီးပါပြီခင်ဗျာ။</b>"
            disp_gb = f"{1000 * months_count} GB"
        else:
            vpn_key, key_name, expire_date = create_outline_key(server_num, user_name, plan_info=plan_info, target_chat_id=target_chat_id, months_count=months_count, is_giveaway=False)
            action_title = "🎉 <b>ငွေလွှဲမှု အောင်မြင်စွာ အတည်ပြုပြီးပါပြီခင်ဗျာ။</b>"
            disp_gb = plan_info['data']
        
        if vpn_key:
            save_sale_transaction(server_num, target_chat_id, plan_code, plan_info['name'], months_count, price_int)

            success_message = (
                f"{action_title}\n\n"
                f"👤 <b>ဝယ်ယူသူ:</b> {user_name}\n"
                f"💳 <b>Plan:</b> {plan_info['name']} ({disp_gb}) - {months_count} လစာ\n"
                f"⏰ <b>သက်တမ်းကုန်ဆုံးရက်:</b> {expire_date}\n\n"
                f"🔑 <b>လူကြီးမင်း၏ VPN Key</b>\n\n"
                f"<code>{vpn_key}</code>\n\n"
                f"☝️ အပေါ်က Key  ကို <b>တစ်ချက်တည်း နှိပ်လိုက်ရုံဖြင့်</b> Auto Copy ကူးသွားပါလိမ့်မယ်ခင်ဗျာ။ ကြိုက်နှစ်သက်ရာ VPN App ထဲသို့ ထည့်သွင်းအသုံးပြုနိုင်ပါပြီ။"
            )
            bot.send_message(target_chat_id, success_message, parse_mode="HTML")
            
            clean_name = user_name.strip().lower()
            save_key_mapping(clean_name, target_chat_id)
            
            bot.edit_message_caption(
                chat_id=ADMIN_CHAT_ID,
                message_id=call.message.message_id,
                caption=call.message.caption + f"\n\n✅ <b>DONE (📡 Server {server_num} 🇸🇬)</b>\n\n🔑 {key_name}",
                parse_mode="HTML"
            )
            bot.answer_callback_query(call.id, f"✅ Server {server_num} မှ Key ထုတ်ပြီး Customer ထံ ပို့ပြီးပါပြီ!")
        else:
            bot.answer_callback_query(call.id, f"❌ Server {server_num} မှ Key မွေးရာတွင် အမှားအယွင်း ရှိနေပါသည်။ API စစ်ပါ။", show_alert=True)
    except Exception as e:
        bot.answer_callback_query(call.id, f"❌ Error: {str(e)}", show_alert=True)

# Screenshot Received
@bot.message_handler(content_types=['photo'])
def handle_payment_screenshot(message):
    chat_id = message.chat.id
    if not is_user_subscribed(chat_id):
        send_force_join_message(chat_id)
        return

    set_search_state(chat_id, False)
    set_redeem_state(chat_id, False)
    user_first = message.from_user.first_name if message.from_user.first_name else ""
    user_last = message.from_user.last_name if message.from_user.last_name else ""
    user_name = f"{user_first} {user_last}".strip()
    if not user_name:
        user_name = "HMA User"
        
    username = f"@{message.from_user.username}" if message.from_user.username else "No Username"
    user_plans = load_user_plans()
    
    if str(chat_id) not in user_plans:
        bot.reply_to(message, "⚠️ ခွင့်လွှတ်ပါခင်ဗျာ၊ ကျေးဇူးပြု၍ '💳 Plan များ ကြည့်ရန်' ခလုတ်ကို အရင်နှိပ်ပြီး ဝယ်ယူလိုသော Plan ကို ရွေးချယ်ပေးပါဦးခင်ဗျာ။")
        return

    plan_info = user_plans.get(str(chat_id))
    plan_code = plan_info.get('code', 'starter')
    months_count = plan_info.get('months', 1)
    price_str = plan_info.get('price_str', f"{plan_info.get('price_int', 1000):,} Ks")
    current_date = datetime.fromtimestamp(message.date).strftime("%d/%m/%Y")

    admin_alert_text = (
        f"💰 <b>ငွေလွှဲပြေစာအသစ်</b>\n"
        f"👤 ဝယ်ယူသူနာမည်: {user_name} ({username})\n"
        f"📦 ရွေးချယ်ထားသော Plan: {plan_info['name']} ({plan_info.get('data', '')}) [{months_count} လစာ]\n"
        f"💵 ကျသင့်ငွေပမာဏ: {price_str}\n"
        f"📅 ပေးပို့သည့်ရက်စွဲ: {current_date}\n"
        f"🆔 User Chat ID: {chat_id}"
    )
    
    approve_markup = InlineKeyboardMarkup()
    approve_markup.row(
        InlineKeyboardButton("📡 Server 1 🇸🇬", callback_data=f"approve_srv1_{chat_id}_{plan_code}_{months_count}"),
        InlineKeyboardButton("📡 Server 2 🇸🇬", callback_data=f"approve_srv2_{chat_id}_{plan_code}_{months_count}")
    )
    
    try:
        bot.send_photo(ADMIN_CHAT_ID, message.photo[-1].file_id, caption=admin_alert_text, parse_mode="HTML", reply_markup=approve_markup)
        bot.reply_to(message, "💌 ငွေလွှဲပြေစာအား စစ်ဆေးနေပါသည်။ Admin အတည်ပြုပြီးပါက VPN Key ကို ချက်ချင်းပို့ပေးပါမည်။ ကျေးဇူးတင်ပါသည်ခင်ဗျာ။ 🙏")
    except Exception as e:
        bot.reply_to(message, f"❌ အစ်ကို့ထံ ပို့၍မရပါ - Bot အား အစ်ကို့အကောင့်မှ Start နှိပ်ထားရန် လိုအပ်ပါသည်။")

# Multi-Server Data Checking Function
def fetch_key_from_server(api_url, input_value):
    try:
        keys_resp = requests.get(f"{api_url}/access-keys", verify=False, timeout=8)
        metrics_resp = requests.get(f"{api_url}/metrics/transfer", verify=False, timeout=8)
        
        if keys_resp.status_code != 200:
            return None, None
            
        keys_data = keys_resp.json().get("accessKeys", [])
        bytes_transferred = metrics_resp.json().get("bytesTransferredByUserId", {})
        
        target_key = None

        if "#" in input_value:
            try:
                raw_name = input_value.split("#")[1]
                clean_name = "".join(re.findall(r'[a-zA-Z0-9_\s]', raw_name)).replace("_", " ").strip().lower()
                if clean_name:
                    for key in keys_data:
                        if clean_name in key.get("name", "").lower():
                            target_key = key
                            break
            except:
                pass

        if not target_key and input_value.startswith("ss://"):
            input_clean = clean_ss_url(input_value)
            for key in keys_data:
                server_clean = clean_ss_url(key.get("accessUrl", ""))
                if input_clean and (input_clean in server_clean or server_clean in input_clean):
                    target_key = key
                    break

        if not target_key and re.search(r'^\d+$', input_value):
            match_id = re.search(r'^\d+$', input_value).group(0)
            for key in keys_data:
                if str(key.get("id")) == str(match_id):
                    target_key = key
                    break
                    
        if target_key:
            return target_key, bytes_transferred
    except:
        pass
    return None, None

# Text/Key Handler
@bot.message_handler(func=lambda message: True)
def handle_all_messages(message):
    input_value = message.text.strip()
    chat_id = message.chat.id

    # Force Join Check
    if not is_user_subscribed(chat_id):
        send_force_join_message(chat_id)
        return

    # ✉️ Admin မှ Target ID သတ်မှတ်ပြီး စာပို့ခြင်း (ပထဆုံး စစ်ဆေးရန်)
    if str(chat_id) == str(ADMIN_CHAT_ID):
        current_target = get_reply_target(ADMIN_CHAT_ID)
        if current_target:
            set_reply_target(ADMIN_CHAT_ID, None)  # ပို့ပြီးတာနဲ့ State ပြန်ဖြုတ်မည်
            try:
                bot.send_message(current_target, f"📢 <b>Admin ထံမှ မက်ဆေ့ခ်ျ:</b>\n\n{input_value}", parse_mode="HTML")
                bot.reply_to(message, f"✅ <b>Chat ID ({current_target})</b> ထံသို့ စာ အောင်မြင်စွာ ပို့ပြီးပါပြီခင်ဗျာ!")
            except Exception as e:
                bot.reply_to(message, f"❌ စာပို့၍ မရပါ: {str(e)}")
            return

    if input_value in ["💳 Plan များ ကြည့်ရန်", "Plan များ ကြည့်ရန်", "💳 Plan ကြည့်ရန်"]:
        set_search_state(chat_id, False)
        set_redeem_state(chat_id, False)
        bot.send_message(chat_id, "🧸  လူကြီးမင်း ဝယ်ယူလိုသော VPN Plan ကို ရွေးချယ်ပေးပါခင်ဗျာ:", reply_markup=get_plan_keyboard())
        return
        
    if input_value in ["⚡️ Data Usage စစ်ရန်", "Data Usage စစ်ရန်", "⚡ Data Usage စစ်ရန်"]:
        set_search_state(chat_id, False)
        set_redeem_state(chat_id, False)
        check_guide = (
            "👇 ဝယ်ယူထားသော VPN Key ကို ဒီမှာ Paste ချပေးပါ:\n\n"
            " 🫶 Key ကို Copy ယူလာတဲ့ ss://... နဲ့စတဲ့ Key တစ်ခုလုံးကို ဒီ Chat ထဲသို့ တန်းပြီး Paste ချပို့ပြီး စစ်ဆေးနိုင်ပါတယ်ခင်ဗျာ။"
        )
        bot.send_message(chat_id, check_guide)
        return

    if input_value in ["🎁 Public Free Key", "Public Free Key"]:
        set_search_state(chat_id, False)
        set_redeem_state(chat_id, False)
        free_key = "ss://Y2hhY2hhMjAtaWV0Zi1wb2x5MTMwNTpFQTVIUmNwYW1odkQyNnY5ZnNBNFgw@h.e.feature.hma.qzz.io:443/?outline=1#🚀🌩️ HMA | Thunder Strike ⚡️"
        free_text = (
            f"🎁 <b>H & E FEATURE PREMIUM VPN မှ လူအများအတွက် 1.5TB အထိ အခမဲ့သုံးစွဲနိုင်သော Premium Key ဖြစ်ပါတယ်ခင်ဗျာ။</b>\n\n"
            f"<code>{free_key}</code>\n\n"
            f"☝️ အပေါ်က ကီးလေးကို <b>တစ်ချက်တည်း နှိပ်လိုက်ရုံဖြင့်</b> Auto Copy ကူးသွားပါလိမ့်မယ်ခင်ဗျာ။"
        )
        bot.send_message(chat_id, free_text, parse_mode="HTML")
        return

    if input_value in ["🎁 Redeem Code", "Redeem Code"]:
        set_search_state(chat_id, False)
        
        # 🛑 User တွင် Active ဖြစ်နေသော Giveaway Key ရှိမရှိ စစ်ဆေးခြင်း
        if has_active_giveaway_key(chat_id) and str(chat_id) != str(ADMIN_CHAT_ID):
            bot.send_message(chat_id, "⚠️ <b>ခွင့်လွှတ်ပါခင်ဗျာ၊ လူကြီးမင်းတွင် လက်ရှိ အသုံးပြုနေဆဲ Giveaway Key ရှိနေပါသေးသည်။ အဆိုပါ Key သက်တမ်းကုန်ဆုံးမှသာ Redeem Code အသစ် ပြန်လည် ထုတ်ယူနိုင်ပါမည်ခင်ဗျာ။</b>", parse_mode="HTML")
            return

        set_redeem_state(chat_id, True)
        redeem_guide = (
            "🎁 <b>Giveaway Redeem Code အသုံးပြုရန်:</b>\n\n"
            "👇 Admin ထံမှ ရရှိထားသော Redeem Code (ဥပမာ- <code>H&E-50GB-XXXXXX</code>) ကို ဒီ Chat ထဲသို့ Paste ချပို့ပေးပါခင်ဗျာ။"
        )
        bot.send_message(chat_id, redeem_guide, parse_mode="HTML")
        return

    if input_value in ["👨‍💻 Admin သို့ ဆက်သွယ်ရန်", "Admin သို့ ဆက်သွယ်ရန်"]:
        set_search_state(chat_id, False)
        set_redeem_state(chat_id, False)
        admin_link_markup = InlineKeyboardMarkup()
        admin_link_markup.add(InlineKeyboardButton("💬 စာပို့ရန် နှိပ်ပါ", url="https://t.me/H_M_A_2026"))
        bot.send_message(chat_id, "👇 အောက်ကခလုတ်ကိုနှိပ်ပြီး Admin ထံ တိုက်ရိုက်စာပို့ ဆက်သွယ်နိုင်ပါပြီဗျာ။", reply_markup=admin_link_markup)
        return

    # 🔍 Admin သီးသန့် User နာမည်အစ (Initial Letter) ဖြင့် ရှာဖွေသည့် ခလုတ်
    if input_value == "🔍 Cus ရှာရန်":
        set_redeem_state(chat_id, False)
        if str(chat_id) != str(ADMIN_CHAT_ID):
            bot.reply_to(message, "❌ ခွင့်လွှတ်ပါ၊ ဒီ ခလုတ်သည် Admin သီးသန့် အသုံးပြုနိုင်သော ခလုတ်ဖြစ်ပါသည်။")
            return
        
        set_search_state(chat_id, True)
        bot.send_message(
            chat_id, 
            "🔍 <b>Customer ရှာဖွေရန်:</b>\n\n👇 ရှာဖွေလိုသော <b>Cus နာမည်အစ စာလုံး (ဥပမာ - H, T, A)</b> ကို ဒီ Chat ထဲသို့ ရိုက်ပို့ပေးပါခင်ဗျာ:", 
            parse_mode="HTML"
        )
        return

    # 🎁 Admin သီးသန့် Code Auto Gen ခလုတ်
    if input_value == "🎁 Gen RD Code":
        set_search_state(chat_id, False)
        set_redeem_state(chat_id, False)
        if str(chat_id) != str(ADMIN_CHAT_ID):
            bot.reply_to(message, "❌ ခွင့်လွှတ်ပါ၊ ဒီ ခလုတ်သည် Admin သီးသန့် အသုံးပြုနိုင်သော ခလုတ်ဖြစ်ပါသည်။")
            return
        
        bot.send_message(
            chat_id, 
            "🎁 <b>Giveaway Redeem Code ထုတ်ရန်:</b>\n\nကျေးပြု၍ ဖန်တီးလိုသော <b>GB ပမာဏ</b> ကို ရွေးချယ်ပေးပါခင်ဗျာ:", 
            parse_mode="HTML", 
            reply_markup=get_admin_gb_keyboard()
        )
        return

    # 🔍 Admin Search State ဖြစ်နေပါက နာမည်အစ တိုက်စစ်ပြီး List ထုတ်ပေးခြင်း
    if str(chat_id) == str(ADMIN_CHAT_ID) and get_search_state(chat_id):
        set_search_state(chat_id, False)
        bot.send_message(chat_id, f"⏳ <b>'{input_value}'</b> ဖြင့် စတင်သော Cus များကို 📡 Server 1 & 2 ထဲတွင် ရှာဖွေနေပါသည်...", parse_mode="HTML")
        
        matches, search_markup = search_users_by_query(input_value)
        if matches:
            bot.send_message(
                chat_id, 
                f"🔎 <b>ရှာဖွေတွေ့ရှိသော Customer စာရင်း ({len(matches)} ခု):</b>\n\n👇 အောက်ပါ ခလုတ်များထဲမှ အသေးစိတ်ကြည့်လိုသော Cus ကို နှိပ်ပါ -", 
                parse_mode="HTML", 
                reply_markup=search_markup
            )
        else:
            bot.send_message(chat_id, f"❌ <b>'{input_value}'</b> ဖြင့် စတင်သော User မရှိပါခင်ဗျာ။", parse_mode="HTML")
        return

    # 🎁 Redeem Code စစ်ဆေးသည့် Logic (လက်ရှိ Active Giveaway Key ရှိမရှိ ထပ်မံစစ်ဆေးသည်)
    if get_redeem_state(chat_id):
        set_redeem_state(chat_id, False)
        
        if has_active_giveaway_key(chat_id) and str(chat_id) != str(ADMIN_CHAT_ID):
            bot.send_message(chat_id, "⚠️ <b>ခွင့်လွှတ်ပါခင်ဗျာ၊ လူကြီးမင်းတွင် လက်ရှိ အသုံးပြုနေဆဲ Giveaway Key ရှိနေပါသေးသည်။ အဆိုပါ Key သက်တမ်းကုန်ဆုံးမှသာ Redeem Code အသစ် ပြန်လည် ထုတ်ယူနိုင်ပါမည်ခင်ဗျာ။</b>", parse_mode="HTML")
            return

        codes = load_redeem_codes()
        
        if input_value in codes:
            code_info = codes[input_value]
            if isinstance(code_info, dict):
                gb_val = code_info.get("gb", 25)
                days_val = code_info.get("days", 30)
            else:
                gb_val = int(code_info)
                days_val = 30

            user_name = message.from_user.first_name if message.from_user.first_name else "Giveaway Winner"
            
            del codes[input_value]
            save_redeem_codes(codes)

            bot.send_message(chat_id, "⏳ Redeem Code မှန်ကန်ပါသည်။ VPN Key ကို ထုတ်ပေးနေပါသည်...")
            
            vpn_key, key_name, expire_date = create_outline_key("1", user_name, custom_gb=gb_val, target_chat_id=chat_id, custom_days=days_val, is_giveaway=True)
            if not vpn_key:
                vpn_key, key_name, expire_date = create_outline_key("2", user_name, custom_gb=gb_val, target_chat_id=chat_id, custom_days=days_val, is_giveaway=True)

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
                bot.send_message(chat_id, success_msg, parse_mode="HTML")
                
                clean_name = user_name.strip().lower()
                save_key_mapping(clean_name, chat_id)

                try:
                    bot.send_message(
                        ADMIN_CHAT_ID, 
                        f"🎁 <b>Redeem Code Alert:</b>\n\nCustomer: {user_name} (ID: {chat_id}) သည် Code: <code>{input_value}</code> ကို အသုံးပြု၍ {gb_val} GB Key ({days_val} ရက်) ရယူသွားပါပြီခင်ဗျာ။",
                        parse_mode="HTML"
                    )
                except:
                    pass
                return
            else:
                bot.send_message(chat_id, "❌ Key မွေးရာတွင် အမှားအယွင်း ရှိနေပါသည်။ Admin ထံ ဆက်သွယ်ပေးပါခင်ဗျာ။")
                return
        else:
            bot.send_message(chat_id, "❌ <b>ထည့်သွင်းထားသော Redeem Code မှားယွင်းနေပါသည် (သို့မဟုတ်) အသုံးပြုပြီးသား ဖြစ်နေပါသည်ခင်ဗျာ။</b>", parse_mode="HTML")
            return

    # 📊 Admin သီးသန့် Total Usage ခလုတ်
    if input_value == "📊 Total Data Usage":
        set_search_state(chat_id, False)
        set_redeem_state(chat_id, False)
        if str(chat_id) != str(ADMIN_CHAT_ID):
            bot.reply_to(message, "❌ ခွင့်လွှတ်ပါ၊ ဒီ ခလုတ်သည် Admin သီးသန့် အသုံးပြုနိုင်သော ခလုတ်ဖြစ်ပါသည်။")
            return
        
        bot.send_message(chat_id, "📡 Server 1 & Server 2 🇸🇬 Data Usage များကို တွက်ချက်နေပါသည်...")
        report_text = get_servers_total_usage()
        bot.send_message(chat_id, report_text, parse_mode="HTML")
        return

    # 💰 Admin သီးသန့် လစဉ် ဝင်ငွေ ခလုတ်
    if input_value in ["💰 လစဉ် ဝင်ငွေ", "လစဉ် ဝင်ငွေ"]:
        set_search_state(chat_id, False)
        set_redeem_state(chat_id, False)
        if str(chat_id) != str(ADMIN_CHAT_ID):
            bot.reply_to(message, "❌ ခွင့်လွှတ်ပါ၊ ဒီ ခလုတ်သည် Admin သီးသန့် အသုံးပြုနိုင်သော ခလုတ်ဖြစ်ပါသည်။")
            return
        
        bot.send_message(chat_id, "💰 ရောင်းရငွေ စာရင်းများကို အတိအကျ စစ်ဆေးတွက်ချက်နေပါသည်...")
        rev_report = get_monthly_revenue_report()
        bot.send_message(chat_id, rev_report, parse_mode="HTML")
        return

    # 🔄 Bot Refresh Logic
    if input_value in ["🔄 Bot Refresh", "/refresh"]:
        set_search_state(chat_id, False)
        set_redeem_state(chat_id, False)
        refresh_text = (
            "🔄 <b>Bot စနစ်အား Refresh ပြုလုပ်ပြီးပါပြီခင်ဗျာ!</b>\n\n"
            "✨ Update စနစ်သစ်ဖြင့် စတင် အသုံးပြုနိုင်ပါပြီ။"
        )
        bot.send_message(chat_id, refresh_text, parse_mode="HTML", reply_markup=get_main_menu_keyboard(chat_id))
        return

    # ADMIN MANUAL REPLY BYPASS SYSTEM
    if str(chat_id) == str(ADMIN_CHAT_ID) and message.reply_to_message:
        reply_caption = message.reply_to_message.caption
        if reply_caption and "User Chat ID:" in reply_caption:
            try:
                target_user_id = re.search(r'User Chat ID:\s*(\d+)', reply_caption).group(1)
                
                success_message = (
                    f"🎉 <b>ငွေလွှဲမှု အောင်မြင်စွာ အတည်ပြုပြီးပါပြီခင်ဗျာ။</b>\n\n"
                    f"🔑 <b>လူကြီးမင်း ဝယ်ယူထားသော VPN Key ကို အောက်တွင် ရယူနိုင်ပါပြီ။</b>\n\n"
                    f"<code>{input_value}</code>\n\n"
                    f"☝️အပေါ်က ကီးကို <b>တစ်ချက်တည်း နှိပ်လိုက်ရုံဖြင့်</b> Auto Copy ကူးသွားပါလိမ့်မယ်ခင်ဗျာ။ ကြိုက်နှစ်သက်ရာ VPN App ထဲသို့ ထည့်သွင်းအသုံးပြုနိုင်ပါပြီခင်ဗျာ။"
                )
                bot.send_message(target_user_id, success_message, parse_mode="HTML")
                bot.reply_to(message, "✅ Customer ထံသို့ VPN Keyအား အောင်မြင်စွာ ပို့ပေးလိုက်ပါပြီခင်ဗျာ။")
                return
            except Exception as e:
                bot.reply_to(message, f"❌ ကီးပို့ရာတွင် အမှားအယွင်းရှိပါသည်- {str(e)}")
                return

    if input_value.startswith('/'):
        return

    # Multi-Server Key Usage Checking
    target_key, bytes_transferred = fetch_key_from_server(OUTLINE_API_URL_1, input_value)
    if not target_key:
        target_key, bytes_transferred = fetch_key_from_server(OUTLINE_API_URL_2, input_value)

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
            plan_gb = f"{bytes_to_gb(limit_bytes)} GB" if limit_bytes else "Unlimited"
            usage_bytes = bytes_transferred.get(str(key_id), 0)
            usage_gb = bytes_to_gb(usage_bytes)
            
            if has_date:
                result_text = (
                    f"👤 အသုံးပြုသူ : {display_name}\n"
                    f"💳 ဝယ်ယူထားသော Plan : {plan_gb}\n"
                    f"⚡️ အသုံးပြုပြီးသား Data : {usage_gb} GB\n"
                    f"⏰ သက်တမ်းကုန်ဆုံးရက်: {end_date}"
                )
            else:
                result_text = (
                    f"👤 အသုံးပြုသူ : {display_name}\n"
                    f"💳 ဝယ်ယူထားသော Plan : {plan_gb}\n"
                    f"⚡️ အသုံးပြုပြီးသား Data : {usage_gb} GB"
                )
                
            bot.reply_to(message, result_text)
            return

        except Exception as e:
            bot.reply_to(message, f"❌ ဒေတာတွက်ချက်မှု မှားယွင်းနေပါသည်- {str(e)}")
            return

    # Not Found Noti
    not_found_msg = (
        "❌ <b>ခွင့်လွှတ်ပါဗျာ၊ တစ်ခုခုမှားနေပါတယ်ခင်ဗျာ။</b>\n\n"
        "💡 <i> Menu ခလုတ်များ အလုပ်မလုပ်ပါက သို့မဟုတ် Refresh လုပ်လိုပါက အောက်ပါ '🔄 Bot Refresh' ခလုတ် သို့မဟုတ် /start ကို နှိပ်ပေးပါခင်ဗျာ။</i>"
    )
    bot.reply_to(message, not_found_msg, parse_mode="HTML", reply_markup=get_main_menu_keyboard(chat_id))

# Cron Check Route
@app.route('/cron-check', methods=['GET', 'POST'])
def cron_check():
    today = datetime.now()
    today_date = today.date()
    
    key_mappings = load_key_mappings()
    notified_count = 0
    deleted_count = 0

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
                        
                        if key_expire_date == today_date:
                            is_expired_today = True
                        elif today_date > key_expire_date:
                            should_delete = True
                    except:
                        pass

                if should_delete:
                    try:
                        del_res = requests.delete(f"{api_url}/access-keys/{key_id}", verify=False, timeout=8)
                        if del_res.status_code in [200, 204]:
                            deleted_count += 1
                            try:
                                bot.send_message(
                                    ADMIN_CHAT_ID, 
                                    f"🗑️ <b>Auto Delete Alert:</b>\n\nKey: <code>{full_name}</code> သည် သက်တမ်းကုန်ဆုံးပြီး ၁ ရက်ကျော်လွန်သွားပါသဖြင့် Server ပေါ်မှ အလိုအလျောက် ဖျက်ဆီးလိုက်ပါပြီခင်ဗျာ။", 
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
                            user_noti = (
                                f"⚠️ <b>သတိပေးချက်:</b>\n\n"
                                f"လူကြီးမင်း အသုံးပြုနေသော VPN Key ({full_name}) သည် <b>{user_warning}</b>\n\n"
                                f"ဆက်လက် အသုံးပြုလိုပါက Bot ၏ '💳 Plan များ ကြည့်ရန်' မှတစ်ဆင့် ပြန်လည် ဝယ်ယူနိုင်ပါတယ်ဗျာ။ 🙏"
                            )
                            bot.send_message(target_chat_id, user_noti, parse_mode="HTML")
                            notified_count += 1
                        except:
                            pass

                    try:
                        admin_noti = (
                            f"📢 <b>Notification Alert</b>\n"
                            f"👤 အသုံးပြုသူ: {full_name}\n"
                            f"📌 အခြေအနေ: {reason_text}\n"
                            f"🆔 User ID: {target_chat_id if target_chat_id else 'မသိရှိပါ'}"
                        )
                        admin_btn_markup = InlineKeyboardMarkup()
                        if target_chat_id:
                            admin_btn_markup.add(InlineKeyboardButton("✉️ ဤ Cus ထံ စာပို့ရန်", callback_data=f"reply_cus_{target_chat_id}"))
                            
                        bot.send_message(ADMIN_CHAT_ID, admin_noti, parse_mode="HTML", reply_markup=admin_btn_markup)
                    except:
                        pass
        except:
            pass

    return jsonify({"status": "cron completed", "notified": notified_count, "deleted": deleted_count}), 200

# Catch-all Webhook Route
@app.route('/', defaults={'path': ''}, methods=['POST', 'GET'])
@app.route('/<path:path>', methods=['POST', 'GET'])
def index(path):
    if request.method == 'POST':
        json_string = request.get_data().decode('utf-8')
        update = telebot.types.Update.de_json(json_string)
        bot.process_new_updates([update])
        return jsonify({"status": "ok"}), 200
    return "Bot is running perfectly!", 200