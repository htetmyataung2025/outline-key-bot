import os
import requests
import random
import string
from flask import Flask, request, jsonify
import telebot
from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton, ReplyKeyboardMarkup, KeyboardButton, WebAppInfo
import re
import json
import html
from datetime import datetime, timedelta
from dateutil.relativedelta import relativedelta

app = Flask(__name__)

TELEGRAM_TOKEN = "8779558815:AAEaXF6rRqCVM-PFhbOlwgubSknk5xTiKvU"
REQUIRED_CHANNEL = "@hefeature"
OUTLINE_API_URL_1 = "https://64.120.94.164:49429/YkDBSn3KwUaICBvzDQtvxQ"
OUTLINE_API_URL_2 = "https://104.207.92.135:8443/o8a5SK1XlVXdrgXUX5Z24Q"
OUTLINE_API_URL_3 = "https://vip.h-e-feature.store:33300/E_LfjCh3-9u_jEFyQnZUfA"
ADMIN_CHAT_IDS = ["8778394176", "6297145771"]
OCR_API_KEY = "K87641025188957"
MY_PAYMENT_PHONES = ["09699970092", "9699970092", "699970092"]

bot = telebot.TeleBot(TELEGRAM_TOKEN, threaded=False)
requests.packages.urllib3.disable_warnings()

KV_URL = os.environ.get("KV_REST_API_URL")
KV_TOKEN = os.environ.get("KV_REST_API_TOKEN")

# ========== REDIS HELPERS ==========
def redis_get(key):
    if not KV_URL or not KV_TOKEN: return None
    try:
        res = requests.get(f"{KV_URL}/get/{key}", headers={"Authorization": f"Bearer {KV_TOKEN}"}, timeout=5)
        if res.status_code == 200:
            val = res.json().get("result")
            return json.loads(val) if val else None
    except: pass
    return None

def redis_set(key, value):
    if not KV_URL or not KV_TOKEN: return False
    try:
        val_str = json.dumps(value)
        res = requests.post(f"{KV_URL}/set/{key}", headers={"Authorization": f"Bearer {KV_TOKEN}"}, data=val_str, timeout=5)
        return res.status_code == 200
    except: return False

# ========== STATE MANAGEMENT (OPTIMIZED - 1 REDIS CALL) ==========
def get_all_states():
    return redis_get("global_states") or {}

def save_all_states(states):
    redis_set("global_states", states)

def set_state(chat_id, key, value):
    states = get_all_states()
    cid = str(chat_id)
    if cid not in states:
        states[cid] = {}
    states[cid][key] = value
    save_all_states(states)

def get_state(chat_id, key, default=None):
    states = get_all_states()
    return states.get(str(chat_id), {}).get(key, default)

def clear_all_states(chat_id):
    states = get_all_states()
    states[str(chat_id)] = {}
    save_all_states(states)

PROCESSED_CALLBACKS = set()
def is_callback_processed(key):
    if key in PROCESSED_CALLBACKS: return True
    PROCESSED_CALLBACKS.add(key)
    if len(PROCESSED_CALLBACKS) > 500: PROCESSED_CALLBACKS.clear()
    return False

# ========== WALLET SYSTEM ==========
def load_all_wallets():
    data = redis_get("user_wallets_data")
    return data if data is not None else {}

def load_expiring_credits():
    data = redis_get("user_expiring_credits")
    return data if data is not None else {}

def save_expiring_credits(data):
    redis_set("user_expiring_credits", data)

def load_claimed_redeem_users():
    data = redis_get("global_claimed_redeemers")
    return data if data is not None else []

def save_claimed_redeem_user(chat_id):
    if str(chat_id) in [str(aid) for aid in ADMIN_CHAT_IDS]: return
    users = load_claimed_redeem_users()
    uid = str(chat_id)
    if uid not in users:
        users.append(uid)
        redis_set("global_claimed_redeemers", users)

def get_user_balance_breakdown(chat_id):
    uid = str(chat_id)
    wallets = load_all_wallets()
    main_bal = int(wallets.get(uid, 0))
    expiring_data = load_expiring_credits()
    user_grants = expiring_data.get(uid, [])
    now = datetime.utcnow() + timedelta(hours=6, minutes=30)
    valid_bonus = 0
    clean_grants = []
    for g in user_grants:
        try:
            exp_dt = datetime.strptime(g["expire_at"], "%Y-%m-%d %H:%M:%S")
            if exp_dt > now and g.get("remaining", 0) > 0:
                valid_bonus += int(g["remaining"])
                clean_grants.append(g)
        except: pass
    if len(clean_grants) != len(user_grants):
        expiring_data[uid] = clean_grants
        save_expiring_credits(expiring_data)
    return main_bal, valid_bonus, (main_bal + valid_bonus)

def get_user_balance(chat_id):
    if str(chat_id) in [str(aid) for aid in ADMIN_CHAT_IDS]: return 999999999
    _, _, total_bal = get_user_balance_breakdown(chat_id)
    return total_bal

def update_user_balance(chat_id, amount_delta):
    uid = str(chat_id)
    wallets = load_all_wallets()
    if amount_delta > 0:
        wallets[uid] = int(wallets.get(uid, 0)) + amount_delta
        redis_set("user_wallets_data", wallets)
        return get_user_balance(chat_id), None
    needed_deduct = abs(amount_delta)
    expiring_data = load_expiring_credits()
    user_grants = expiring_data.get(uid, [])
    now = datetime.utcnow() + timedelta(hours=6, minutes=30)
    sorted_grants = []
    for g in user_grants:
        try:
            exp_dt = datetime.strptime(g["expire_at"], "%Y-%m-%d %H:%M:%S")
            if exp_dt > now and g.get("remaining", 0) > 0:
                sorted_grants.append(g)
        except: pass
    sorted_grants.sort(key=lambda x: x["expire_at"])
    used_bonus_days = []
    for g in sorted_grants:
        if needed_deduct <= 0: break
        rem = g.get("remaining", 0)
        if rem <= needed_deduct:
            needed_deduct -= rem
            g["remaining"] = 0
            used_bonus_days.append(g.get("days", 1))
        else:
            g["remaining"] -= needed_deduct
            needed_deduct = 0
            used_bonus_days.append(g.get("days", 1))
    expiring_data[uid] = [g for g in sorted_grants if g.get("remaining", 0) > 0]
    save_expiring_credits(expiring_data)
    if needed_deduct > 0:
        wallets[uid] = max(0, int(wallets.get(uid, 0)) - needed_deduct)
        redis_set("user_wallets_data", wallets)
    min_bonus_days = min(used_bonus_days) if used_bonus_days else None
    return get_user_balance(chat_id), min_bonus_days

def add_expiring_bonus_to_wallet(chat_id, amount, validity_days):
    uid = str(chat_id)
    now = datetime.utcnow() + timedelta(hours=6, minutes=30)
    exp_dt = now + timedelta(days=validity_days)
    expiring_data = load_expiring_credits()
    if uid not in expiring_data: expiring_data[uid] = []
    grant = {
        "amount": int(amount), "remaining": int(amount), "days": int(validity_days),
        "expire_at": exp_dt.strftime("%Y-%m-%d %H:%M:%S"),
        "expire_disp": exp_dt.strftime("%d.%m.%Y")
    }
    expiring_data[uid].append(grant)
    save_expiring_credits(expiring_data)
    save_claimed_redeem_user(chat_id)
    return get_user_balance(chat_id), grant["expire_disp"]

def admin_deduct_specific_funds(target_chat_id, amount_to_deduct, deduct_type="all"):
    uid = str(target_chat_id)
    needed = int(amount_to_deduct)
    deducted = 0
    if deduct_type in ["bonus", "all"]:
        expiring_data = load_expiring_credits()
        user_grants = expiring_data.get(uid, [])
        for g in user_grants:
            if needed <= 0: break
            rem = g.get("remaining", 0)
            if rem <= needed:
                needed -= rem; deducted += rem; g["remaining"] = 0
            else:
                g["remaining"] -= needed; deducted += needed; needed = 0
        expiring_data[uid] = [g for g in user_grants if g.get("remaining", 0) > 0]
        save_expiring_credits(expiring_data)
    if deduct_type in ["main", "all"]:
        if deduct_type == "main": needed = int(amount_to_deduct)
        if needed > 0:
            wallets = load_all_wallets()
            curr = int(wallets.get(uid, 0))
            sub = min(curr, needed)
            wallets[uid] = curr - sub
            deducted += sub
            redis_set("user_wallets_data", wallets)
    m, b, t = get_user_balance_breakdown(uid)
    return deducted, m, b, t

# ========== PERSISTENT STORAGE ==========
def load_persistent_keys():
    return redis_get("persistent_keys_registry") or {}

def save_persistent_key(server_num, key_id, name, access_url, limit_bytes=None, order_id=None, chat_id=None):
    if not key_id or not server_num: return
    registry = load_persistent_keys()
    uid = f"{server_num}_{key_id}"
    date_match = re.search(r'\d{1,2}\.\d{1,2}\.(\d{4}|\d{2})', name)
    exp_date = date_match.group(0) if date_match else "မသိရှိပါ"
    existing = registry.get(uid, {})
    registry[uid] = {
        "server": str(server_num), "key_id": str(key_id), "name": name,
        "access_url": access_url if access_url else existing.get("access_url", ""),
        "limit_bytes": limit_bytes if limit_bytes else existing.get("limit_bytes"),
        "expire_date": exp_date if exp_date != "မသိရှိပါ" else existing.get("expire_date", "မသိရှိပါ"),
        "order_id": order_id if order_id else existing.get("order_id", "N/A"),
        "chat_id": str(chat_id) if chat_id else existing.get("chat_id", "")
    }
    redis_set("persistent_keys_registry", registry)

def sync_keys_to_persistent_registry(server_num, keys_data):
    if not keys_data: return
    registry = load_persistent_keys()
    key_orders_map = load_key_orders()
    for k in keys_data:
        k_id = str(k.get("id"))
        uid = f"{server_num}_{k_id}"
        k_name = k.get("name", "")
        raw_url = k.get("accessUrl", "")
        full_url = f"{raw_url}#{k_name}" if k_name else raw_url
        l_bytes = k.get("dataLimit", {}).get("bytes")
        ord_id = key_orders_map.get(k_name.strip().lower(), "N/A")
        cid_match = re.search(r'\((\d+)\)', k_name)
        cid = cid_match.group(1) if cid_match else ""
        date_match = re.search(r'\d{1,2}\.\d{1,2}\.(\d{4}|\d{2})', k_name)
        exp_date = date_match.group(0) if date_match else "မသိရှိပါ"
        registry[uid] = {
            "server": str(server_num), "key_id": k_id, "name": k_name,
            "access_url": full_url, "limit_bytes": l_bytes,
            "expire_date": exp_date, "order_id": ord_id, "chat_id": cid
        }
    redis_set("persistent_keys_registry", registry)

def load_key_orders():
    return redis_get("key_orders") or {}

def map_key_to_order(key_name, order_id):
    if not order_id or not key_name: return
    data = load_key_orders()
    data[key_name.strip().lower()] = str(order_id)
    redis_set("key_orders", data)

def get_order_id_for_key(key_name):
    data = load_key_orders()
    return data.get(key_name.strip().lower(), "N/A")

def load_sales_history():
    return redis_get("sales_history") or []

def save_sale_transaction(server_num, chat_id, plan_code, plan_name, months_count, price_int, order_id=None):
    sales = load_sales_history()
    now = datetime.utcnow() + timedelta(hours=6, minutes=30)
    sales.append({
        "timestamp": now.strftime("%Y-%m-%d %H:%M:%S"),
        "date": now.strftime("%Y-%m-%d"), "year": now.year, "month": now.month,
        "server": str(server_num), "chat_id": str(chat_id),
        "plan_code": plan_code, "plan_name": plan_name,
        "months": months_count, "price": int(price_int) if price_int else 0,
        "order_id": order_id or "N/A"
    })
    redis_set("sales_history", sales)

def load_all_user_history():
    return redis_get("user_purchases_data") or {}

def save_user_purchase_record(chat_id, order_id, plan_name, disp_gb, months_count, price_str, server_num, expire_date, vpn_key):
    history_data = load_all_user_history()
    uid = str(chat_id)
    if uid not in history_data: history_data[uid] = []
    now = datetime.utcnow() + timedelta(hours=6, minutes=30)
    history_data[uid].append({
        "timestamp": now.strftime("%d/%m/%Y (%I:%M %p)"),
        "order_id": order_id if order_id else "N/A",
        "plan_name": plan_name, "disp_gb": disp_gb, "months": months_count,
        "price_str": price_str, "server": str(server_num),
        "expire_date": expire_date, "vpn_key": vpn_key
    })
    redis_set("user_purchases_data", history_data)

def get_user_combined_purchase_records(chat_id):
    history_data = load_all_user_history()
    records = list(history_data.get(str(chat_id), []))
    known_orders = set(r.get("order_id") for r in records if r.get("order_id") and r.get("order_id") != "N/A")
    sales = load_sales_history()
    user_sales = [s for s in sales if str(s.get("chat_id")) == str(chat_id)]
    persistent_registry = load_persistent_keys()
    for s in user_sales:
        s_ord = s.get("order_id", "N/A")
        if s_ord != "N/A" and s_ord in known_orders: continue
        srv_num = str(s.get("server", "1"))
        matched_link = "N/A"
        exp_found = "မသိရှိပါ"
        for k_data in persistent_registry.values():
            if str(k_data.get("chat_id")) == str(chat_id) and str(k_data.get("server")) == srv_num:
                matched_link = k_data.get("access_url", "N/A")
                exp_found = k_data.get("expire_date", "မသိရှိပါ")
                break
        p_info = PLANS.get(s.get("plan_code"), {})
        records.append({
            "timestamp": s.get("timestamp", s.get("date", "N/A")),
            "order_id": s_ord, "plan_name": s.get("plan_name", "VPN Plan"),
            "disp_gb": p_info.get("data", "N/A"), "months": s.get("months", 1),
            "price_str": f"{s.get('price', 0):,} Ks",
            "server": srv_num, "expire_date": exp_found, "vpn_key": matched_link
        })
        if s_ord != "N/A": known_orders.add(s_ord)
    return records

def load_redeem_codes():
    return redis_get("redeem_codes") or {}

def save_redeem_codes(codes):
    redis_set("redeem_codes", codes)

def save_user_id(chat_id):
    users = redis_get("all_users") or []
    if str(chat_id) not in [str(u) for u in users]:
        users.append(str(chat_id))
        redis_set("all_users", users)

def load_all_users():
    return redis_get("all_users") or []

def load_key_mappings():
    return redis_get("key_mappings") or {}

def save_key_mapping(clean_name, chat_id):
    mappings = load_key_mappings()
    mappings[clean_name.strip().lower()] = str(chat_id)
    redis_set("key_mappings", mappings)

# ========== PLAN CONFIG (CUSTOM REMOVED) ==========
PLANS = {
    "starter":  {"name": "Starter Plan",      "data": "25 GB",  "bytes": 25 * 1000**3,  "price": 1000,  "months": 1},
    "basic":    {"name": "Basic Plan",        "data": "50 GB",  "bytes": 50 * 1000**3,  "price": 2000,  "months": 1},
    "standard": {"name": "Standard Plan",     "data": "75 GB",  "bytes": 75 * 1000**3,  "price": 3000,  "months": 1},
    "premium":  {"name": "Premium Plan",      "data": "100 GB", "bytes": 100 * 1000**3, "price": 4000,  "months": 1},
    "vip":      {"name": "VIP Plan",          "data": "150 GB", "bytes": 150 * 1000**3, "price": 5000,  "months": 1},
    "pro":      {"name": "Pro Plan",          "data": "200 GB", "bytes": 200 * 1000**3, "price": 7000,  "months": 1},
    "ultimate": {"name": "Ultimate VIP Plan", "data": "500 GB", "bytes": 500 * 1000**3, "price": 10000, "months": 1},
}

def bytes_to_gb(b): return round(b / (1000 ** 3), 2)

def clean_ss_url(url_str):
    if not url_str: return ""
    return url_str.replace("ss://", "").split("#")[0].split("?")[0].strip()

# ========== KEYBOARDS ==========
def get_main_menu_keyboard(chat_id=None):
    markup = ReplyKeyboardMarkup(resize_keyboard=True, row_width=2)
    markup.add(KeyboardButton("🛍️ Plan များဝယ်ရန်"), KeyboardButton("💰 ငွေဖြည့်ရန်"))
    markup.add(KeyboardButton("💳 လက်ကျန်ငွေ"), KeyboardButton("📇 ဝယ်ယူမှုမှတ်တမ်း"))
    markup.add(KeyboardButton("🧰 Data ပမာဏစစ်ရန်"), KeyboardButton("♻️ Key လဲရန်"))
    markup.add(KeyboardButton("👨‍💻 Admin ဆက်သွယ်ရန်"), KeyboardButton("🤖 Bot Refresh"))
    if chat_id and str(chat_id) in [str(aid) for aid in ADMIN_CHAT_IDS]:
        markup.add(KeyboardButton("📊 Total Data Usage"), KeyboardButton("🎟️ Gen RD Code"))
        markup.add(KeyboardButton("💰 လစဉ် ဝင်ငွေ"), KeyboardButton("🔍 Cus ရှာရန်"))
        markup.add(KeyboardButton("💸 ငွေနှုတ်ရန်"), KeyboardButton("📢 Broadcast စာပို့ရန်"))
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
    markup.row(InlineKeyboardButton("🌌 Ultimate VIP (500 GB) - 10,000 Ks", callback_data="selectplan_ultimate"))
    markup.row(InlineKeyboardButton("🔙 မူလ Menu သို့ ပြန်သွားရန်", callback_data="back_to_main"))
    return markup

def get_topup_amounts_keyboard():
    markup = InlineKeyboardMarkup()
    markup.row(InlineKeyboardButton("💵 1,000 Ks", callback_data="topup_amt_1000"), InlineKeyboardButton("💵 2,000 Ks", callback_data="topup_amt_2000"))
    markup.row(InlineKeyboardButton("💵 3,000 Ks", callback_data="topup_amt_3000"), InlineKeyboardButton("💵 5,000 Ks", callback_data="topup_amt_5000"))
    markup.row(InlineKeyboardButton("💵 10,000 Ks", callback_data="topup_amt_10000"), InlineKeyboardButton("💵 20,000 Ks", callback_data="topup_amt_20000"))
    markup.row(InlineKeyboardButton("✍️ စိတ်ကြိုက်ပမာဏ ရိုက်ထည့်မည်", callback_data="topup_amt_custom"))
    markup.row(InlineKeyboardButton("🔙 မူလ Menu သို့ ပြန်သွားရန်", callback_data="back_to_main"))
    return markup

def get_admin_rd_amounts_keyboard():
    markup = InlineKeyboardMarkup()
    markup.row(InlineKeyboardButton("💵 1,000 Ks", callback_data="adm_rdamt_1000"), InlineKeyboardButton("💵 3,000 Ks", callback_data="adm_rdamt_3000"))
    markup.row(InlineKeyboardButton("💵 5,000 Ks", callback_data="adm_rdamt_5000"), InlineKeyboardButton("💵 10,000 Ks", callback_data="adm_rdamt_10000"))
    markup.row(InlineKeyboardButton("🔙 မူလ Menu သို့ ပြန်သွားရန်", callback_data="back_to_main"))
    return markup

def get_admin_rd_mode_keyboard(amt):
    markup = InlineKeyboardMarkup()
    markup.row(InlineKeyboardButton(f"👤 တစ်ဦးတည်းသုံး ({int(amt):,} Ks)", callback_data=f"adm_rdmode_{amt}_single"))
    markup.row(InlineKeyboardButton("👥 လူအများခွဲသုံး (၁၀၀၀ ~ ၃၀၀၀ Ks စီ)", callback_data=f"adm_rdmode_{amt}_shared"))
    markup.row(InlineKeyboardButton("🔙 ငွေပမာဏ ပြန်ရွေးရန်", callback_data="back_to_gen_rd"))
    return markup

def get_admin_rd_days_keyboard(amt, mode):
    markup = InlineKeyboardMarkup()
    markup.row(InlineKeyboardButton("📅 1 ရက်", callback_data=f"adm_rddur_{amt}_{mode}_1"), InlineKeyboardButton("📅 3 ရက်", callback_data=f"adm_rddur_{amt}_{mode}_3"))
    markup.row(InlineKeyboardButton("📅 5 ရက်", callback_data=f"adm_rddur_{amt}_{mode}_5"), InlineKeyboardButton("📅 7 ရက်", callback_data=f"adm_rddur_{amt}_{mode}_7"))
    markup.row(InlineKeyboardButton("🔙 နောက်သို့", callback_data="back_to_gen_rd"))
    return markup

def get_admin_rd_count_keyboard(amt, mode, days):
    markup = InlineKeyboardMarkup()
    markup.row(InlineKeyboardButton("1 ခု", callback_data=f"adm_rdcnt_{amt}_{mode}_{days}_1"), InlineKeyboardButton("3 ခု", callback_data=f"adm_rdcnt_{amt}_{mode}_{days}_3"))
    markup.row(InlineKeyboardButton("5 ခု", callback_data=f"adm_rdcnt_{amt}_{mode}_{days}_5"), InlineKeyboardButton("10 ခု", callback_data=f"adm_rdcnt_{amt}_{mode}_{days}_10"))
    markup.row(InlineKeyboardButton("🔙 ရက်ပေါင်း", callback_data=f"adm_rdmode_{amt}_{mode}"))
    return markup

def get_admin_deduct_type_keyboard():
    markup = InlineKeyboardMarkup()
    markup.row(InlineKeyboardButton("🎁 Redeem Bonus ငွေနှုတ်မည်", callback_data="adm_deduct_type_bonus"))
    markup.row(InlineKeyboardButton("💵 လက်ကျန်ငွေ ပမာဏနှုတ်မည်", callback_data="adm_deduct_type_main"))
    markup.row(InlineKeyboardButton("⚡ စုစုပေါင်း အကုန်နှုတ်မည်", callback_data="adm_deduct_type_all"))
    markup.row(InlineKeyboardButton("🔙 မူလ Menu", callback_data="back_to_main"))
    return markup

# ========== FORCE JOIN ==========
def is_user_subscribed(user_id):
    if str(user_id) in [str(aid) for aid in ADMIN_CHAT_IDS]: return True
    try:
        member = bot.get_chat_member(REQUIRED_CHANNEL, user_id)
        if member.status in ['creator', 'administrator', 'member']: return True
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
    bot.send_message(
        chat_id,
        f"⚠️ <b>သတိပေးချက်:</b>\n\nBot အား စတင်အသုံးပြုရန်အတွက် အောက်ပါ Channel ကို အရင်ဆုံး Join ပေးပါ။\n\n👉 <b>Channel:</b> {REQUIRED_CHANNEL}\n\nJoin ပြီးပါက Verify ခလုတ်ကို နှိပ်ပါ။",
        parse_mode="HTML", reply_markup=get_force_join_keyboard()
    )

# ========== OUTLINE KEY CREATION ==========
def get_user_next_key_number(user_name, target_chat_id=None):
    max_num = 0
    found_any = False
    clean_user = user_name.strip().lower()
    persistent_registry = load_persistent_keys()
    for k_data in persistent_registry.values():
        k_name = k_data.get("name", "")
        if (target_chat_id and f"({target_chat_id})" in k_name) or (clean_user in k_name.lower()):
            found_any = True
            num_match = re.search(r'\((\d+)\)\s*\d{1,2}\.\d{1,2}\.', k_name) or re.search(r'\((\d+)\)', k_name)
            if num_match:
                try:
                    val = int(num_match.group(1))
                    if str(val) != str(target_chat_id) and val > max_num: max_num = val
                except: pass
    for api_url in [OUTLINE_API_URL_1, OUTLINE_API_URL_2, OUTLINE_API_URL_3]:
        try:
            res = requests.get(f"{api_url}/access-keys", verify=False, timeout=4)
            if res.status_code == 200:
                for k in res.json().get("accessKeys", []):
                    k_name = k.get("name", "")
                    if (target_chat_id and f"({target_chat_id})" in k_name) or (clean_user in k_name.lower()):
                        found_any = True
                        num_match = re.search(r'\((\d+)\)\s*\d{1,2}\.\d{1,2}\.', k_name) or re.search(r'\((\d+)\)', k_name)
                        if num_match:
                            try:
                                val = int(num_match.group(1))
                                if str(val) != str(target_chat_id) and val > max_num: max_num = val
                            except: pass
        except: pass
    if not found_any: return 0, 1
    elif max_num == 0: return 1, 2
    else: return max_num, max_num + 1

def extract_chat_id_from_key_name(key_name):
    if not key_name: return None
    match = re.search(r'\((\d{8,12})\)', key_name)
    return match.group(1) if match else None

def get_user_ultimate_keys(chat_id, server_num="1"):
    api_url = OUTLINE_API_URL_1 if str(server_num) == "1" else (OUTLINE_API_URL_2 if str(server_num) == "2" else OUTLINE_API_URL_3)
    user_keys = []
    try:
        res = requests.get(f"{api_url}/access-keys", verify=False, timeout=6)
        if res.status_code == 200:
            for k in res.json().get("accessKeys", []):
                k_name = k.get("name", "")
                cid = extract_chat_id_from_key_name(k_name)
                if (cid and str(cid) == str(chat_id)) or (f"({chat_id})" in k_name):
                    if "[gw]" not in k_name.lower():
                        user_keys.append({"id": k.get("id"), "name": k_name, "server": str(server_num)})
    except: pass
    return user_keys

def create_outline_key(server_num, user_name, plan_info=None, target_chat_id=None, custom_days=None, months_count=1, order_id=None):
    today = datetime.now()
    if custom_days:
        expire_date = (today + timedelta(days=custom_days)).strftime("%d.%m.%Y")
    else:
        expire_date = (today + relativedelta(months=months_count)).strftime("%d.%m.%Y")
    curr_max, next_number = get_user_next_key_number(user_name, target_chat_id)
    id_str = f" ({target_chat_id})" if target_chat_id else ""
    crown_str = " 👑" if str(target_chat_id) in [str(aid) for aid in ADMIN_CHAT_IDS] else ""
    if curr_max == 0:
        key_name = f"{user_name}{crown_str}{id_str} {expire_date}"
    else:
        key_name = f"{user_name}{crown_str}{id_str} ({next_number}) {expire_date}"
    api_url = OUTLINE_API_URL_1 if str(server_num) == "1" else (OUTLINE_API_URL_2 if str(server_num) == "2" else OUTLINE_API_URL_3)
    try:
        res = requests.post(f"{api_url}/access-keys", verify=False, timeout=10)
        if res.status_code in [200, 201]:
            key_data = res.json()
            key_id = key_data.get("id")
            requests.put(f"{api_url}/access-keys/{key_id}/name", data={"name": key_name}, verify=False, timeout=8)
            limit_bytes = plan_info.get("bytes", 0) * months_count if plan_info else 0
            if limit_bytes and limit_bytes > 0:
                requests.put(f"{api_url}/access-keys/{key_id}/data-limit", json={"limit": {"bytes": limit_bytes}}, verify=False, timeout=8)
            if order_id: map_key_to_order(key_name, order_id)
            raw_url = key_data.get("accessUrl", "")
            final_key = f"{raw_url}#{key_name}"
            save_persistent_key(server_num, key_id, key_name, final_key, limit_bytes, order_id, target_chat_id)
            return final_key, key_name, expire_date
    except Exception as e:
        print("Key Generation Error:", e)
    return None, None, None

def renew_or_create_unlimited_key(server_num, user_name, target_chat_id, months_count=1, custom_days=None, order_id=None):
    api_url = OUTLINE_API_URL_1 if str(server_num) == "1" else (OUTLINE_API_URL_2 if str(server_num) == "2" else OUTLINE_API_URL_3)
    today = datetime.now()
    if custom_days:
        new_expire_date = (today + timedelta(days=custom_days)).strftime("%d.%m.%Y")
    else:
        new_expire_date = (today + relativedelta(months=months_count)).strftime("%d.%m.%Y")
    add_bytes = (500 * months_count) * 1000**3
    try:
        keys_resp = requests.get(f"{api_url}/access-keys", verify=False, timeout=8)
        metrics_resp = requests.get(f"{api_url}/metrics/transfer", verify=False, timeout=8)
        if keys_resp.status_code == 200:
            keys_data = keys_resp.json().get("accessKeys", [])
            bytes_transferred = metrics_resp.json().get("bytesTransferredByUserId", {}) if metrics_resp.status_code == 200 else {}
            target_key_id = None; target_key_name = None
            for k in keys_data:
                k_name = k.get("name", "")
                cid = extract_chat_id_from_key_name(k_name)
                if (cid and str(cid) == str(target_chat_id)) or (f"({target_chat_id})" in k_name):
                    if "[gw]" not in k_name.lower():
                        target_key_id = k.get("id"); target_key_name = k_name
                        break
            if target_key_id:
                used_bytes = bytes_transferred.get(str(target_key_id), 0)
                new_fup_limit = used_bytes + add_bytes
                updated_name = re.sub(r'\d{1,2}\.\d{1,2}\.(\d{4}|\d{2})$', new_expire_date, target_key_name)
                if updated_name == target_key_name:
                    updated_name = f"{target_key_name.split('(')[0].strip()} ({target_chat_id}) {new_expire_date}"
                requests.put(f"{api_url}/access-keys/{target_key_id}/name", data={"name": updated_name}, verify=False, timeout=8)
                requests.put(f"{api_url}/access-keys/{target_key_id}/data-limit", json={"limit": {"bytes": new_fup_limit}}, verify=False, timeout=8)
                if order_id: map_key_to_order(updated_name, order_id)
                raw_url = k.get("accessUrl", "")
                final_key = f"{raw_url}#{updated_name}"
                save_persistent_key(server_num, target_key_id, updated_name, final_key, new_fup_limit, order_id, target_chat_id)
                return final_key, updated_name, new_expire_date, True
    except Exception as e:
        print("Unlimited Renewal Error:", e)
    vpn_key, key_name, expire_date = create_outline_key(server_num, user_name, plan_info={"bytes": add_bytes}, target_chat_id=target_chat_id, custom_days=custom_days, months_count=months_count, order_id=order_id)
    return vpn_key, key_name, expire_date, False

def generate_random_redeem_code():
    return ''.join(random.choices(string.ascii_lowercase + string.digits, k=10))

# ========== PAYMENT TEXT ==========
def get_payment_instruction_text(amt):
    return (
        f"✅ <b>Wallet ထဲသို့ ငွေဖြည့်သွင်းရန်</b>\n"
        f"💵 ဖြည့်သွင်းမည့် ပမာဏ: <b>{amt:,} Ks</b>\n\n"
        f"━━━━━━━━━━━━━━━\n"
        f"💰 <b>ငွေလွှဲရမည့် အကောင့်များ:</b>\n\n"
        f"📱 <b>KBZ Pay</b> - <code>09699970092</code>\n👤 Htet Myat Aung\n\n"
        f"📱 <b>Wave Pay</b> - <code>09699970092</code>\n👤 Htet Myat Aung\n\n"
        f"📱 <b>AYA Pay</b> - <code>09699970092</code>\n👤 Htet Myat Aung\n\n"
        f"📱 <b>Uab Pay</b> - <code>09699970092</code>\n👤 Htet Myat Aung\n\n"
        f"📱 <b>CB Pay</b> - <code>09699970092</code>\n👤 Htet Myat Aung\n\n"
        f"━━━━━━━━━━━━━━━\n\n"
        f"👉 <b>{amt:,} Ks</b> တိတိကျကျ လွှဲပြီး 📸 Screenshot ပို့ပါ။"
    )

# ========== OCR HELPERS ==========
def parse_slip_ocr(file_path):
    try:
        file_url = f"https://api.telegram.org/file/bot{TELEGRAM_TOKEN}/{file_path}"
        img_resp = requests.get(file_url, timeout=12)
        if img_resp.status_code == 200:
            files = {'file': ('slip.jpg', img_resp.content, 'image/jpeg')}
            payload = {'apikey': OCR_API_KEY, 'language': 'eng', 'isOverlayRequired': False, 'OCREngine': '2'}
            res = requests.post('https://api.ocr.space/parse/image', files=files, data=payload, timeout=20)
            if res.status_code == 200:
                result = res.json()
                if result.get("IsErroredOnProcessing") == False:
                    pr = result.get("ParsedResults", [])
                    if pr: return pr[0].get("ParsedText", "")
    except Exception as e:
        print("OCR API Error:", e)
    return ""

def clean_ocr_text_thoroughly(text):
    if not text: return ""
    for mm, en in {'၀':'0','၁':'1','၂':'2','၃':'3','၄':'4','၅':'5','၆':'6','၇':'7','၈':'8','၉':'9'}.items():
        text = text.replace(mm, en)
    return text

def extract_transaction_last6(ocr_text):
    if not ocr_text: return None
    normalized = clean_ocr_text_thoroughly(ocr_text)
    for ph in MY_PAYMENT_PHONES: normalized = normalized.replace(ph, "")
    lines = normalized.splitlines()
    for i, line in enumerate(lines):
        clean_l = line.replace(" ", "").replace("-", "")
        if any(k in clean_l.lower() for k in ["transaction", "trx", "လုပ်ဆောင်ချက်", "အိုင်ဒီ", "အမှတ်"]):
            digits = re.findall(r'\d{6,24}', clean_l)
            if digits: return digits[0][-6:]
            if i + 1 < len(lines):
                nd = re.findall(r'\d{6,24}', lines[i+1].replace(" ", ""))
                if nd: return nd[0][-6:]
    kpay = re.search(r'\b(010\d{13,20})\b', normalized.replace(" ", ""))
    if kpay: return kpay.group(1)[-6:]
    nums = re.findall(r'\b\d{8,15}\b', normalized.replace("-", " "))
    for num in nums:
        if not num.startswith("09") and not num.startswith("9699"): return num[-6:]
    return None

def generate_order_id_from_slip(file_path=None):
    if file_path:
        last6 = extract_transaction_last6(parse_slip_ocr(file_path))
        if last6 and len(last6) == 6: return f"#{last6}"
    return f"#{''.join(random.choices(string.ascii_uppercase + string.digits, k=6))}"

# ========== CALLBACK: BACK TO MAIN ==========
@bot.callback_query_handler(func=lambda call: call.data == "back_to_main")
def handle_back_to_main(call):
    try:
        chat_id = call.message.chat.id
        clear_all_states(chat_id)
        bot.answer_callback_query(call.id, "🔙 Menu သို့ ပြန်သွားပါပြီ။")
        try: bot.delete_message(chat_id, call.message.message_id)
        except: pass
        bot.send_message(chat_id, "👋 H & E FEATURE PREMIUM VPN Bot မှ ကြိုဆိုပါတယ်။\n\n👇 Menu ကို သုံးပြီး ရွေးချယ်ပါ။", reply_markup=get_main_menu_keyboard(chat_id))
    except Exception as e:
        print("back_to_main error:", e)

@bot.callback_query_handler(func=lambda call: call.data == "back_to_gen_rd")
def handle_back_to_gen_rd(call):
    try:
        bot.answer_callback_query(call.id)
        if str(call.from_user.id) not in [str(aid) for aid in ADMIN_CHAT_IDS] and str(call.message.chat.id) not in [str(aid) for aid in ADMIN_CHAT_IDS]: return
        bot.edit_message_text("🎟️ <b>Wallet Redeem Code ထုတ်ရန်:</b>\n\nငွေပမာဏ ရွေးပါ:", chat_id=call.message.chat.id, message_id=call.message.message_id, parse_mode="HTML", reply_markup=get_admin_rd_amounts_keyboard())
    except:
        try: bot.send_message(call.message.chat.id, "🎟️ ငွေပမာဏ ရွေးပါ:", reply_markup=get_admin_rd_amounts_keyboard())
        except: pass

# ========== ADMIN RD CODE GENERATION ==========
@bot.callback_query_handler(func=lambda call: call.data.startswith("adm_rdamt_"))
def handle_admin_rd_amt(call):
    try:
        bot.answer_callback_query(call.id)
        if str(call.from_user.id) not in [str(aid) for aid in ADMIN_CHAT_IDS] and str(call.message.chat.id) not in [str(aid) for aid in ADMIN_CHAT_IDS]: return
        amt = int(call.data.replace("adm_rdamt_", ""))
        if amt in [5000, 10000]:
            bot.edit_message_text(f"🎟️ <b>{amt:,} Ks Wallet Redeem Code</b>\n\nပုံစံ ရွေးပါ:", chat_id=call.message.chat.id, message_id=call.message.message_id, parse_mode="HTML", reply_markup=get_admin_rd_mode_keyboard(amt))
        else:
            bot.edit_message_text(f"🎟️ <b>{amt:,} Ks (တစ်ဦးတည်းသုံး)</b>\n\nသက်တမ်း (ရက်) ရွေးပါ:", chat_id=call.message.chat.id, message_id=call.message.message_id, parse_mode="HTML", reply_markup=get_admin_rd_days_keyboard(amt, "single"))
    except Exception as e: print("adm_rdamt error:", e)

@bot.callback_query_handler(func=lambda call: call.data.startswith("adm_rdmode_"))
def handle_admin_rd_mode(call):
    try:
        bot.answer_callback_query(call.id)
        parts = call.data.split("_")
        amt, mode = parts[2], parts[3]
        mode_text = "တစ်ဦးတည်းသုံး" if mode == "single" else "လူအများခွဲသုံး"
        bot.edit_message_text(f"🎟️ <b>{int(amt):,} Ks ({mode_text})</b>\n\nသက်တမ်း (ရက်) ရွေးပါ:", chat_id=call.message.chat.id, message_id=call.message.message_id, parse_mode="HTML", reply_markup=get_admin_rd_days_keyboard(amt, mode))
    except Exception as e: print("adm_rdmode error:", e)

@bot.callback_query_handler(func=lambda call: call.data.startswith("adm_rddur_"))
def handle_admin_rd_days(call):
    try:
        bot.answer_callback_query(call.id)
        parts = call.data.split("_")
        amt, mode, days = parts[2], parts[3], parts[4]
        mode_text = "တစ်ဦးတည်းသုံး" if mode == "single" else "လူအများခွဲသုံး"
        bot.edit_message_text(f"🎟️ <b>{int(amt):,} Ks ({mode_text} - {days} ရက်)</b>\n\nCode အရေအတွက် ရွေးပါ:", chat_id=call.message.chat.id, message_id=call.message.message_id, parse_mode="HTML", reply_markup=get_admin_rd_count_keyboard(amt, mode, days))
    except Exception as e: print("adm_rddur error:", e)

@bot.callback_query_handler(func=lambda call: call.data.startswith("adm_rdcnt_"))
def handle_admin_rd_gen(call):
    try:
        if is_callback_processed(f"rdgen_{call.message.message_id}_{call.data}"):
            bot.answer_callback_query(call.id); return
        bot.answer_callback_query(call.id, "✅ Code များထုတ်ပြီးပါပြီ!")
        parts = call.data.split("_")
        amt, mode, days, count = int(parts[2]), parts[3], int(parts[4]), int(parts[5])
        codes = load_redeem_codes()
        gen_list = []
        for _ in range(count):
            code = generate_random_redeem_code()
            codes[code] = {"type": "wallet", "amount": amt, "mode": mode, "remaining": amt, "validity_days": days, "claimed_users": []}
            gen_list.append(f"<code>{code}</code>")
        save_redeem_codes(codes)
        mode_desc = "လူအများခွဲသုံး (၁၀၀၀ ~ ၃၀၀၀ Ks စီ)" if mode == "shared" else f"တစ်ဦးတည်းသုံး ({amt:,} Ks)"
        reply = (
            f"🎉 <b>Wallet Redeem Code ({count} ခု) ထုတ်ပြီးပါပြီ:</b>\n\n"
            f"💵 ငွေ: <b>{amt:,} MMK</b>\n📌 ပုံစံ: <b>{mode_desc}</b>\n⏰ သက်တမ်း: <b>{days} ရက်</b>\n\n"
            + "\n".join(gen_list) + f"\n\n💡 <i>{days} ရက်အတွင်း အသုံးပြုပါ။</i>"
        )
        bot.edit_message_text(reply, chat_id=call.message.chat.id, message_id=call.message.message_id, parse_mode="HTML", reply_markup=get_back_inline_keyboard())
    except Exception as e: print("adm_rdcnt error:", e)

@bot.callback_query_handler(func=lambda call: call.data.startswith("adm_deduct_type_"))
def handle_admin_deduct_type(call):
    try:
        bot.answer_callback_query(call.id)
        if str(call.from_user.id) not in [str(aid) for aid in ADMIN_CHAT_IDS]: return
        dtype = call.data.replace("adm_deduct_type_", "")
        set_state(call.message.chat.id, "admin_deduct", {"type": dtype, "step": "ask_user"})
        type_name = "Redeem Bonus ငွေ" if dtype == "bonus" else ("လက်ကျန်ငွေ ပမာဏ" if dtype == "main" else "စုစုပေါင်း လက်ကျန်ငွေ")
        bot.edit_message_text(f"💸 <b>{type_name} နှုတ်ယူရန်:</b>\n\n👇 Customer ၏ Telegram Chat ID ရိုက်ပါ:", chat_id=call.message.chat.id, message_id=call.message.message_id, parse_mode="HTML", reply_markup=get_back_inline_keyboard())
    except Exception as e: print("adm_deduct_type error:", e)

# ========== VERIFY SUBSCRIPTION ==========
@bot.callback_query_handler(func=lambda call: call.data == "verify_subscription")
def handle_verify_sub(call):
    try:
        chat_id = call.message.chat.id
        if is_user_subscribed(chat_id):
            save_user_id(chat_id)
            bot.answer_callback_query(call.id, "✅ Verification အောင်မြင်ပါသည်။")
            try: bot.delete_message(chat_id, call.message.message_id)
            except: pass
            bot.send_message(chat_id, "👋 H & E FEATURE PREMIUM VPN Bot မှ ကြိုဆိုပါတယ်။\n\n👇 Menu ကို သုံးပါ။", reply_markup=get_main_menu_keyboard(chat_id))
        else:
            bot.answer_callback_query(call.id, "❌ Channel ထဲ မဝင်ရသေးပါ။", show_alert=True)
    except Exception as e: print("verify_sub error:", e)

# ========== WALLET / TOPUP ==========
@bot.callback_query_handler(func=lambda call: call.data == "btn_open_topup")
def handle_btn_open_topup(call):
    try:
        bot.answer_callback_query(call.id)
        set_state(call.message.chat.id, "custom_topup", False)
        bot.edit_message_text("💰 <b>ငွေပမာဏ ရွေးပါ:</b>", chat_id=call.message.chat.id, message_id=call.message.message_id, parse_mode="HTML", reply_markup=get_topup_amounts_keyboard())
    except Exception as e: print("btn_open_topup error:", e)

@bot.callback_query_handler(func=lambda call: call.data.startswith("topup_amt_"))
def handle_topup_amt(call):
    try:
        bot.answer_callback_query(call.id)
        chat_id = call.message.chat.id
        raw_val = call.data.replace("topup_amt_", "")
        if raw_val == "custom":
            set_state(chat_id, "custom_topup", True)
            set_state(chat_id, "topup", None)
            markup = InlineKeyboardMarkup()
            markup.row(InlineKeyboardButton("🔙 ငွေပမာဏ ပြန်ရွေးရန်", callback_data="btn_open_topup"))
            markup.row(InlineKeyboardButton("🔙 မူလ Menu သို့", callback_data="back_to_main"))
            bot.edit_message_text("✍️ <b>စိတ်ကြိုက်ငွေပမာဏ ရိုက်ထည့်ပါ:</b>\n\nဥပမာ- <code>15000</code>", chat_id=chat_id, message_id=call.message.message_id, parse_mode="HTML", reply_markup=markup)
            return
        amt = int(raw_val)
        set_state(chat_id, "topup", amt)
        set_state(chat_id, "custom_topup", False)
        markup = InlineKeyboardMarkup()
        markup.row(InlineKeyboardButton("🔙 ငွေပမာဏ ပြန်ရွေးရန်", callback_data="btn_open_topup"))
        markup.row(InlineKeyboardButton("🔙 မူလ Menu သို့", callback_data="back_to_main"))
        bot.edit_message_text(get_payment_instruction_text(amt), chat_id=chat_id, message_id=call.message.message_id, parse_mode="HTML", reply_markup=markup)
    except Exception as e: print("topup_amt error:", e)

@bot.callback_query_handler(func=lambda call: call.data.startswith("approve_topup_"))
def handle_approve_topup(call):
    try:
        if is_callback_processed(f"appr_{call.message.message_id}_{call.data}"):
            bot.answer_callback_query(call.id, "⚠️ ပြီးပါပြီ။"); return
        if str(call.message.chat.id) not in [str(aid) for aid in ADMIN_CHAT_IDS]: return
        parts = call.data.split("_")
        target_chat_id, amount, topup_id = parts[2], int(parts[3]), parts[4]
        new_balance, _ = update_user_balance(target_chat_id, amount)
        bot.answer_callback_query(call.id, f"✅ {amount:,} Ks ဖြည့်ပြီးပါပြီ။")
        try:
            bot.send_message(target_chat_id, f"🎉 <b>ငွေဖြည့်သွင်းမှု အောင်မြင်ပါသည်!</b>\n\n🧾 Top-Up ID: <code>{topup_id}</code>\n\n💵 ဖြည့်ငွေ: <b>+{amount:,} MMK</b>\n\n💳 လက်ကျန်ငွေ: <b>{new_balance:,} MMK</b>", parse_mode="HTML")
        except: pass
        try: bot.edit_message_caption(chat_id=call.message.chat.id, message_id=call.message.message_id, caption=(call.message.caption or "") + f"\n\n✅ <b>APPROVED (+{amount:,} MMK)</b>", parse_mode="HTML", reply_markup=None)
        except: pass
    except Exception as e: print("approve_topup error:", e)

# ========== PLAN SELECTION (ROBUST) ==========
@bot.callback_query_handler(func=lambda call: call.data.startswith("selectplan_"))
def handle_select_plan(call):
    try:
        chat_id = call.message.chat.id
        plan_code = call.data.replace("selectplan_", "")
        plan = PLANS.get(plan_code)
        if not plan:
            bot.answer_callback_query(call.id, "❌ Plan ရှာမတွေ့ပါ။", show_alert=True); return
        
        # Answer callback EARLY so user sees feedback
        bot.answer_callback_query(call.id)
        
        amount = plan["price"]
        balance = get_user_balance(chat_id)
        is_admin = str(chat_id) in [str(aid) for aid in ADMIN_CHAT_IDS]
        _, bonus_bal, _ = get_user_balance_breakdown(chat_id)
        has_redeem = (bonus_bal > 0) and not is_admin
        
        # Ultimate special: renew existing key
        if plan_code == "ultimate" and not has_redeem:
            user_keys = get_user_ultimate_keys(chat_id, "1")
            if len(user_keys) > 0:
                markup = InlineKeyboardMarkup()
                for idx, uk in enumerate(user_keys, 1):
                    markup.row(InlineKeyboardButton(f"♻️ Key #{idx} ({uk['name'][:25]}) တိုးမည်", callback_data=f"renew_choice_{plan_code}_1_{uk['id']}"))
                markup.row(InlineKeyboardButton("➕ Key အသစ် ဝယ်မည်", callback_data=f"renew_choice_{plan_code}_1_new"))
                markup.row(InlineKeyboardButton("🔙 Plan များ", callback_data="back_to_plans"))
                markup.row(InlineKeyboardButton("🔙 မူလ Menu", callback_data="back_to_main"))
                text = f"🌌 <b>Ultimate VIP Plan</b>\n\n💡 Active Key <b>{len(user_keys)} ခု</b> ရှိပါသည်။\n\n👇 သက်တမ်းတိုးမည့် Key ရွေးပါ (သို့) အသစ်ဝယ်ပါ:"
                try: bot.edit_message_text(text, chat_id=chat_id, message_id=call.message.message_id, parse_mode="HTML", reply_markup=markup)
                except: bot.send_message(chat_id, text, parse_mode="HTML", reply_markup=markup)
                return
        
        # Build purchase markup
        markup = InlineKeyboardMarkup()
        if balance >= amount or is_admin:
            if plan_code == "ultimate" or has_redeem:
                label = "📡 Server 1 🇸🇬 (Redeem Credit)" if has_redeem else "📡 Server 1 🇸🇬 (Main Server) ဖြင့် ဝယ်မည်"
                markup.row(InlineKeyboardButton(label, callback_data=f"buywallet_{plan_code}_1"))
            else:
                markup.row(InlineKeyboardButton("📡 Server 1 🇸🇬 ဖြင့် ဝယ်မည်", callback_data=f"buywallet_{plan_code}_1"))
                markup.row(InlineKeyboardButton("📡 Server 2 🇸🇬 ဖြင့် ဝယ်မည်", callback_data=f"buywallet_{plan_code}_2"))
                markup.row(InlineKeyboardButton("📡 Server 3 🇸🇬 ဖြင့် ဝယ်မည်", callback_data=f"buywallet_{plan_code}_3"))
        else:
            markup.row(InlineKeyboardButton(f"💰 ငွေ {amount - balance:,} Ks ထပ်ဖြည့်ရန်", callback_data="btn_open_topup"))
        markup.row(InlineKeyboardButton("🔙 Plan များ", callback_data="back_to_plans"))
        markup.row(InlineKeyboardButton("🔙 မူလ Menu", callback_data="back_to_main"))
        
        balance_disp = "♾️" if is_admin else f"{balance:,} MMK"
        status = "✅ ဝယ်ယူရန် လုံလောက်ပါသည်" if (balance >= amount or is_admin) else f"⚠️ ငွေမလုံလောက်ပါ (+{amount-balance:,} Ks ဖြည့်ပါ)"
        redeem_notice = "\n💡 <i>(Redeem ငွေ ရှိသဖြင့် Server 1 မှသာ ထုတ်ပေးမည်)</i>" if has_redeem else ""
        
        text = (
            f"🛍️ <b>ဝယ်ယူမည့် Plan အချက်အလက်</b>\n\n"
            f"📮 <b>Plan:</b> {plan['name']}\n"
            f"🗃️ <b>Data:</b> {plan['data']} (၁လစာ)\n"
            f"💵 <b>ကျသင့်ငွေ:</b> {amount:,} MMK\n\n"
            f"━━━━━━━━━━━━━━━\n"
            f"💳 <b>လက်ကျန်ငွေ:</b> <b>{balance_disp}</b>\n"
            f"အခြေအနေ: <b>{status}</b>\n"
            f"━━━━━━━━━━━━━━━\n{redeem_notice}\n"
            f"👇 ဆာဗာ ရွေးပါ:"
        )
        try:
            bot.edit_message_text(text, chat_id=chat_id, message_id=call.message.message_id, parse_mode="HTML", reply_markup=markup)
        except Exception as edit_err:
            print(f"Edit failed, trying send: {edit_err}")
            try: bot.send_message(chat_id, text, parse_mode="HTML", reply_markup=markup)
            except Exception as send_err:
                print(f"Send failed: {send_err}")
    except Exception as e:
        print(f"handle_select_plan FATAL: {e}")
        try: bot.answer_callback_query(call.id, f"❌ Error: {str(e)[:80]}", show_alert=True)
        except: pass

@bot.callback_query_handler(func=lambda call: call.data.startswith("renew_choice_"))
def handle_renew_choice(call):
    try:
        bot.answer_callback_query(call.id)
        chat_id = call.message.chat.id
        raw = call.data[len("renew_choice_"):]
        tail = raw.rsplit("_", 1)
        choice_val = tail[1]
        head = tail[0].rsplit("_", 1)
        plan_code, server_num = head[0], head[1]
        plan = PLANS.get(plan_code)
        if not plan: return
        amount = plan["price"]
        balance = get_user_balance(chat_id)
        is_admin = str(chat_id) in [str(aid) for aid in ADMIN_CHAT_IDS]
        if not is_admin and balance < amount:
            bot.answer_callback_query(call.id, "❌ ငွေမလုံလောက်ပါ။", show_alert=True); return
        order_id = "#" + "".join(random.choices(string.ascii_uppercase + string.digits, k=6))
        new_bal, used_bonus_days = update_user_balance(chat_id, -amount)
        chat_info = call.message.chat
        uf = getattr(chat_info, 'first_name', '') or ""
        ul = getattr(chat_info, 'last_name', '') or ""
        user_name = f"{uf} {ul}".strip() or "HMA Customer"
        bot.answer_callback_query(call.id, "⏳ VPN Key ဆောင်ရွက်နေပါသည်...")
        apply_days = None if is_admin else used_bonus_days
        if choice_val == "new":
            vpn_key, key_name, expire_date = create_outline_key(server_num, user_name, plan_info=plan, target_chat_id=chat_id, custom_days=apply_days, months_count=1, order_id=order_id)
        else:
            today = datetime.now()
            expire_date = (today + (timedelta(days=apply_days) if apply_days else relativedelta(months=1))).strftime("%d.%m.%Y")
            vpn_key, key_name, expire_date = None, None, expire_date
            try:
                api_url = OUTLINE_API_URL_1 if server_num == "1" else (OUTLINE_API_URL_2 if server_num == "2" else OUTLINE_API_URL_3)
                keys_resp = requests.get(f"{api_url}/access-keys", verify=False, timeout=8)
                metrics_resp = requests.get(f"{api_url}/metrics/transfer", verify=False, timeout=8)
                if keys_resp.status_code == 200:
                    keys_data = keys_resp.json().get("accessKeys", [])
                    bt = metrics_resp.json().get("bytesTransferredByUserId", {}) if metrics_resp.status_code == 200 else {}
                    for k in keys_data:
                        if str(k.get("id")) == str(choice_val):
                            tkn = k.get("name", "")
                            used = bt.get(str(choice_val), 0)
                            add_b = (500) * 1000**3
                            nfl = used + add_b
                            un = re.sub(r'\d{1,2}\.\d{1,2}\.(\d{4}|\d{2})$', expire_date, tkn)
                            if un == tkn: un = f"{tkn.split('(')[0].strip()} {expire_date}"
                            requests.put(f"{api_url}/access-keys/{choice_val}/name", data={"name": un}, verify=False, timeout=8)
                            requests.put(f"{api_url}/access-keys/{choice_val}/data-limit", json={"limit": {"bytes": nfl}}, verify=False, timeout=8)
                            map_key_to_order(un, order_id)
                            final = f"{k.get('accessUrl','')}#{un}"
                            save_persistent_key(server_num, choice_val, un, final, nfl, order_id)
                            vpn_key, key_name = final, un
                            break
            except Exception as e: print("renew err:", e)
        if not vpn_key:
            update_user_balance(chat_id, amount)
            bot.send_message(chat_id, "❌ ဆာဗာလိုင်းမရပါ။ ငွေ ပြန်ထည့်ပြီးပါပြီ။", reply_markup=get_back_inline_keyboard())
            return
        save_sale_transaction(server_num, chat_id, plan_code, plan['name'], 1, amount, order_id=order_id)
        save_user_purchase_record(chat_id=chat_id, order_id=order_id, plan_name=plan['name'], disp_gb=plan["data"], months_count=1, price_str=f"{amount:,} Ks", server_num=server_num, expire_date=expire_date, vpn_key=vpn_key)
        save_key_mapping(user_name.strip().lower(), chat_id)
        udb = "♾️" if is_admin else f"{new_bal:,} MMK"
        success = (
            f"🎉 <b>ဝယ်ယူမှု အောင်မြင်ပါသည်!</b>\n\n"
            f"🧾 <b>Order ID:</b> <code>{order_id}</code>\n\n"
            f"🛍️ <b>Plan:</b> {plan['name']} ({plan['data']})\n"
            f"📡 <b>Server:</b> Singapore {server_num} 🇸🇬\n"
            f"⏰ <b>သက်တမ်းကုန်ရက်:</b> {expire_date}\n"
            + (f"<i>(Redeem ငွေအလိုက် {apply_days} ရက်)</i>\n" if apply_days else "") +
            f"\n💳 <b>လက်ကျန်ငွေ:</b> <code>{udb}</code>\n\n"
            f"🔑 <b>VPN Key:</b>\n\n<code>{vpn_key}</code>\n\n"
            f"☝️ Key ကို တစ်ချက်နှိပ် Auto Copy ကူးပါ။"
        )
        try: bot.edit_message_text(success, chat_id=chat_id, message_id=call.message.message_id, parse_mode="HTML", reply_markup=get_back_inline_keyboard())
        except: bot.send_message(chat_id, success, parse_mode="HTML", reply_markup=get_back_inline_keyboard())
    except Exception as e:
        print(f"renew_choice FATAL: {e}")

# ========== BUY WITH WALLET (MAIN PURCHASE FLOW) ==========
@bot.callback_query_handler(func=lambda call: call.data.startswith("buywallet_"))
def handle_buy_with_wallet(call):
    try:
        chat_id = call.message.chat.id
        lock_key = f"buy_{call.message.message_id}_{call.data}"
        if is_callback_processed(lock_key):
            bot.answer_callback_query(call.id, "⚠️ လုပ်ဆောင်နေပါသည်..."); return
        
        # FIXED: rsplit for plan_code with underscore
        raw_data = call.data[len("buywallet_"):]
        parts = raw_data.rsplit("_", 1)
        if len(parts) != 2:
            bot.answer_callback_query(call.id, "❌ Invalid data"); return
        plan_code, server_num = parts[0], parts[1]
        plan = PLANS.get(plan_code)
        if not plan:
            bot.answer_callback_query(call.id, "❌ Plan ရှာမတွေ့ပါ။"); return
        
        amount = plan["price"]
        balance = get_user_balance(chat_id)
        is_admin = str(chat_id) in [str(aid) for aid in ADMIN_CHAT_IDS]
        if not is_admin and balance < amount:
            bot.answer_callback_query(call.id, "❌ လက်ကျန်ငွေ မလုံလောက်ပါ။", show_alert=True); return
        
        bot.answer_callback_query(call.id, "⏳ VPN Key ထုတ်ပေးနေပါသည်...")
        order_id = "#" + "".join(random.choices(string.ascii_uppercase + string.digits, k=6))
        new_bal, used_bonus_days = update_user_balance(chat_id, -amount)
        
        chat_info = call.message.chat
        uf = getattr(chat_info, 'first_name', '') or ""
        ul = getattr(chat_info, 'last_name', '') or ""
        user_name = f"{uf} {ul}".strip() or "HMA Customer"
        apply_days = None if is_admin else used_bonus_days
        
        vpn_key = None; key_name = None; expire_date = None
        disp_gb = plan["data"]
        
        if plan_code == "ultimate":
            vpn_key, key_name, expire_date, _ = renew_or_create_unlimited_key(server_num, user_name, chat_id, months_count=1, custom_days=apply_days, order_id=order_id)
        else:
            vpn_key, key_name, expire_date = create_outline_key(server_num, user_name, plan_info=plan, target_chat_id=chat_id, custom_days=apply_days, months_count=1, order_id=order_id)
        
        if not vpn_key:
            update_user_balance(chat_id, amount)
            try: bot.send_message(chat_id, "❌ ဆာဗာလိုင်းမရပါ။ ငွေ ပြန်ထည့်ပြီးပါပြီ။", reply_markup=get_back_inline_keyboard())
            except: pass
            return
        
        save_sale_transaction(server_num, chat_id, plan_code, plan['name'], 1, amount, order_id=order_id)
        save_user_purchase_record(chat_id=chat_id, order_id=order_id, plan_name=plan['name'], disp_gb=disp_gb, months_count=1, price_str=f"{amount:,} Ks", server_num=server_num, expire_date=expire_date, vpn_key=vpn_key)
        save_key_mapping(user_name.strip().lower(), chat_id)
        
        exp_info = f"⏰ <b>သက်တမ်းကုန်ဆုံးရက်:</b> {expire_date}"
        if apply_days:
            exp_info += f" <i>(Redeem {apply_days} ရက်)</i>"
        udb = "♾️" if is_admin else f"{new_bal:,} MMK"
        
        success_text = (
            f"🎉 <b>ဝယ်ယူမှု အောင်မြင်ပါသည်ခင်ဗျာ!</b>\n\n"
            f"🧾 <b>Order ID:</b> <code>{order_id}</code>\n\n"
            f"🛍️ <b>Plan:</b> {plan['name']} ({disp_gb})\n"
            f"📡 <b>Server:</b> Singapore Server {server_num} 🇸🇬\n\n"
            f"{exp_info}\n\n"
            f"💳 <b>ကျန်ရှိသော လက်ကျန်ငွေ:</b> <code>{udb}</code>\n\n"
            f"🔑 <b>လူကြီးမင်း၏ VPN Key:</b>\n\n"
            f"<code>{vpn_key}</code>\n\n"
            f"☝️ Key ကို <b>တစ်ချက်တည်း နှိပ်လိုက်ရုံဖြင့်</b> Auto Copy ကူးသွားပါလိမ့်မယ်။ V2BOX VPN App ထဲ ထည့်သုံးပါ။"
        )
        try:
            bot.edit_message_text(success_text, chat_id=chat_id, message_id=call.message.message_id, parse_mode="HTML", reply_markup=get_back_inline_keyboard())
        except Exception as edit_e:
            print(f"edit success failed: {edit_e}")
            try: bot.send_message(chat_id, success_text, parse_mode="HTML", reply_markup=get_back_inline_keyboard())
            except Exception as send_e:
                print(f"send success failed: {send_e}")
        
        for aid in ADMIN_CHAT_IDS:
            try:
                bot.send_message(aid, f"🛍️ <b>Customer ကီးဝယ်သွားပါပြီ။</b>\n\n🧾 Order: <code>{order_id}</code>\n👤 {user_name} (<code>{chat_id}</code>)\n🛍️ {plan['name']}\n📡 Server {server_num}\n💵 {amount:,} MMK\n⏰ {expire_date}", parse_mode="HTML")
            except: pass
    except Exception as e:
        print(f"buywallet FATAL: {e}")
        try: bot.answer_callback_query(call.id, f"❌ Error: {str(e)[:80]}", show_alert=True)
        except: pass

@bot.callback_query_handler(func=lambda call: call.data == "back_to_plans")
def handle_back_to_plans(call):
    try:
        bot.answer_callback_query(call.id)
        bot.edit_message_text("🧸 ဝယ်ယူလိုသော Plan ရွေးပါ:", chat_id=call.message.chat.id, message_id=call.message.message_id, reply_markup=get_plan_keyboard())
    except Exception as e: print("back_to_plans error:", e)

# ========== REDEEM CODE (USER) ==========
@bot.callback_query_handler(func=lambda call: call.data == "btn_open_redeem")
def handle_btn_open_redeem(call):
    try:
        bot.answer_callback_query(call.id)
        chat_id = call.message.chat.id
        is_admin = str(chat_id) in [str(aid) for aid in ADMIN_CHAT_IDS]
        if not is_admin:
            _, bonus_bal, _ = get_user_balance_breakdown(chat_id)
            if bonus_bal > 0:
                bot.send_message(chat_id, f"⚠️ <b>Redeem Bonus {bonus_bal:,} MMK ရှိနေဆဲဖြစ်၍ Code အသစ် ထပ်မရယူနိုင်ပါ။</b>", parse_mode="HTML", reply_markup=get_back_inline_keyboard())
                return
        set_state(chat_id, "redeem", True)
        bot.send_message(chat_id, "🎟️ <b>Redeem Code ထည့်ရန်:</b>\n\nAdmin ထံမှ ရရှိသော Code ကို Chat ထဲ Paste ချပို့ပါ:", parse_mode="HTML", reply_markup=get_back_inline_keyboard())
    except Exception as e: print("btn_open_redeem error:", e)

# ========== MESSAGE HANDLERS ==========
@bot.message_handler(commands=['start'])
def send_welcome(message):
    try:
        chat_id = message.chat.id
        save_user_id(chat_id)
        clear_all_states(chat_id)
        if not is_user_subscribed(chat_id):
            send_force_join_message(chat_id); return
        uf = getattr(message.from_user, 'first_name', '') or ""
        ul = getattr(message.from_user, 'last_name', '') or ""
        full_name = f"{uf} {ul}".strip() or "HMA User"
        bot.reply_to(message, f"👋 မင်္ဂလာပါ {full_name}!\nH & E FEATURE PREMIUM VPN Bot မှ ကြိုဆိုပါတယ်။\n\n👇 Menu ကို သုံးပါ။", reply_markup=get_main_menu_keyboard(chat_id))
        try:
            bot.set_chat_menu_button(chat_id, telebot.types.MenuButtonWebApp(type="web_app", text="Main Website", web_app=WebAppInfo(url="https://h-e.feature.hma.qzz.io")))
        except: pass
    except Exception as e: print("start error:", e)

@bot.message_handler(commands=['buy'])
def send_plans(message):
    chat_id = message.chat.id
    save_user_id(chat_id)
    if not is_user_subscribed(chat_id):
        send_force_join_message(chat_id); return
    clear_all_states(chat_id)
    bot.reply_to(message, "🧸 Plan ရွေးပါ:", reply_markup=get_plan_keyboard())

@bot.message_handler(commands=['deduct'])
def handle_admin_deduct_cmd(message):
    chat_id = str(message.chat.id)
    if chat_id not in [str(aid) for aid in ADMIN_CHAT_IDS]: return
    parts = message.text.strip().split()
    if len(parts) < 3:
        bot.reply_to(message, "⚠️ <code>/deduct &lt;Chat_ID&gt; &lt;Amount&gt;</code>", parse_mode="HTML"); return
    target_id, amt_str = parts[1].strip(), parts[2].strip()
    if not amt_str.isdigit():
        bot.reply_to(message, "❌ ဂဏန်းသာ ရိုက်ပါ။"); return
    amt = int(amt_str)
    deducted, m, b, f = admin_deduct_specific_funds(target_id, amt, "all")
    bot.reply_to(message, f"✅ <b>အောင်မြင်ပါသည်!</b>\n\n👤 ID: <code>{target_id}</code>\n💵 နှုတ်ငွေ: <b>-{deducted:,} MMK</b>\n💳 ကျန်ငွေ: <b>{f:,} MMK</b>", parse_mode="HTML")
    try: bot.send_message(target_id, f"⚠️ Wallet ထဲမှ <b>-{deducted:,} MMK</b> Admin နှုတ်ယူလိုက်ပါသည်။\n💳 ကျန်ငွေ: <b>{f:,} MMK</b>", parse_mode="HTML")
    except: pass

@bot.message_handler(commands=['redeem'])
def handle_redeem_cmd(message):
    chat_id = message.chat.id
    save_user_id(chat_id)
    clear_all_states(chat_id)
    if not is_user_subscribed(chat_id):
        send_force_join_message(chat_id); return
    is_admin = str(chat_id) in [str(aid) for aid in ADMIN_CHAT_IDS]
    if not is_admin:
        _, bonus_bal, _ = get_user_balance_breakdown(chat_id)
        if bonus_bal > 0:
            bot.send_message(chat_id, f"⚠️ Redeem Bonus {bonus_bal:,} MMK ရှိနေဆဲပါ။", parse_mode="HTML", reply_markup=get_back_inline_keyboard()); return
    set_state(chat_id, "redeem", True)
    bot.send_message(chat_id, "🎟️ Redeem Code ကို Paste ချပို့ပါ:", reply_markup=get_back_inline_keyboard())

# ========== PHOTO HANDLER (TOPUP) ==========
@bot.message_handler(content_types=['photo'])
def handle_photo_messages(message):
    try:
        chat_id = message.chat.id
        save_user_id(chat_id)
        if not is_user_subscribed(chat_id):
            send_force_join_message(chat_id); return
        if str(chat_id) in [str(aid) for aid in ADMIN_CHAT_IDS] and get_state(chat_id, "broadcast"):
            set_state(chat_id, "broadcast", False)
            all_users = load_all_users()
            cnt = 0
            photo_id = message.photo[-1].file_id
            caption_text = message.caption or ""
            bot.send_message(chat_id, f"⏳ Broadcast ({len(all_users)}) ဆီ ပို့နေသည်...")
            for uid in all_users:
                if str(uid) in [str(aid) for aid in ADMIN_CHAT_IDS]: continue
                try:
                    bot.send_photo(uid, photo_id, caption=caption_text, parse_mode="HTML"); cnt += 1
                except: pass
            bot.send_message(chat_id, f"✅ ပို့ပြီး! {cnt}/{len(all_users)}", parse_mode="HTML"); return
        
        uf = getattr(message.from_user, 'first_name', '') or ""
        ul = getattr(message.from_user, 'last_name', '') or ""
        user_name = f"{uf} {ul}".strip() or "HMA User"
        username = f"@{message.from_user.username}" if message.from_user.username else "No Username"
        topup_amt = get_state(chat_id, "topup") or 1000
        set_state(chat_id, "topup", None)
        set_state(chat_id, "custom_topup", False)
        photo_file = bot.get_file(message.photo[-1].file_id)
        topup_id = generate_order_id_from_slip(photo_file.file_path)
        alert = f"💰 <b>Top-Up အသစ်</b>\n\n🧾 ID: <code>{topup_id}</code>\n👤 {user_name} ({username})\n💵 <b>{topup_amt:,} MMK</b>\n🆔 <code>{chat_id}</code>"
        markup = InlineKeyboardMarkup()
        markup.add(InlineKeyboardButton(f"✅ Approve (+{topup_amt:,})", callback_data=f"approve_topup_{chat_id}_{topup_amt}_{topup_id}"))
        for aid in ADMIN_CHAT_IDS:
            try: bot.send_photo(aid, message.photo[-1].file_id, caption=alert, parse_mode="HTML", reply_markup=markup)
            except: pass
        bot.reply_to(message, f"💌 ပြေစာ ရရှိပါသည်။\n🧾 ID: <code>{topup_id}</code>\n💵 {topup_amt:,} MMK\n\nAdmin စစ်ဆေးပြီး ချက်ချင်း ဖြည့်ပေးပါမည်။", parse_mode="HTML")
    except Exception as e: print("photo error:", e)

# ========== KEY FETCH ==========
def fetch_key_from_server(api_url, input_value):
    if not api_url or "dummyKey" in api_url: return None, None, None
    api_url = api_url.rstrip('/')
    server_num = "1" if api_url == OUTLINE_API_URL_1.rstrip('/') else ("2" if api_url == OUTLINE_API_URL_2.rstrip('/') else "3")
    try:
        keys_resp = requests.get(f"{api_url}/access-keys", verify=False, timeout=5)
        bt = {}
        try:
            mr = requests.get(f"{api_url}/metrics/transfer", verify=False, timeout=4)
            if mr.status_code == 200: bt = mr.json().get("bytesTransferredByUserId", {})
        except: pass
        if keys_resp.status_code == 200:
            keys_data = keys_resp.json().get("accessKeys", [])
            sync_keys_to_persistent_registry(server_num, keys_data)
            tk = None; input_raw = input_value.strip()
            if re.search(r'^\d+$', input_raw):
                for k in keys_data:
                    if str(k.get("id")) == input_raw: tk = k; break
            if not tk and "#" in input_raw:
                rh = input_raw.split("#")[-1].strip().lower()
                for k in keys_data:
                    kn = k.get("name", "").strip().lower()
                    if rh and (rh in kn or kn in rh): tk = k; break
            if not tk and input_raw.startswith("ss://"):
                ci = input_raw.replace("ss://", "").split("?")[0].split("#")[0].strip()
                for k in keys_data:
                    su = k.get("accessUrl", "").replace("ss://", "").split("?")[0].split("#")[0].strip()
                    if ci and (ci in su or su in ci): tk = k; break
                    try:
                        if ci.split("@")[0] == su.split("@")[0]: tk = k; break
                    except: pass
            if not tk:
                for k in keys_data:
                    if input_raw.lower() in k.get("name", "").strip().lower(): tk = k; break
            if tk: return tk, bt, server_num
    except Exception as e: print(f"Fetch {api_url}:", e)
    pr = load_persistent_keys(); input_raw = input_value.strip().lower()
    for uid, kd in pr.items():
        if kd.get("server") == server_num:
            kn = kd.get("name", "").lower()
            au = kd.get("access_url", "").lower()
            if (input_raw.startswith("ss://") and clean_ss_url(input_raw) in clean_ss_url(au)) or (input_raw in kn):
                return {"id": kd.get("key_id"), "name": kd.get("name"), "accessUrl": kd.get("access_url", "").split("#")[0], "dataLimit": {"bytes": kd.get("limit_bytes")} if kd.get("limit_bytes") else {}}, {}, server_num
    return None, None, None

# ========== MAIN MESSAGE DISPATCHER ==========
@bot.message_handler(func=lambda message: True)
def handle_all_messages(message):
    try:
        input_value = message.text.strip()
        chat_id = message.chat.id
        save_user_id(chat_id)
        if not is_user_subscribed(chat_id):
            send_force_join_message(chat_id); return
        
        # Custom Topup Amount
        if get_state(chat_id, "custom_topup"):
            clean_amt = re.sub(r'[^\d]', '', input_value)
            if clean_amt and clean_amt.isdigit():
                amt = int(clean_amt)
                if amt < 500:
                    bot.reply_to(message, "⚠️ အနည်းဆုံး 500 Ks ပါ။"); return
                set_state(chat_id, "custom_topup", False)
                set_state(chat_id, "topup", amt)
                markup = InlineKeyboardMarkup()
                markup.row(InlineKeyboardButton("🔙 ငွေပမာဏ", callback_data="btn_open_topup"))
                markup.row(InlineKeyboardButton("🔙 မူလ Menu", callback_data="back_to_main"))
                bot.send_message(chat_id, get_payment_instruction_text(amt), parse_mode="HTML", reply_markup=markup); return
            else:
                bot.reply_to(message, "❌ ဂဏန်းသာ ရိုက်ပါ။"); return
        
        # Admin Deduct Dialog
        if str(chat_id) in [str(aid) for aid in ADMIN_CHAT_IDS]:
            ds = get_state(chat_id, "admin_deduct")
            if ds:
                step = ds.get("step"); dtype = ds.get("type", "all")
                if step == "ask_user":
                    tid = input_value.strip()
                    if not tid.isdigit():
                        bot.reply_to(message, "❌ Chat ID ဂဏန်းသာ ရိုက်ပါ။"); return
                    ds["target_user_id"] = tid; ds["step"] = "ask_amount"
                    set_state(chat_id, "admin_deduct", ds)
                    m, b, t = get_user_balance_breakdown(tid)
                    bot.reply_to(message, f"👤 ID: <code>{tid}</code>\n💵 လက်ကျန်: <b>{m:,} Ks</b>\n🎁 Redeem: <b>{b:,} Ks</b>\n💎 စုစုပေါင်း: <b>{t:,} Ks</b>\n\n👇 နှုတ်ယူမည့် ပမာဏ ရိုက်ပါ:", parse_mode="HTML"); return
                elif step == "ask_amount":
                    ca = re.sub(r'[^\d]', '', input_value)
                    if not ca.isdigit() or int(ca) <= 0:
                        bot.reply_to(message, "❌ ဂဏန်းသာ ရိုက်ပါ။"); return
                    tid = ds.get("target_user_id"); amt = int(ca)
                    set_state(chat_id, "admin_deduct", None)
                    ded, m, b, f = admin_deduct_specific_funds(tid, amt, dtype)
                    bot.reply_to(message, f"✅ <b>အောင်မြင်ပါသည်!</b>\n\n👤 ID: <code>{tid}</code>\n💵 နှုတ်: <b>-{ded:,} MMK</b>\n💳 ကျန်: <b>{f:,} MMK</b>", parse_mode="HTML")
                    try: bot.send_message(tid, f"⚠️ Wallet ထဲမှ <b>-{ded:,} MMK</b> Admin နှုတ်လိုက်ပါသည်။\n💳 ကျန်: <b>{f:,} MMK</b>", parse_mode="HTML")
                    except: pass
                    return
        
        # Admin Broadcast
        if str(chat_id) in [str(aid) for aid in ADMIN_CHAT_IDS] and get_state(chat_id, "broadcast"):
            set_state(chat_id, "broadcast", False)
            all_users = load_all_users()
            cnt = 0
            bot.send_message(chat_id, f"⏳ Broadcast ({len(all_users)}) ဆီ ပို့နေသည်...")
            for uid in all_users:
                if str(uid) in [str(aid) for aid in ADMIN_CHAT_IDS]: continue
                try: bot.send_message(uid, input_value, parse_mode="HTML"); cnt += 1
                except: pass
            bot.send_message(chat_id, f"✅ ပို့ပြီး! {cnt}/{len(all_users)}", parse_mode="HTML"); return
        
        # Main Menu Buttons
        if input_value in ["🛍️ Plan များဝယ်ရန်", "Plan များဝယ်ရန်"]:
            clear_all_states(chat_id)
            bot.send_message(chat_id, "🧸 Plan ရွေးပါ:", reply_markup=get_plan_keyboard()); return
        
        if input_value in ["💰 ငွေဖြည့်ရန်", "ငွေဖြည့်ရန်"]:
            clear_all_states(chat_id)
            bot.send_message(chat_id, "💰 <b>ငွေပမာဏ ရွေးပါ:</b>", parse_mode="HTML", reply_markup=get_topup_amounts_keyboard()); return
        
        if input_value in ["💳 လက်ကျန်ငွေ", "လက်ကျန်ငွေ"]:
            clear_all_states(chat_id)
            is_admin = str(chat_id) in [str(aid) for aid in ADMIN_CHAT_IDS]
            m, b, t = get_user_balance_breakdown(chat_id)
            bd = ""
            if b > 0:
                ed = load_expiring_credits().get(str(chat_id), [])
                lines = [f"   • <b>+{g['remaining']:,} Ks</b> (ကုန်ရက်: <code>{g['expire_disp']}</code>)" for g in ed if g.get("remaining", 0) > 0]
                if lines: bd = "\n⏳ <b>ရက်စွဲပါ လက်ကျန်ငွေများ:</b>\n" + "\n".join(lines) + "\n"
            crown = " 👑" if is_admin else ""
            mdisp = "♾️" if is_admin else f"{m:,} MMK"
            tdisp = "♾️" if is_admin else f"{t:,} MMK"
            uf = getattr(message.from_user, 'first_name', '') or ""
            ul = getattr(message.from_user, 'last_name', '') or ""
            full_name = f"{uf} {ul}".strip() or "HMA User"
            text = f"💳 <b>Wallet အချက်အလက်</b>\n\n👤 {full_name}{crown}\n🆔 <code>{chat_id}</code>\n\n💵 လက်ကျန်: {mdisp}\n🎁 Redeem: {b:,} MMK\n{bd}━━━━━━━━━━━━━━━\n💎 စုစုပေါင်း: <b>{tdisp}</b>\n━━━━━━━━━━━━━━━"
            markup = InlineKeyboardMarkup()
            markup.row(InlineKeyboardButton("💰 ငွေဖြည့်", callback_data="btn_open_topup"), InlineKeyboardButton("🎟️ Redeem Code", callback_data="btn_open_redeem"))
            markup.row(InlineKeyboardButton("🔙 မူလ Menu", callback_data="back_to_main"))
            bot.send_message(chat_id, text, parse_mode="HTML", reply_markup=markup); return
        
        if input_value in ["🧰 Data ပမာဏစစ်ရန်", "Data ပမာဏစစ်ရန်"]:
            clear_all_states(chat_id)
            bot.send_message(chat_id, "👇 VPN Key (<code>ss://...</code>) ကို Paste ချပို့ပါ။", parse_mode="HTML", reply_markup=get_back_inline_keyboard()); return
        
        if input_value in ["📇 ဝယ်ယူမှုမှတ်တမ်း", "ဝယ်ယူမှုမှတ်တမ်း"]:
            clear_all_states(chat_id)
            recs = get_user_combined_purchase_records(chat_id)
            if not recs:
                bot.send_message(chat_id, "📇 <i>မှတ်တမ်း မရှိသေးပါ။</i>", parse_mode="HTML", reply_markup=get_back_inline_keyboard()); return
            texts = []
            for idx, r in enumerate(reversed(recs), 1):
                srv = f"S{r.get('server','1')} 🇸🇬" if r.get('server') != "VIP" else "VIP 🇸🇬"
                vk = r.get('vpn_key', '')
                kb = f"<code>{vk}</code>" if vk != "N/A" else "<i>(Key မရှိ)</i>"
                texts.append(f"<b>#{idx}</b>\n🧾 <code>{r.get('order_id','N/A')}</code>\n📅 {r.get('timestamp','N/A')}\n🛍️ {r.get('plan_name','')} ({r.get('disp_gb','')})\n📡 {srv}\n⏰ {r.get('expire_date','N/A')}\n🔑\n{kb}")
            final = f"📇 <b>ဝယ်ယူမှုမှတ်တမ်း ({len(recs)} ခု):</b>\n\n" + "\n\n━━━━━━━━━━\n\n".join(texts)
            if len(final) > 4000:
                for p in [final[i:i+4000] for i in range(0, len(final), 4000)]: bot.send_message(chat_id, p, parse_mode="HTML")
            else:
                bot.send_message(chat_id, final, parse_mode="HTML", reply_markup=get_back_inline_keyboard())
            return
        
        if input_value in ["♻️ Key လဲရန်", "Key လဲရန်"]:
            clear_all_states(chat_id)
            set_state(chat_id, "replacement", True)
            bot.send_message(chat_id, "♻️ အဆင်မပြေသော VPN Key (<code>ss://...</code>) ကို Paste ချပါ။", parse_mode="HTML", reply_markup=get_back_inline_keyboard()); return
        
        if input_value in ["👨‍💻 Admin ဆက်သွယ်ရန်", "Admin ဆက်သွယ်ရန်"]:
            clear_all_states(chat_id)
            markup = InlineKeyboardMarkup()
            markup.add(InlineKeyboardButton("💬 Admin ထံ စာပို့ရန်", url="https://t.me/H_M_A_2026"))
            markup.add(InlineKeyboardButton("🔙 မူလ Menu", callback_data="back_to_main"))
            bot.send_message(chat_id, "👇 Admin ထံ ဆက်သွယ်ရန်:", reply_markup=markup); return
        
        # Redeem Code
        if get_state(chat_id, "redeem"):
            set_state(chat_id, "redeem", False)
            is_admin = str(chat_id) in [str(aid) for aid in ADMIN_CHAT_IDS]
            if not is_admin:
                _, bb, _ = get_user_balance_breakdown(chat_id)
                if bb > 0:
                    bot.send_message(chat_id, f"⚠️ Redeem Bonus {bb:,} MMK ရှိနေဆဲပါ။", parse_mode="HTML", reply_markup=get_back_inline_keyboard()); return
            codes = load_redeem_codes()
            ci = input_value.strip().lower()
            mk = None
            for ck in codes.keys():
                if ck.strip().lower() == ci: mk = ck; break
            if mk:
                info = codes[mk]
                vd = int(info.get("validity_days", 1))
                mode = info.get("mode", "single")
                usid = str(chat_id)
                claimed = info.get("claimed_users", [])
                if mode == "shared":
                    if not is_admin and usid in claimed:
                        bot.send_message(chat_id, "⚠️ ဤ Code ရယူပြီးဖြစ်ပါသည်။", parse_mode="HTML", reply_markup=get_back_inline_keyboard()); return
                    rem = int(info.get("remaining", 0))
                    if rem < 500:
                        del codes[mk]; save_redeem_codes(codes)
                        bot.send_message(chat_id, "❌ Code ပြည့်သွားပါပြီ။", parse_mode="HTML", reply_markup=get_back_inline_keyboard()); return
                    vopts = [o for o in [1000, 2000, 3000] if o <= rem]
                    if not vopts: aw = rem
                    else:
                        w = [70, 20, 10][:len(vopts)]
                        aw = random.choices(vopts, weights=w, k=1)[0]
                    nb, ed = add_expiring_bonus_to_wallet(chat_id, aw, vd)
                    rem -= aw; claimed.append(usid)
                    info["remaining"] = rem; info["claimed_users"] = claimed
                    if rem < 500: del codes[mk]
                    else: codes[mk] = info
                    save_redeem_codes(codes)
                    un = getattr(message.from_user, 'first_name', '') or "Winner"
                    ci_icon = " 👑" if is_admin else ""
                    dtb = "♾️" if is_admin else f"{nb:,} MMK"
                    bot.send_message(chat_id, f"🎉 <b>Redeem အောင်မြင်ပါသည်!</b>\n\n👤 {un}{ci_icon}\n🎟️ <code>{mk}</code>\n💵 <b>+{aw:,} MMK</b>\n⏰ {vd} ရက် ({ed} ကုန်)\n\n💳 စုစုပေါင်း: <b>{dtb}</b>", parse_mode="HTML", reply_markup=get_back_inline_keyboard())
                    for aid in ADMIN_CHAT_IDS:
                        try: bot.send_message(aid, f"🎟️ <b>Shared Code:</b>\n{un} (<code>{chat_id}</code>) → <code>{mk}</code> = {aw:,} MMK ({vd} ရက်)\n(ကျန်: {rem:,} MMK)", parse_mode="HTML")
                        except: pass
                    return
                else:
                    ata = int(info.get("amount", 1000))
                    del codes[mk]; save_redeem_codes(codes)
                    nb, ed = add_expiring_bonus_to_wallet(chat_id, ata, vd)
                    un = getattr(message.from_user, 'first_name', '') or "Winner"
                    ci_icon = " 👑" if is_admin else ""
                    dtb = "♾️" if is_admin else f"{nb:,} MMK"
                    bot.send_message(chat_id, f"🎉 <b>Redeem အောင်မြင်ပါသည်!</b>\n\n👤 {un}{ci_icon}\n🎟️ <code>{mk}</code>\n💵 <b>+{ata:,} MMK</b>\n⏰ {vd} ရက် ({ed} ကုန်)\n\n💳 စုစုပေါင်း: <b>{dtb}</b>", parse_mode="HTML", reply_markup=get_back_inline_keyboard())
                    for aid in ADMIN_CHAT_IDS:
                        try: bot.send_message(aid, f"🎟️ <b>Single Code:</b>\n{un} (<code>{chat_id}</code>) → <code>{mk}</code> = {ata:,} MMK ({vd} ရက်)", parse_mode="HTML")
                        except: pass
                    return
            else:
                bot.send_message(chat_id, "❌ Code မှားနေသည် (သို့) အသုံးပြုပြီးဖြစ်သည်။", parse_mode="HTML", reply_markup=get_back_inline_keyboard()); return
        
        # Admin: Search User
        if input_value == "🔍 Cus ရှာရန်":
            clear_all_states(chat_id)
            if str(chat_id) not in [str(aid) for aid in ADMIN_CHAT_IDS]:
                bot.reply_to(message, "❌ Admin သီးသန့်။"); return
            bot.send_message(chat_id, "⏳ Customer စာရင်း တွက်ချက်နေသည်...")
            # Summary
            s1, s2, s3 = set(), set(), set()
            tset = set()
            for sn, au in [("1", OUTLINE_API_URL_1), ("2", OUTLINE_API_URL_2), ("3", OUTLINE_API_URL_3)]:
                try:
                    r = requests.get(f"{au}/access-keys", verify=False, timeout=4)
                    if r.status_code == 200:
                        for k in r.json().get("accessKeys", []):
                            kn = k.get("name", "").strip()
                            cm = re.search(r'\((\d+)\)', kn)
                            ident = cm.group(1) if cm else kn.lower()
                            if ident:
                                if sn == "1": s1.add(ident)
                                elif sn == "2": s2.add(ident)
                                elif sn == "3": s3.add(ident)
                                tset.add(ident)
                except: pass
            pr = load_persistent_keys()
            for kd in pr.values():
                cid = kd.get("chat_id"); kn = kd.get("name", "").strip(); sv = str(kd.get("server", "1"))
                ident = cid if cid else kn.lower()
                if ident:
                    if sv == "1": s1.add(ident)
                    elif sv == "2": s2.add(ident)
                    elif sv == "3": s3.add(ident)
                    tset.add(ident)
            summ = f"👥 <b>Customer စာရင်း</b>\n\n📡 S1: <b>{len(s1)}</b> ယောက်\n📡 S2: <b>{len(s2)}</b> ယောက်\n📡 S3: <b>{len(s3)}</b> ယောက်\n━━━━━━━━━━\n🌟 စုစုပေါင်း: <b>{len(tset)}</b> ယောက်\n\n👇 ရှာလိုသော နာမည်အစ / Chat ID / Order ID ရိုက်ပါ:"
            set_state(chat_id, "search", True)
            bot.send_message(chat_id, summ, parse_mode="HTML", reply_markup=get_back_inline_keyboard()); return
        
        # Admin: Gen RD Code
        if input_value == "🎟️ Gen RD Code":
            clear_all_states(chat_id)
            if str(chat_id) not in [str(aid) for aid in ADMIN_CHAT_IDS]: return
            bot.send_message(chat_id, "🎟️ <b>Redeem Code ထုတ်ရန် ငွေပမာဏ ရွေးပါ:</b>", parse_mode="HTML", reply_markup=get_admin_rd_amounts_keyboard()); return
        
        # Admin: Deduct
        if input_value == "💸 ငွေနှုတ်ရန်":
            clear_all_states(chat_id)
            if str(chat_id) not in [str(aid) for aid in ADMIN_CHAT_IDS]: return
            bot.send_message(chat_id, "💸 <b>ငွေနှုတ်ယူရန် အမျိုးအစား ရွေးပါ:</b>", parse_mode="HTML", reply_markup=get_admin_deduct_type_keyboard()); return
        
        # Admin: Broadcast
        if input_value == "📢 Broadcast စာပို့ရန်":
            clear_all_states(chat_id)
            if str(chat_id) not in [str(aid) for aid in ADMIN_CHAT_IDS]: return
            au = load_all_users()
            set_state(chat_id, "broadcast", True)
            bot.send_message(chat_id, f"📢 <b>Broadcast ({len(au)} User):</b>\n\nစာသား / ဓာတ်ပုံ ပို့ပါ:", parse_mode="HTML", reply_markup=get_back_inline_keyboard()); return
        
        # Admin: Search Input
        if str(chat_id) in [str(aid) for aid in ADMIN_CHAT_IDS] and get_state(chat_id, "search"):
            set_state(chat_id, "search", False)
            q = input_value.strip().lower()
            bot.send_message(chat_id, f"⏳ '{input_value}' ရှာနေသည်...")
            matches = []; seen = set()
            ko = load_key_orders()
            for sn, au in [("1", OUTLINE_API_URL_1), ("2", OUTLINE_API_URL_2), ("3", OUTLINE_API_URL_3)]:
                try:
                    r = requests.get(f"{au}/access-keys", verify=False, timeout=4)
                    if r.status_code == 200:
                        kdata = r.json().get("accessKeys", [])
                        sync_keys_to_persistent_registry(sn, kdata)
                        for k in kdata:
                            kn = k.get("name", "").strip().lower()
                            ao = ko.get(kn, "").lower()
                            kid = str(k.get("id")); uid = f"{sn}_{kid}"
                            if len(q) == 1:
                                if kn.startswith(q): matches.append((sn, kid, k.get("name", ""))); seen.add(uid)
                            else:
                                if q in kn or (ao and q in ao): matches.append((sn, kid, k.get("name", ""))); seen.add(uid)
                except: pass
            pr = load_persistent_keys()
            for uid, kd in pr.items():
                if uid in seen: continue
                kn = kd.get("name", "").lower(); ko2 = kd.get("order_id", "").lower()
                sn = kd.get("server", "1"); kid = kd.get("key_id", "0"); cid = kd.get("chat_id", "").lower()
                if len(q) == 1:
                    if kn.startswith(q): matches.append((sn, kid, kd.get("name", ""))); seen.add(uid)
                else:
                    if q in kn or (ko2 and q in ko2) or (cid and q in cid): matches.append((sn, kid, kd.get("name", ""))); seen.add(uid)
            if matches:
                mk = InlineKeyboardMarkup()
                for sn, kid, kn in matches[:30]:
                    icon = f"📡 S{sn}🇸🇬" if sn != "VIP" else "⚡ VIP 🇸🇬"
                    mk.add(InlineKeyboardButton(f"{icon} | {kn[:35]}", callback_data=f"viewkey_{sn}_{kid}"))
                mk.add(InlineKeyboardButton("🔙 မူလ Menu", callback_data="back_to_main"))
                bot.send_message(chat_id, f"🔎 <b>တွေ့ရှိ ({len(matches)} ခု):</b>", parse_mode="HTML", reply_markup=mk)
            else:
                bot.send_message(chat_id, f"❌ '{input_value}' ရှာမတွေ့ပါ။", parse_mode="HTML", reply_markup=get_back_inline_keyboard())
            return
        
        # Key Replacement
        if get_state(chat_id, "replacement"):
            set_state(chat_id, "replacement", False)
            bot.send_message(chat_id, "⏳ Key စစ်ဆေးနေသည်...")
            tk, bt, sn = fetch_key_from_server(OUTLINE_API_URL_1, input_value)
            if not tk: tk, bt, sn = fetch_key_from_server(OUTLINE_API_URL_2, input_value)
            if not tk: tk, bt, sn = fetch_key_from_server(OUTLINE_API_URL_3, input_value)
            if tk:
                fn = tk.get("name", "HMA User"); kid = str(tk.get("id"))
                dm = re.search(r'\d{1,2}\.\d{1,2}\.(\d{4}|\d{2})', fn)
                ed = dm.group(0) if dm else "30.09.2026"
                lb = tk.get("dataLimit", {}).get("bytes", 0)
                ub = bt.get(kid, 0)
                tg = bytes_to_gb(lb) if lb else 500
                ug = bytes_to_gb(ub)
                rg = max(0, round(tg - ug, 2))
                alert = f"♻️ <b>KEY REPLACEMENT</b>\n\n👤 {getattr(message.from_user, 'first_name', '')}\n🆔 <code>{chat_id}</code>\n📡 S{sn}\n🔑 {fn}\n🧰 ကျန်: <b>{rg} GB</b>/{tg} GB\n⏰ {ed}"
                mk = InlineKeyboardMarkup()
                mk.row(
                    InlineKeyboardButton("📡 S1 သို့", callback_data=f"replace_srv1_{sn}_{kid}_{chat_id}_{rg}_{ed}"),
                    InlineKeyboardButton("📡 S2 သို့", callback_data=f"replace_srv2_{sn}_{kid}_{chat_id}_{rg}_{ed}"),
                    InlineKeyboardButton("📡 S3 သို့", callback_data=f"replace_srv3_{sn}_{kid}_{chat_id}_{rg}_{ed}")
                )
                mk.row(InlineKeyboardButton("❌ Reject", callback_data=f"replace_reject_{chat_id}_{kid}"))
                for aid in ADMIN_CHAT_IDS:
                    try: bot.send_message(aid, alert, parse_mode="HTML", reply_markup=mk)
                    except: pass
                bot.send_message(chat_id, "✅ Admin ထံ ပို့ပြီးပါပြီ။", reply_markup=get_back_inline_keyboard())
            else:
                bot.send_message(chat_id, "❌ Key ရှာမတွေ့ပါ။", reply_markup=get_back_inline_keyboard())
            return
        
        # Admin: Total Data Usage
        if input_value == "📊 Total Data Usage":
            clear_all_states(chat_id)
            if str(chat_id) not in [str(aid) for aid in ADMIN_CHAT_IDS]: return
            bot.send_message(chat_id, "📡 တွက်ချက်နေသည်...")
            def stats(au):
                tk, tb = 0, 0
                try:
                    kr = requests.get(f"{au}/access-keys", verify=False, timeout=6)
                    mr = requests.get(f"{au}/metrics/transfer", verify=False, timeout=6)
                    if kr.status_code == 200: tk = len(kr.json().get("accessKeys", []))
                    if mr.status_code == 200: tb = sum(mr.json().get("bytesTransferredByUserId", {}).values())
                except: pass
                return tk, tb
            t1, b1 = stats(OUTLINE_API_URL_1); t2, b2 = stats(OUTLINE_API_URL_2); t3, b3 = stats(OUTLINE_API_URL_3)
            ob = b1 + b2 + b3
            rep = f"📊 <b>SERVER STATS</b>\n\n📡 S1: <b>{t1}</b> keys | <b>{bytes_to_gb(b1)} GB</b>\n📡 S2: <b>{t2}</b> keys | <b>{bytes_to_gb(b2)} GB</b>\n📡 S3: <b>{t3}</b> keys | <b>{bytes_to_gb(b3)} GB</b>\n━━━━━━━━━━\n🌟 Total: <b>{bytes_to_gb(ob)} GB</b>"
            bot.send_message(chat_id, rep, parse_mode="HTML", reply_markup=get_back_inline_keyboard()); return
        
        # Admin: Monthly Revenue
        if input_value in ["💰 လစဉ် ဝင်ငွေ", "လစဉ် ဝင်ငွေ"]:
            clear_all_states(chat_id)
            if str(chat_id) not in [str(aid) for aid in ADMIN_CHAT_IDS]: return
            now = datetime.utcnow() + timedelta(hours=6, minutes=30)
            cy, cm = now.year, now.month
            today = now.strftime("%Y-%m-%d")
            sales = load_sales_history()
            s1k=s1r=s2k=s2r=s3k=s3r=vk=vr=0
            tk=today_k=tr=today_r=0
            tp = {}
            for it in sales:
                if it.get("year") == cy and it.get("month") == cm:
                    sv = str(it.get("server", "1")); pr = int(it.get("price", 0))
                    pn = it.get("plan_name", "Plan"); pm = it.get("months", 1)
                    pk = f"{pn} [{pm} လ]"
                    ist = (it.get("date") == today)
                    if ist: tp[pk] = tp.get(pk, 0) + 1
                    if sv == "1": s1k += 1; s1r += pr; tk += 1; tr += pr
                    elif sv == "2": s2k += 1; s2r += pr; tk += 1; tr += pr
                    elif sv == "3": s3k += 1; s3r += pr; tk += 1; tr += pr
                    else: vk += 1; vr += pr; tk += 1; tr += pr
                    if ist: today_k += 1; today_r += pr
            bd = "\n".join([f"   • {k}: <b>{v}</b> ခု" for k, v in tp.items()]) if tp else "   • <i>မရှိ</i>"
            rep = f"💵 <b>REVENUE REPORT</b>\n📅 <code>{now.strftime('%d/%m/%Y %I:%M %p')}</code>\n━━━━━━━━━━\n🔥 <b>ဒီနေ့</b>\n🔑 {today_k} ခု\n{bd}\n💰 <b>{today_r:,} Ks</b>\n━━━━━━━━━━\n📡 S1: <b>{s1r:,} Ks</b> ({s1k})\n📡 S2: <b>{s2r:,} Ks</b> ({s2k})\n📡 S3: <b>{s3r:,} Ks</b> ({s3k})\n⚡ VIP: <b>{vr:,} Ks</b> ({vk})\n━━━━━━━━━━\n🌐 Total: <b>{tk} ခု</b>\n💎 <b>{tr:,} MMK</b>"
            bot.send_message(chat_id, rep, parse_mode="HTML", reply_markup=get_back_inline_keyboard()); return
        
        if input_value in ["🤖 Bot Refresh", "/refresh"]:
            clear_all_states(chat_id)
            bot.send_message(chat_id, "🤖 <b>Bot Refresh ပြီးပါပြီ!</b>", parse_mode="HTML", reply_markup=get_main_menu_keyboard(chat_id)); return
        
        if input_value.startswith('/'): return
        
        # Data Check (Paste Key)
        tk, bt, sn = fetch_key_from_server(OUTLINE_API_URL_1, input_value)
        if not tk: tk, bt, sn = fetch_key_from_server(OUTLINE_API_URL_2, input_value)
        if not tk: tk, bt, sn = fetch_key_from_server(OUTLINE_API_URL_3, input_value)
        if tk:
            try:
                fn = tk.get("name", "HMA User"); kid = str(tk.get("id"))
                dn = fn; dm = None
                for m in re.finditer(r'\d{1,2}\.\d{1,2}\.(\d{4}|\d{2})', fn): dm = m.group(0)
                if dm: dn = dn.replace(dm, "")
                dn = dn.replace("[GW]", "").replace("[gw]", "").split("tg")[0].replace("_", " ").strip() or "HMA Customer"
                hd = False
                if dm:
                    ep = dm.split('.'); d, mo, ys = int(ep[0]), int(ep[1]), ep[2]
                    yr = int("20" + ys) if len(ys) == 2 else int(ys)
                    ed = f"{d}.{mo}.{yr}"; hd = True
                lb = tk.get("dataLimit", {}).get("bytes")
                pgv = bytes_to_gb(lb) if lb else 500
                pg = f"{pgv} GB" if lb else "Unlimited"
                if bt:
                    ub = bt.get(str(kid), 0); ug = bytes_to_gb(ub)
                    ugs = f"{ug} GB"; rgs = f"{max(0, round(pgv - ug, 2))} GB" if lb else "Unlimited"
                else:
                    ugs = "Server offline"; rgs = pg
                oid = get_order_id_for_key(fn)
                ol = f"🧾 Order: <code>{oid}</code>\n\n" if oid != "N/A" else ""
                sd = f"S{sn} 🇸🇬" if bt else f"S{sn} 🇸🇬 <i>(⚠️ Offline)</i>"
                txt = f"👤 <b>{dn}</b>\n\n{ol}📡 {sd}\n🛍️ Plan: <b>{pg}</b>\n🧰 သုံးပြီး: <b>{ugs}</b>\n🗃️ ကျန်: <b>{rgs}</b>\n⏰ ကုန်ရက်: <b>{ed if hd else 'မသိ'}</b>"
                bot.reply_to(message, txt, parse_mode="HTML", reply_markup=get_back_inline_keyboard()); return
            except Exception as e:
                bot.reply_to(message, f"❌ Error: {str(e)}"); return
        
        bot.reply_to(message, "❌ <b>တစ်ခုခုမှားနေပါသည်။</b>\n\nMenu ကို /start နှိပ်ပြီး Refresh လုပ်ပါ။", parse_mode="HTML", reply_markup=get_main_menu_keyboard(chat_id))
    except Exception as e:
        print(f"handle_all FATAL: {e}")

# ========== ADMIN KEY VIEW / DELETE ==========
@bot.callback_query_handler(func=lambda call: call.data.startswith("viewkey_"))
def handle_view_key(call):
    try:
        bot.answer_callback_query(call.id)
        if str(call.message.chat.id) not in [str(aid) for aid in ADMIN_CHAT_IDS]: return
        parts = call.data.split("_"); sn = parts[1]; kid = parts[2]
        au = OUTLINE_API_URL_1 if sn == "1" else (OUTLINE_API_URL_2 if sn == "2" else OUTLINE_API_URL_3)
        au = au.rstrip('/')
        tk = None; bt = {}
        try:
            kr = requests.get(f"{au}/access-keys", verify=False, timeout=4)
            if kr.status_code == 200:
                for k in kr.json().get("accessKeys", []):
                    if str(k.get("id")) == str(kid): tk = k; break
                if tk:
                    try:
                        mr = requests.get(f"{au}/metrics/transfer", verify=False, timeout=4)
                        if mr.status_code == 200: bt = mr.json().get("bytesTransferredByUserId", {})
                    except: pass
        except Exception as e: print("Live fetch err:", e)
        ci = None
        if not tk: ci = load_persistent_keys().get(f"{sn}_{kid}")
        if tk or ci:
            if tk:
                fn = tk.get("name", "Unnamed"); rurl = tk.get("accessUrl", "")
                fk = f"{rurl}#{fn}" if fn else rurl
                lb = tk.get("dataLimit", {}).get("bytes")
                pg = f"{bytes_to_gb(lb)} GB" if lb else "Unlimited"
                ub = bt.get(str(kid), 0); ug = f"{bytes_to_gb(ub)} GB" if bt else "ဖတ်မရ"
                dm = re.search(r'\d{1,2}\.\d{1,2}\.(\d{4}|\d{2})', fn)
                ed = dm.group(0) if dm else "မသိ"
                oid = get_order_id_for_key(fn); sname = f"Server {sn} 🇸🇬"
            else:
                fn = ci.get("name", "Unnamed"); fk = ci.get("access_url", "N/A")
                lb2 = ci.get("limit_bytes"); pg = f"{bytes_to_gb(lb2)} GB" if lb2 else "Unlimited"
                ug = "Server offline"; ed = ci.get("expire_date", "မသိ"); oid = ci.get("order_id", "N/A")
                sname = f"Server {sn} 🇸🇬 <i>(⚠️ Offline)</i>"
            ol = f"🧾 <b>Order:</b> <code>{oid}</code>\n" if oid != "N/A" else ""
            mk = InlineKeyboardMarkup()
            mk.add(InlineKeyboardButton("🗑️ Delete", callback_data=f"delkey_ask_{sn}_{kid}"))
            msg = f"👤 <b>Customer Info</b>\n\n🤖 <b>{html.escape(fn)}</b>\n{ol}📡 {sname}\n🧰 {ug} / {pg}\n⏰ {ed}\n🔑 <b>Key:</b>\n\n<code>{fk}</code>"
            bot.send_message(call.message.chat.id, msg, parse_mode="HTML", reply_markup=mk)
        else:
            bot.send_message(call.message.chat.id, "❌ Key ရှာမတွေ့ပါ။")
    except Exception as e: print("viewkey err:", e)

@bot.callback_query_handler(func=lambda call: call.data.startswith("delkey_"))
def handle_del_key(call):
    try:
        bot.answer_callback_query(call.id)
        if is_callback_processed(f"del_{call.message.message_id}_{call.data}"): return
        if str(call.message.chat.id) not in [str(aid) for aid in ADMIN_CHAT_IDS]: return
        parts = call.data.split("_"); action = parts[1]; sn = parts[2]; kid = parts[3]
        if action == "ask":
            mk = InlineKeyboardMarkup()
            mk.row(InlineKeyboardButton("✅ Yes", callback_data=f"delkey_confirm_{sn}_{kid}"), InlineKeyboardButton("❌ No", callback_data="delkey_cancel"))
            bot.send_message(call.message.chat.id, f"⚠️ S{sn} ပေါ်မှ Key ({kid}) ဖျက်မှာ သေချာပါသလား?", reply_markup=mk)
        elif action == "confirm":
            pr = load_persistent_keys(); uid = f"{sn}_{kid}"
            if uid in pr: del pr[uid]; redis_set("persistent_keys_registry", pr)
            au = OUTLINE_API_URL_1 if sn == "1" else (OUTLINE_API_URL_2 if sn == "2" else OUTLINE_API_URL_3)
            try:
                requests.delete(f"{au}/access-keys/{kid}", verify=False, timeout=8)
                bot.edit_message_text(f"✅ Key ({kid}) ဖျက်ပြီးပါပြီ။", chat_id=call.message.chat.id, message_id=call.message.message_id)
            except:
                bot.edit_message_text(f"✅ မှတ်တမ်းထဲမှ Key ({kid}) ဖျက်ပြီးပါပြီ။", chat_id=call.message.chat.id, message_id=call.message.message_id)
        elif action == "cancel":
            bot.edit_message_text("❌ ဖျက်ခြင်း ပယ်ဖျက်ပါပြီ။", chat_id=call.message.chat.id, message_id=call.message.message_id)
    except Exception as e: print("delkey err:", e)

# ========== REPLACEMENT CALLBACK ==========
@bot.callback_query_handler(func=lambda call: call.data.startswith("replace_"))
def handle_replace_cb(call):
    try:
        if is_callback_processed(f"repl_{call.message.message_id}_{call.data}"):
            bot.answer_callback_query(call.id, "⚠️ ပြီးပါပြီ။"); return
        if str(call.message.chat.id) not in [str(aid) for aid in ADMIN_CHAT_IDS]: return
        parts = call.data.split("_"); action = parts[1]
        if action == "reject":
            tid = parts[2]
            try: bot.send_message(tid, "❌ Key အစားထိုးခြင်းကို Admin မှ ငြင်းလိုက်ပါသည်။")
            except: pass
            bot.edit_message_text((call.message.text or "") + "\n\n❌ <b>REJECTED</b>", chat_id=call.message.chat.id, message_id=call.message.message_id, parse_mode="HTML")
            return
        new_sn = parts[1].replace("srv", ""); old_sn = parts[2]; old_kid = parts[3]
        tid = parts[4]; rg = float(parts[5]); ed = parts[6]
        au_old = OUTLINE_API_URL_1 if old_sn == "1" else (OUTLINE_API_URL_2 if old_sn == "2" else OUTLINE_API_URL_3)
        try: requests.delete(f"{au_old}/access-keys/{old_kid}", verify=False, timeout=8)
        except: pass
        try:
            ci = bot.get_chat(tid)
            uf = getattr(ci, 'first_name', '') or ""; ul = getattr(ci, 'last_name', '') or ""
            un = f"{uf} {ul}".strip() or "HMA Customer"
            nk, _, ned = create_outline_key(new_sn, un, plan_info={"bytes": int(rg * 1000**3)}, target_chat_id=tid, months_count=1)
            if nk:
                bot.send_message(tid, f"🎉 <b>VPN Key အသစ် အစားထိုးပေးလိုက်ပါပြီ!</b>\n\n📡 Server {new_sn} 🇸🇬\n🧰 Data: {rg} GB\n⏰ {ed}\n\n🔑 <code>{nk}</code>", parse_mode="HTML")
                bot.edit_message_text((call.message.text or "") + f"\n\n✅ <b>REPLACED (S{new_sn})</b>", chat_id=call.message.chat.id, message_id=call.message.message_id, parse_mode="HTML")
                bot.answer_callback_query(call.id, "✅ ပြီးပါပြီ။")
        except Exception as e:
            bot.answer_callback_query(call.id, f"❌ {str(e)[:80]}", show_alert=True)
    except Exception as e: print("replace err:", e)

# ========== CRON CHECK ==========
@app.route('/cron-check', methods=['GET', 'POST'])
def cron_check():
    today = (datetime.utcnow() + timedelta(hours=6, minutes=30)).date()
    km = load_key_mappings(); nc = 0; dc = 0
    for au in [OUTLINE_API_URL_1, OUTLINE_API_URL_2, OUTLINE_API_URL_3]:
        try:
            kr = requests.get(f"{au}/access-keys", verify=False, timeout=8)
            mr = requests.get(f"{au}/metrics/transfer", verify=False, timeout=8)
            if kr.status_code != 200: continue
            kd = kr.json().get("accessKeys", [])
            bt = mr.json().get("bytesTransferredByUserId", {}) if mr.status_code == 200 else {}
            for k in kd:
                fn = k.get("name", ""); kid = str(k.get("id"))
                lb = k.get("dataLimit", {}).get("bytes"); ub = bt.get(kid, 0)
                is_gb_full = lb and ub >= lb
                is_today = False; should_del = False
                dms = list(re.finditer(r'(\d{1,2})\.(\d{1,2})\.(\d{2,4})', fn))
                if dms:
                    dm = dms[-1]
                    try:
                        d, m, yr = int(dm.group(1)), int(dm.group(2)), dm.group(3)
                        yr = int("20" + yr) if len(yr) == 2 else int(yr)
                        kexp = datetime(yr, m, d).date()
                        if kexp == today: is_today = True
                        elif today > kexp: should_del = True
                    except: pass
                if should_del:
                    try:
                        if requests.delete(f"{au}/access-keys/{kid}", verify=False, timeout=8).status_code in [200, 204]:
                            dc += 1
                            for aid in ADMIN_CHAT_IDS:
                                try: bot.send_message(aid, f"🗑️ Key expired & deleted: <code>{fn}</code>", parse_mode="HTML")
                                except: pass
                    except: pass
                    continue
                if is_gb_full or is_today:
                    tid = extract_chat_id_from_key_name(fn)
                    if not tid:
                        im = re.search(r'\((\d{8,12})\)', fn)
                        if im: tid = im.group(1)
                    if not tid:
                        cn = fn
                        if dms: cn = cn.replace(dms[-1].group(0), "")
                        cn = re.sub(r'\b(tg|viber|mess|fb)\b', '', cn, flags=re.IGNORECASE).replace("[GW]", "").replace("[gw]", "").strip().lower()
                        tid = km.get(cn)
                        if not tid:
                            for mn, cid in km.items():
                                if mn in cn or cn in mn: tid = cid; break
                    warn = "Data GB ပြည့်ပါပြီ" if is_gb_full else "ယနေ့ သက်တမ်းကုန်ပါပြီ"
                    if tid:
                        try:
                            bot.send_message(tid, f"⚠️ <b>သတိပေးချက်:</b>\n\nVPN Key ({fn}) <b>{warn}</b>\n\nဆက်သုံးလိုပါက Bot '🛍️ Plan များဝယ်ရန်' မှ ပြန်ဝယ်ပါ။", parse_mode="HTML")
                            nc += 1
                        except: pass
                    for aid in ADMIN_CHAT_IDS:
                        try: bot.send_message(aid, f"📢 <b>Customer:</b> {fn}\n⚠️ {warn}\n🆔 {tid or 'မသိ'}", parse_mode="HTML")
                        except: pass
        except: pass
    return jsonify({"status": "ok", "notified": nc, "deleted": dc}), 200

@app.route('/', defaults={'path': ''}, methods=['POST', 'GET'])
@app.route('/<path:path>', methods=['POST', 'GET'])
def index(path):
    if request.method == 'POST':
        try:
            update = telebot.types.Update.de_json(request.get_data().decode('utf-8'))
            bot.process_new_updates([update])
        except Exception as e:
            print("Webhook error:", e)
        return jsonify({"status": "ok"}), 200
    return "Bot is running perfectly!", 200