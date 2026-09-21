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

# 🔑 Admin Telegram Chat IDs
ADMIN_CHAT_IDS = ["8778394176", "6297145771"]

# 🔍 OCR Space API Key Configuration
OCR_API_KEY = "K87641025188957"
MY_PAYMENT_PHONES = ["09699970092", "9699970092", "699970092"]

bot = telebot.TeleBot(TELEGRAM_TOKEN, threaded=False)
requests.packages.urllib3.disable_warnings()

# 🌐 Vercel Upstash Redis REST API Setup
KV_URL = os.environ.get("KV_REST_API_URL")
KV_TOKEN = os.environ.get("KV_REST_API_TOKEN")

def redis_get(key):
    if not KV_URL or not KV_TOKEN:
        return None
    try:
        res = requests.get(f"{KV_URL}/get/{key}", headers={"Authorization": f"Bearer {KV_TOKEN}"}, timeout=15)
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
        res = requests.post(f"{KV_URL}/set/{key}", headers={"Authorization": f"Bearer {KV_TOKEN}"}, data=val_str, timeout=15)
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
PERSISTENT_KEYS_FILE = "/tmp/persistent_keys.json"
WALLET_FILE = "/tmp/user_wallets.json"
TOPUP_STATE_FILE = "/tmp/user_topup_state.json"
CUSTOM_TOPUP_STATE_FILE = "/tmp/user_custom_topup.json"
EXPIRING_CREDITS_FILE = "/tmp/expiring_credits.json"
DEDUCT_STATE_FILE = "/tmp/admin_deduct_state.json"
RENEW_CHOICE_STATE_FILE = "/tmp/user_renew_choice.json"
PROCESSED_CALLBACKS = set()

def is_callback_processed(call_id):
    if call_id in PROCESSED_CALLBACKS:
        return True
    PROCESSED_CALLBACKS.add(call_id)
    if len(PROCESSED_CALLBACKS) > 1000:
        PROCESSED_CALLBACKS.clear()
    return False

# 💳 Advanced Wallet System
def load_all_wallets():
    data = redis_get("user_wallets_data")
    if data is not None:
        return data
    if os.path.exists(WALLET_FILE):
        try:
            with open(WALLET_FILE, 'r') as f:
                return json.load(f)
        except:
            pass
    return {}

def load_expiring_credits():
    data = redis_get("user_expiring_credits")
    if data is not None:
        return data
    if os.path.exists(EXPIRING_CREDITS_FILE):
        try:
            with open(EXPIRING_CREDITS_FILE, 'r') as f:
                return json.load(f)
        except:
            pass
    return {}

def save_expiring_credits(data):
    redis_set("user_expiring_credits", data)
    try:
        with open(EXPIRING_CREDITS_FILE, 'w') as f:
            json.dump(data, f)
    except:
        pass

def load_claimed_redeem_users():
    data = redis_get("global_claimed_redeemers")
    if data is not None:
        return data
    if os.path.exists(USED_REDEEMERS_FILE):
        try:
            with open(USED_REDEEMERS_FILE, 'r') as f:
                return json.load(f)
        except:
            pass
    return []

def save_claimed_redeem_user(chat_id):
    if str(chat_id) in [str(aid) for aid in ADMIN_CHAT_IDS]:
        return
    users = load_claimed_redeem_users()
    uid = str(chat_id)
    if uid not in users:
        users.append(uid)
        redis_set("global_claimed_redeemers", users)
        try:
            with open(USED_REDEEMERS_FILE, 'w') as f:
                json.dump(users, f)
        except:
            pass

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
        except:
            pass
            
    if len(clean_grants) != len(user_grants):
        expiring_data[uid] = clean_grants
        save_expiring_credits(expiring_data)
        
    return main_bal, valid_bonus, (main_bal + valid_bonus)

def get_user_balance(chat_id):
    if str(chat_id) in [str(aid) for aid in ADMIN_CHAT_IDS]:
        return 999999999
    _, _, total_bal = get_user_balance_breakdown(chat_id)
    return total_bal

def update_user_balance(chat_id, amount_delta):
    uid = str(chat_id)
    wallets = load_all_wallets()
    
    if amount_delta > 0:
        curr = int(wallets.get(uid, 0))
        new_bal = curr + amount_delta
        wallets[uid] = new_bal
        redis_set("user_wallets_data", wallets)
        try:
            with open(WALLET_FILE, 'w') as f:
                json.dump(wallets, f)
        except:
            pass
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
        except:
            pass
            
    sorted_grants.sort(key=lambda x: x["expire_at"])
    used_bonus_days = []
    
    for g in sorted_grants:
        if needed_deduct <= 0:
            break
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
        curr_main = int(wallets.get(uid, 0))
        new_main = max(0, curr_main - needed_deduct)
        wallets[uid] = new_main
        redis_set("user_wallets_data", wallets)
        try:
            with open(WALLET_FILE, 'w') as f:
                json.dump(wallets, f)
        except:
            pass
            
    min_bonus_days = min(used_bonus_days) if used_bonus_days else None
    return get_user_balance(chat_id), min_bonus_days

def add_expiring_bonus_to_wallet(chat_id, amount, validity_days):
    uid = str(chat_id)
    now = datetime.utcnow() + timedelta(hours=6, minutes=30)
    exp_dt = now + timedelta(days=validity_days)
    
    expiring_data = load_expiring_credits()
    if uid not in expiring_data:
        expiring_data[uid] = []
        
    grant = {
        "amount": int(amount),
        "remaining": int(amount),
        "days": int(validity_days),
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
            if needed <= 0:
                break
            rem = g.get("remaining", 0)
            if rem <= needed:
                needed -= rem
                deducted += rem
                g["remaining"] = 0
            else:
                g["remaining"] -= needed
                deducted += needed
                needed = 0
        expiring_data[uid] = [g for g in user_grants if g.get("remaining", 0) > 0]
        save_expiring_credits(expiring_data)
        
    if deduct_type in ["main", "all"]:
        if deduct_type == "main":
            needed = int(amount_to_deduct)
        if needed > 0:
            wallets = load_all_wallets()
            curr_main = int(wallets.get(uid, 0))
            to_sub = min(curr_main, needed)
            wallets[uid] = curr_main - to_sub
            deducted += to_sub
            redis_set("user_wallets_data", wallets)
            try:
                with open(WALLET_FILE, 'w') as f:
                    json.dump(wallets, f)
            except:
                pass
                
    m_bal, b_bal, f_total = get_user_balance_breakdown(uid)
    return deducted, m_bal, b_bal, f_total

def set_admin_deduct_state(admin_id, state_dict=None):
    states = redis_get("admin_deduct_state") or {}
    if state_dict:
        states[str(admin_id)] = state_dict
    else:
        if str(admin_id) in states:
            del states[str(admin_id)]
    redis_set("admin_deduct_state", states)

def get_admin_deduct_state(admin_id):
    states = redis_get("admin_deduct_state") or {}
    return states.get(str(admin_id))

def set_topup_state(chat_id, amount):
    states = redis_get("user_topup_state") or {}
    if amount is not None:
        states[str(chat_id)] = amount
    else:
        if str(chat_id) in states:
            del states[str(chat_id)]
    redis_set("user_topup_state", states)

def get_topup_state(chat_id):
    states = redis_get("user_topup_state") or {}
    return states.get(str(chat_id))

def set_custom_topup_state(chat_id, is_waiting=True):
    states = redis_get("user_custom_topup") or {}
    states[str(chat_id)] = is_waiting
    redis_set("user_custom_topup", states)

def get_custom_topup_state(chat_id):
    states = redis_get("user_custom_topup") or {}
    return states.get(str(chat_id), False)

def set_renew_choice_state(chat_id, data_dict=None):
    states = redis_get("user_renew_choice") or {}
    if data_dict:
        states[str(chat_id)] = data_dict
    else:
        if str(chat_id) in states:
            del states[str(chat_id)]
    redis_set("user_renew_choice", states)

def get_renew_choice_state(chat_id):
    states = redis_get("user_renew_choice") or {}
    return states.get(str(chat_id))

# 💾 Persistent Key Storage System
def load_persistent_keys():
    data = redis_get("persistent_keys_registry")
    if data is not None:
        return data
    if os.path.exists(PERSISTENT_KEYS_FILE):
        try:
            with open(PERSISTENT_KEYS_FILE, 'r') as f:
                return json.load(f)
        except:
            pass
    return {}

def save_persistent_key(server_num, key_id, name, access_url, limit_bytes=None, order_id=None, chat_id=None):
    if not key_id or not server_num:
        return
    registry = load_persistent_keys()
    uid = f"{server_num}_{key_id}"
    
    date_match = re.search(r'\d{1,2}\.\d{1,2}\.(\d{4}|\d{2})', name)
    exp_date = date_match.group(0) if date_match else "မသိရှိပါ"
    
    existing = registry.get(uid, {})
    registry[uid] = {
        "server": str(server_num),
        "key_id": str(key_id),
        "name": name,
        "access_url": access_url if access_url else existing.get("access_url", ""),
        "limit_bytes": limit_bytes if limit_bytes else existing.get("limit_bytes"),
        "expire_date": exp_date if exp_date != "မသိရှိပါ" else existing.get("expire_date", "မသိရှိပါ"),
        "order_id": order_id if order_id else existing.get("order_id", "N/A"),
        "chat_id": str(chat_id) if chat_id else existing.get("chat_id", "")
    }
    redis_set("persistent_keys_registry", registry)
    try:
        with open(PERSISTENT_KEYS_FILE, 'w') as f:
            json.dump(registry, f)
    except:
        pass

def sync_keys_to_persistent_registry(server_num, keys_data):
    if not keys_data:
        return
    registry = load_persistent_keys()
    key_orders_map = load_key_orders()
    changed = False

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
            "server": str(server_num),
            "key_id": k_id,
            "name": k_name,
            "access_url": full_url,
            "limit_bytes": l_bytes,
            "expire_date": exp_date,
            "order_id": ord_id,
            "chat_id": cid
        }
        changed = True

    if changed:
        redis_set("persistent_keys_registry", registry)
        try:
            with open(PERSISTENT_KEYS_FILE, 'w') as f:
                json.dump(registry, f)
        except:
            pass

def sync_legacy_redis_data_to_registry():
    registry = load_persistent_keys()
    changed = False
    
    sales = load_sales_history()
    for idx, s in enumerate(sales, 1):
        s_cid = str(s.get("chat_id", ""))
        s_srv = str(s.get("server", "1"))
        s_ord = s.get("order_id", "N/A")
        p_name = s.get("plan_name", "VPN Plan")
        
        uid = f"{s_srv}_sale_{s_ord if s_ord != 'N/A' else idx}"
        if uid not in registry:
            registry[uid] = {
                "server": s_srv,
                "key_id": f"sale_{idx}",
                "name": f"{p_name} ({s_cid})" if s_cid else p_name,
                "access_url": "N/A",
                "limit_bytes": None,
                "expire_date": s.get("date", "မသိရှိပါ"),
                "order_id": s_ord,
                "chat_id": s_cid
            }
            changed = True

    orders = load_orders()
    for o_id, o_data in orders.items():
        o_cid = str(o_data.get("chat_id", ""))
        u_name = o_data.get("user_name", "Customer")
        uid = f"1_ord_{o_id}"
        if uid not in registry:
            registry[uid] = {
                "server": "1",
                "key_id": f"ord_{o_id}",
                "name": f"{u_name} ({o_cid})",
                "access_url": "N/A",
                "limit_bytes": None,
                "expire_date": o_data.get("date", "မသိရှိပါ"),
                "order_id": o_id,
                "chat_id": o_cid
            }
            changed = True

    if changed:
        redis_set("persistent_keys_registry", registry)
        try:
            with open(PERSISTENT_KEYS_FILE, 'w') as f:
                json.dump(registry, f)
        except:
            pass

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
    persistent_registry = load_persistent_keys()

    for s in user_sales:
        s_ord = s.get("order_id", "N/A")
        if s_ord != "N/A" and s_ord in known_orders:
            continue
            
        srv_num = str(s.get("server", "1"))
        matched_key_link = "N/A"
        exp_date_found = "မသိရှိပါ"
        
        for k_data in persistent_registry.values():
            if str(k_data.get("chat_id")) == str(chat_id) and str(k_data.get("server")) == srv_num:
                matched_key_link = k_data.get("access_url", "N/A")
                exp_date_found = k_data.get("expire_date", "မသိရှိပါ")
                break

        p_info = PLANS.get(s.get("plan_code"), {})
        disp_gb = p_info.get("data", "N/A")

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
        img_resp = requests.get(file_url, timeout=15)
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

def set_manual_dispatch_state(admin_id, order_info_dict=None):
    states = redis_get("admin_manual_dispatch_state") or {}
    if order_info_dict:
        states[str(admin_id)] = order_info_dict
    else:
        if str(admin_id) in states:
            del states[str(admin_id)]
    redis_set("admin_manual_dispatch_state", states)

def get_manual_dispatch_state(admin_id):
    states = redis_get("admin_manual_dispatch_state") or {}
    return states.get(str(admin_id))

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

# 🎟️ Wallet Amount Redeem Code Storage System
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
    set_manual_dispatch_state(chat_id, None)
    set_topup_state(chat_id, None)
    set_custom_topup_state(chat_id, False)
    set_admin_deduct_state(chat_id, None)
    set_renew_choice_state(chat_id, None)

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

# 🌟 Plan Configuration
PLANS = {
    "starter": {"name": "Starter Plan", "data": "25 GB", "bytes": 25 * 1000**3, "price": 1000, "manual": False, "months": 1},
    "basic": {"name": "Basic Plan", "data": "50 GB", "bytes": 50 * 1000**3, "price": 2000, "manual": False, "months": 1},
    "standard": {"name": "Standard Plan", "data": "75 GB", "bytes": 75 * 1000**3, "price": 3000, "manual": False, "months": 1},
    "premium": {"name": "Premium Plan", "data": "100 GB", "bytes": 100 * 1000**3, "price": 4000, "manual": False, "months": 1},
    "vip": {"name": "VIP Plan", "data": "150 GB", "bytes": 150 * 1000**3, "price": 5000, "manual": False, "months": 1},
    "pro": {"name": "Pro Plan", "data": "200 GB", "bytes": 200 * 1000**3, "price": 7000, "manual": False, "months": 1},
    "ultimate": {"name": "Ultimate VIP Plan", "data": "500 GB", "bytes": 500 * 1000**3, "price": 10000, "manual": False, "months": 1},
    "custom_1m": {"name": "၁ လ စိတ်ကြိုက်သုံး (5 Device)", "data": "Unlimited Data", "bytes": 0, "price": 20000, "manual": True, "months": 1},
    "custom_3m": {"name": "၃ လ စိတ်ကြိုက်သုံး (5 Device)", "data": "Unlimited Data", "bytes": 0, "price": 60000, "manual": True, "months": 3},
}

def bytes_to_gb(bytes_value):
    return round(bytes_value / (1000 ** 3), 2)

def clean_ss_url(url_str):
    if not url_str:
        return ""
    main_part = url_str.replace("ss://", "").split("#")[0].split("?")[0]
    return main_part.strip()

# 📱 ပင်မ Menu Keyboard
def get_main_menu_keyboard(chat_id=None):
    markup = ReplyKeyboardMarkup(resize_keyboard=True, row_width=2)
    btn_buy = KeyboardButton("🛍️ Plan များဝယ်ရန်")
    btn_topup = KeyboardButton("💰 ငွေဖြည့်ရန်")
    btn_wallet = KeyboardButton("💳 လက်ကျန်ငွေ")
    btn_check = KeyboardButton("🧰 Data ပမာဏစစ်ရန်")
    btn_history = KeyboardButton("📇 ဝယ်ယူမှုမှတ်တမ်း")
    btn_replace = KeyboardButton("♻️ Key လဲရန်")
    btn_admin = KeyboardButton("👨‍💻 Admin ဆက်သွယ်ရန်")
    btn_refresh = KeyboardButton("🤖 Bot Refresh")
    
    markup.add(btn_buy, btn_topup)
    markup.add(btn_wallet, btn_history)
    markup.add(btn_check, btn_replace)
    markup.add(btn_admin, btn_refresh)
    
    if chat_id and str(chat_id) in [str(aid) for aid in ADMIN_CHAT_IDS]:
        btn_total_usage = KeyboardButton("📊 Total Data Usage")
        btn_monthly_income = KeyboardButton("💰 လစဉ် ဝင်ငွေ")
        btn_gen_code = KeyboardButton("🎟️ Gen RD Code")
        btn_search_user = KeyboardButton("🔍 Cus ရှာရန်")
        btn_deduct = KeyboardButton("💸 ငွေနှုတ်ရန်")
        btn_broadcast = KeyboardButton("📢 Broadcast စာပို့ရန်")
        markup.add(btn_total_usage, btn_gen_code)
        markup.add(btn_monthly_income, btn_search_user)
        markup.add(btn_deduct, btn_broadcast)
        
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
    markup.row(InlineKeyboardButton("⚡️ ၁ လ စိတ်ကြိုက်သုံး (5 Device) - 20,000 Ks", callback_data="selectplan_custom_1m"))
    markup.row(InlineKeyboardButton("🔥 ၃ လ စိတ်ကြိုက်သုံး (5 Device) - 60,000 Ks", callback_data="selectplan_custom_3m"))
    markup.row(InlineKeyboardButton("🔙 မူလ Menu သို့ ပြန်သွားရန်", callback_data="back_to_main"))
    return markup

def get_topup_amounts_keyboard():
    markup = InlineKeyboardMarkup()
    markup.row(
        InlineKeyboardButton("💵 1,000 Ks", callback_data="topup_amt_1000"),
        InlineKeyboardButton("💵 2,000 Ks", callback_data="topup_amt_2000")
    )
    markup.row(
        InlineKeyboardButton("💵 3,000 Ks", callback_data="topup_amt_3000"),
        InlineKeyboardButton("💵 5,000 Ks", callback_data="topup_amt_5000")
    )
    markup.row(
        InlineKeyboardButton("💵 10,000 Ks", callback_data="topup_amt_10000"),
        InlineKeyboardButton("💵 20,000 Ks", callback_data="topup_amt_20000")
    )
    markup.row(
        InlineKeyboardButton("✍️ စိတ်ကြိုက်ပမာဏ ရိုက်ထည့်မည်", callback_data="topup_amt_custom")
    )
    markup.row(InlineKeyboardButton("🔙 မူလ Menu သို့ ပြန်သွားရန်", callback_data="back_to_main"))
    return markup

def get_admin_rd_amounts_keyboard():
    markup = InlineKeyboardMarkup()
    markup.row(
        InlineKeyboardButton("💵 1,000 Ks", callback_data="adm_rdamt_1000"),
        InlineKeyboardButton("💵 3,000 Ks", callback_data="adm_rdamt_3000")
    )
    markup.row(
        InlineKeyboardButton("💵 5,000 Ks", callback_data="adm_rdamt_5000"),
        InlineKeyboardButton("💵 10,000 Ks", callback_data="adm_rdamt_10000")
    )
    markup.row(InlineKeyboardButton("🔙 မူလ Menu သို့ ပြန်သွားရန်", callback_data="back_to_main"))
    return markup

def get_admin_rd_mode_keyboard(amt):
    markup = InlineKeyboardMarkup()
    markup.row(
        InlineKeyboardButton(f"👤 တစ်ဦးတည်းသုံး ({int(amt):,} Ks)", callback_data=f"adm_rdmode_{amt}_single")
    )
    markup.row(
        InlineKeyboardButton("👥 လူအများခွဲသုံး (၁၀၀၀ ~ ၃၀၀၀ Ks စီ)", callback_data=f"adm_rdmode_{amt}_shared")
    )
    markup.row(InlineKeyboardButton("🔙 ငွေပမာဏ ပြန်ရွေးရန်", callback_data="back_to_gen_rd"))
    return markup

def get_admin_rd_days_keyboard(amt, mode):
    markup = InlineKeyboardMarkup()
    markup.row(
        InlineKeyboardButton("📅 1 ရက် သက်တမ်း", callback_data=f"adm_rddur_{amt}_{mode}_1"),
        InlineKeyboardButton("📅 3 ရက် သက်တမ်း", callback_data=f"adm_rddur_{amt}_{mode}_3")
    )
    markup.row(
        InlineKeyboardButton("📅 5 ရက် သက်တမ်း", callback_data=f"adm_rddur_{amt}_{mode}_5"),
        InlineKeyboardButton("📅 7 ရက် သက်တမ်း", callback_data=f"adm_rddur_{amt}_{mode}_7")
    )
    markup.row(InlineKeyboardButton("🔙 နောက်သို့ ပြန်သွားရန်", callback_data="back_to_gen_rd"))
    return markup

def get_admin_rd_count_keyboard(amt, mode, days):
    markup = InlineKeyboardMarkup()
    markup.row(
        InlineKeyboardButton("1 ခု", callback_data=f"adm_rdcnt_{amt}_{mode}_{days}_1"),
        InlineKeyboardButton("3 ခု", callback_data=f"adm_rdcnt_{amt}_{mode}_{days}_3")
    )
    markup.row(
        InlineKeyboardButton("5 ခု", callback_data=f"adm_rdcnt_{amt}_{mode}_{days}_5"),
        InlineKeyboardButton("10 ခု", callback_data=f"adm_rdcnt_{amt}_{mode}_{days}_10")
    )
    markup.row(InlineKeyboardButton("🔙 ရက်ပေါင်း ပြန်ရွေးရန်", callback_data=f"adm_rdmode_{amt}_{mode}"))
    return markup

def get_admin_deduct_type_keyboard():
    markup = InlineKeyboardMarkup()
    markup.row(
        InlineKeyboardButton("🎁 Redeem Bonus ငွေနှုတ်မည်", callback_data="adm_deduct_type_bonus")
    )
    markup.row(
        InlineKeyboardButton("💵 လက်ကျန်ငွေ ပမာဏနှုတ်မည်", callback_data="adm_deduct_type_main")
    )
    markup.row(
        InlineKeyboardButton("⚡ စုစုပေါင်း လက်ကျန်ငွေမှ အကုန်နှုတ်မည်", callback_data="adm_deduct_type_all")
    )
    markup.row(InlineKeyboardButton("🔙 မူလ Menu သို့ ပြန်သွားရန်", callback_data="back_to_main"))
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
    vip_keys, vip_rev, vip_today_keys, vip_today_rev = 0, 0, 0, 0

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
                if is_today: s1_today_keys += 1; s1_today_rev += price
            elif srv == "2":
                s2_keys += 1
                s2_rev += price
                if is_today: s2_today_keys += 1; s2_today_rev += price
            elif srv == "3":
                s3_keys += 1
                s3_rev += price
                if is_today: s3_today_keys += 1; s3_today_rev += price
            else:
                vip_keys += 1
                vip_rev += price
                if is_today: vip_today_keys += 1; vip_today_rev += price

    total_keys = s1_keys + s2_keys + s3_keys + vip_keys
    total_rev = s1_rev + s2_rev + s3_rev + vip_rev
    today_keys = s1_today_keys + s2_today_keys + s3_today_keys + vip_today_keys
    today_rev = s1_today_rev + s2_today_rev + s3_today_rev + vip_today_rev

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
        f"📡 <b>Server 1 🇸🇬 :</b> <b>{s1_rev:,} Ks</b> ({s1_keys} ခု)\n"
        f"📡 <b>Server 2 🇸🇬 :</b> <b>{s2_rev:,} Ks</b> ({s2_keys} ခု)\n"
        f"📡 <b>Server 3 🇸🇬 :</b> <b>{s3_rev:,} Ks</b> ({s3_keys} ခု)\n"
        f"⚡ <b>VIP (စိတ်ကြိုက်သုံး) :</b> <b>{vip_rev:,} Ks</b> ({vip_keys} ခု)\n\n"
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
            keys_resp = requests.get(f"{api_url}/access-keys", verify=False, timeout=15)
            metrics_resp = requests.get(f"{api_url}/metrics/transfer", verify=False, timeout=15)

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

def get_customer_summary_stats():
    s1_users = set()
    s2_users = set()
    s3_users = set()
    total_unique_users = set()

    for srv_num, api_url in [("1", OUTLINE_API_URL_1), ("2", OUTLINE_API_URL_2), ("3", OUTLINE_API_URL_3)]:
        try:
            res = requests.get(f"{api_url}/access-keys", verify=False, timeout=15)
            if res.status_code == 200:
                keys = res.json().get("accessKeys", [])
                for k in keys:
                    k_name = k.get("name", "").strip()
                    cid_match = re.search(r'\((\d+)\)', k_name)
                    identifier = cid_match.group(1) if cid_match else k_name.lower()
                    if identifier:
                        if srv_num == "1": s1_users.add(identifier)
                        elif srv_num == "2": s2_users.add(identifier)
                        elif srv_num == "3": s3_users.add(identifier)
                        total_unique_users.add(identifier)
        except:
            pass

    try:
        sync_legacy_redis_data_to_registry()
    except:
        pass

    persistent_registry = load_persistent_keys()
    for k_data in persistent_registry.values():
        cid = k_data.get("chat_id")
        k_name = k_data.get("name", "").strip()
        srv = str(k_data.get("server", "1"))
        identifier = cid if cid else k_name.lower()
        if identifier:
            if srv == "1": s1_users.add(identifier)
            elif srv == "2": s2_users.add(identifier)
            elif srv == "3": s3_users.add(identifier)
            total_unique_users.add(identifier)

    summary_text = (
        f"👥 <b>လက်ရှိ Customer စာရင်း အကျဉ်းချုပ်</b>\n\n"
        f"📡 Server 1 🇸🇬 : <b>{len(s1_users)}</b> ယောက်\n"
        f"📡 Server 2 🇸🇬 : <b>{len(s2_users)}</b> ယောက်\n"
        f"📡 Server 3 🇸🇬 : <b>{len(s3_users)}</b> ယောက်\n"
        f"━━━━━━━━━━━━━━━━━\n"
        f"🌟 <b>စုစုပေါင်း Customer ဦးရေ:</b> <b>{len(total_unique_users)}</b> ယောက်\n\n"
        f"👇 ရှာဖွေလိုသော <b>Cus နာမည်အစ စာလုံး (ဥပမာ - H, T, A) သို့မဟုတ် Chat ID / Order ID</b> ကို ဒီ Chat ထဲသို့ ရိုက်ပို့ပေးပါခင်ဗျာ:"
    )
    return summary_text

def search_users_by_query(query):
    query_clean = query.strip().lower()
    markup = InlineKeyboardMarkup()
    found_matches = []
    seen_identifiers = set()
    key_orders_map = load_key_orders()

    try:
        sync_legacy_redis_data_to_registry()
    except:
        pass

    for server_num, api_url in [("1", OUTLINE_API_URL_1), ("2", OUTLINE_API_URL_2), ("3", OUTLINE_API_URL_3)]:
        try:
            res = requests.get(f"{api_url}/access-keys", verify=False, timeout=15)
            if res.status_code == 200:
                keys = res.json().get("accessKeys", [])
                sync_keys_to_persistent_registry(server_num, keys)
                for k in keys:
                    k_name = k.get("name", "").strip()
                    k_name_lower = k_name.lower()
                    assigned_ord = key_orders_map.get(k_name_lower, "").lower()
                    k_id = str(k.get("id"))
                    uid = f"{server_num}_{k_id}"

                    if len(query_clean) == 1:
                        if k_name_lower.startswith(query_clean):
                            found_matches.append((server_num, k_id, k_name))
                            seen_identifiers.add(uid)
                    else:
                        if query_clean in k_name_lower or (assigned_ord and query_clean in assigned_ord):
                            found_matches.append((server_num, k_id, k_name))
                            seen_identifiers.add(uid)
        except:
            pass

    persistent_registry = load_persistent_keys()
    for uid, k_data in persistent_registry.items():
        if uid in seen_identifiers:
            continue
            
        k_name = k_data.get("name", "")
        k_name_lower = k_name.lower()
        k_ord = k_data.get("order_id", "").lower()
        srv_num = k_data.get("server", "1")
        k_id = k_data.get("key_id", "0")
        k_cid = k_data.get("chat_id", "").lower()

        if len(query_clean) == 1:
            if k_name_lower.startswith(query_clean):
                found_matches.append((srv_num, k_id, k_name))
                seen_identifiers.add(uid)
        else:
            if query_clean in k_name_lower or (k_ord and query_clean in k_ord) or (k_cid and query_clean in k_cid):
                found_matches.append((srv_num, k_id, k_name))
                seen_identifiers.add(uid)

    for server_num, key_id, k_name in found_matches[:30]:
        srv_icon = f"📡 S{server_num}🇸🇬" if server_num != "VIP" else "⚡ VIP 🇸🇬"
        btn_text = f"{srv_icon} | {k_name}"
        markup.add(InlineKeyboardButton(btn_text, callback_data=f"viewkey_{server_num}_{key_id}"))

    return found_matches, markup

# 🔙 Back to Main Menu Callback Handler
@bot.callback_query_handler(func=lambda call: call.data == "back_to_main")
def handle_back_to_main_callback(call):
    try:
        bot.answer_callback_query(call.id, "🔙 မူလ Menu သို့ ပြန်သွားပါပြီ။")
    except:
        pass
    chat_id = call.message.chat.id
    clear_all_states(chat_id)
    try:
        bot.delete_message(chat_id, call.message.message_id)
    except:
        pass
    welcome_text = (
        "👋 မင်္ဂလာပါ! H & E FEATURE PREMIUM VPN ဝန်ဆောင်မှု Bot မှ ကြိုဆိုပါတယ်။\n\n"
        "👇 အောက်ခြေက Menu Button တွေကို အသုံးပြုပြီး မိမိတို့ အလိုရှိရာကို ရွေးချယ်နိုင်ပါတယ်ခင်ဗျာ။"
    )
    bot.send_message(chat_id, welcome_text, reply_markup=get_main_menu_keyboard(chat_id))

# 🔙 Admin Back to Gen RD Code Handler
@bot.callback_query_handler(func=lambda call: call.data == "back_to_gen_rd")
def handle_back_to_gen_rd(call):
    try:
        bot.answer_callback_query(call.id)
    except:
        pass
    user_id = str(call.from_user.id)
    chat_id = str(call.message.chat.id)
    if user_id not in [str(aid) for aid in ADMIN_CHAT_IDS] and chat_id not in [str(aid) for aid in ADMIN_CHAT_IDS]:
        return
    try:
        bot.edit_message_text(
            "🎟️ <b>Wallet Amount Redeem Code ထုတ်ရန်:</b>\n\nကျေးဇူးပြု၍ မည်သည့် <b>ငွေပမာဏ</b> အတွက် Code ထုတ်ယူမည်ကို ရွေးချယ်ပေးပါခင်ဗျာ:",
            chat_id=call.message.chat.id,
            message_id=call.message.message_id,
            parse_mode="HTML",
            reply_markup=get_admin_rd_amounts_keyboard()
        )
    except Exception:
        bot.send_message(call.message.chat.id, "🎟️ <b>Wallet Amount Redeem Code ထုတ်ရန်:</b>", parse_mode="HTML", reply_markup=get_admin_rd_amounts_keyboard())

@bot.callback_query_handler(func=lambda call: call.data.startswith("adm_rdamt_"))
def handle_admin_rd_amt_select(call):
    try:
        bot.answer_callback_query(call.id)
    except:
        pass
    user_id = str(call.from_user.id)
    chat_id = str(call.message.chat.id)
    if user_id not in [str(aid) for aid in ADMIN_CHAT_IDS] and chat_id not in [str(aid) for aid in ADMIN_CHAT_IDS]:
        return
    
    amt = int(call.data.replace("adm_rdamt_", ""))
    
    try:
        if amt in [5000, 10000]:
            prompt = (
                f"🎟️ <b>{amt:,} Ks Wallet Redeem Code</b>\n\n"
                f"မည်သည့် ပုံစံဖြင့် ထုတ်ယူလိုပါသလဲ ရွေးချယ်ပေးပါခင်ဗျာ:"
            )
            bot.edit_message_text(
                prompt,
                chat_id=call.message.chat.id,
                message_id=call.message.message_id,
                parse_mode="HTML",
                reply_markup=get_admin_rd_mode_keyboard(amt)
            )
        else:
            prompt = f"🎟️ <b>{amt:,} Ks (တစ်ဦးတည်းသုံး)</b> အတွက် ရရှိမည့် Wallet ငွေ၏ <b>သက်တမ်း (ရက်)</b> ရွေးချယ်ပေးပါခင်ဗျာ:"
            bot.edit_message_text(
                prompt,
                chat_id=call.message.chat.id,
                message_id=call.message.message_id,
                parse_mode="HTML",
                reply_markup=get_admin_rd_days_keyboard(amt, "single")
            )
    except Exception:
        pass

@bot.callback_query_handler(func=lambda call: call.data.startswith("adm_rdmode_"))
def handle_admin_rd_mode_select(call):
    try:
        bot.answer_callback_query(call.id)
    except:
        pass
    user_id = str(call.from_user.id)
    chat_id = str(call.message.chat.id)
    if user_id not in [str(aid) for aid in ADMIN_CHAT_IDS] and chat_id not in [str(aid) for aid in ADMIN_CHAT_IDS]:
        return
    
    parts = call.data.split("_")
    amt = parts[2]
    mode = parts[3]
    
    mode_text = "တစ်ဦးတည်းသုံး" if mode == "single" else "လူအများခွဲသုံး (၁၀၀၀ ~ ၃၀၀၀ Ks စီ)"
    prompt = f"🎟️ <b>{int(amt):,} Ks ({mode_text})</b> အတွက် ရရှိမည့် Wallet ငွေ၏ <b>သက်တမ်း (ရက်)</b> ရွေးချယ်ပေးပါခင်ဗျာ:"
    try:
        bot.edit_message_text(
            prompt,
            chat_id=call.message.chat.id,
            message_id=call.message.message_id,
            parse_mode="HTML",
            reply_markup=get_admin_rd_days_keyboard(amt, mode)
        )
    except Exception:
        pass

@bot.callback_query_handler(func=lambda call: call.data.startswith("adm_rddur_"))
def handle_admin_rd_days_select(call):
    try:
        bot.answer_callback_query(call.id)
    except:
        pass
    user_id = str(call.from_user.id)
    chat_id = str(call.message.chat.id)
    if user_id not in [str(aid) for aid in ADMIN_CHAT_IDS] and chat_id not in [str(aid) for aid in ADMIN_CHAT_IDS]:
        return
    
    parts = call.data.split("_")
    amt = parts[2]
    mode = parts[3]
    days = parts[4]
    
    mode_text = "တစ်ဦးတည်းသုံး" if mode == "single" else "လူအများခွဲသုံး"
    prompt = f"🎟️ <b>{int(amt):,} Ks ({mode_text} - ငွေသက်တမ်း {days} ရက်)</b> အတွက် မည်မျှအရေအတွက် Code ထုတ်ယူလိုပါသလဲ?"
    try:
        bot.edit_message_text(
            prompt,
            chat_id=call.message.chat.id,
            message_id=call.message.message_id,
            parse_mode="HTML",
            reply_markup=get_admin_rd_count_keyboard(amt, mode, days)
        )
    except Exception:
        pass

@bot.callback_query_handler(func=lambda call: call.data.startswith("adm_rdcnt_"))
def handle_admin_rd_generate(call):
    try:
        bot.answer_callback_query(call.id, "✅ Code များထုတ်ပြီးပါပြီ!")
    except:
        pass
    if is_callback_processed(f"adm_rdgen_{call.message.message_id}_{call.data}"):
        return

    user_id = str(call.from_user.id)
    chat_id = str(call.message.chat.id)
    if user_id not in [str(aid) for aid in ADMIN_CHAT_IDS] and chat_id not in [str(aid) for aid in ADMIN_CHAT_IDS]:
        return
    
    parts = call.data.split("_")
    amt = int(parts[2])
    mode = parts[3]
    days = int(parts[4])
    count = int(parts[5])
    
    codes = load_redeem_codes()
    generated_list = []
    
    for _ in range(count):
        code = generate_random_redeem_code()
        codes[code] = {
            "type": "wallet",
            "amount": amt,
            "mode": mode,
            "remaining": amt,
            "validity_days": days,
            "claimed_users": []
        }
        generated_list.append(f"<code>{code}</code>")
        
    save_redeem_codes(codes)
    
    if mode == "shared":
        mode_desc = f"လူအများခွဲသုံး (၁၀၀၀ ~ ၃၀၀၀ Ks စီ)"
    else:
        mode_desc = f"တစ်ဦးတည်းသုံး ({amt:,} Ks အပြည့်)"

    reply_msg = (
        f"🎉 <b>Wallet Amount Redeem Code ({count} ခု) အောင်မြင်စွာ ထုတ်ပြီးပါပြီ:</b>\n\n"
        f"💵 သတ်မှတ်ငွေ: <b>{amt:,} MMK</b>\n"
        f"📌 ပုံစံ: <b>{mode_desc}</b>\n"
        f"⏰ Wallet ငွေ သက်တမ်း: <b>{days} ရက်</b>\n\n"
        + "\n".join(generated_list) +
        f"\n\n💡 <i>Customer များသည် Wallet Menu ထဲရှိ '🎟️ Redeem Code သုံးမည်' တွင် ထည့်သွင်းပြီး {days} ရက်အတွင်း အသုံးပြုနိုင်ပါပြီဗျာ။ (အဆိုပါငွေဖြင့် ဝယ်ယူသော Key သက်တမ်းသည်လည်း {days} ရက် ဖြစ်ပါမည်)</i>"
    )
    try:
        bot.edit_message_text(reply_msg, chat_id=call.message.chat.id, message_id=call.message.message_id, parse_mode="HTML", reply_markup=get_back_inline_keyboard())
    except Exception:
        bot.send_message(call.message.chat.id, reply_msg, parse_mode="HTML", reply_markup=get_back_inline_keyboard())

@bot.callback_query_handler(func=lambda call: call.data.startswith("adm_deduct_type_"))
def handle_admin_deduct_type_select(call):
    try:
        bot.answer_callback_query(call.id)
    except:
        pass
    user_id = str(call.from_user.id)
    if user_id not in [str(aid) for aid in ADMIN_CHAT_IDS]:
        return

    dtype = call.data.replace("adm_deduct_type_", "")
    set_admin_deduct_state(call.message.chat.id, {"type": dtype, "step": "ask_user"})

    type_name = "Redeem Bonus ငွေ" if dtype == "bonus" else ("လက်ကျန်ငွေ ပမာဏ" if dtype == "main" else "စုစုပေါင်း လက်ကျန်ငွေ")
    prompt = (
        f"💸 <b>{type_name} နှုတ်ယူရန်:</b>\n\n"
        f"👇 ငွေနှုတ်လိုသော Customer ၏ <b>Telegram Chat ID</b> ကို ဒီ Chat ထဲသို့ ရိုက်ပို့ပေးပါခင်ဗျာ:"
    )
    bot.edit_message_text(prompt, chat_id=call.message.chat.id, message_id=call.message.message_id, parse_mode="HTML", reply_markup=get_back_inline_keyboard())

@bot.callback_query_handler(func=lambda call: call.data.startswith("viewkey_"))
def handle_view_key_detail(call):
    try:
        bot.answer_callback_query(call.id)
    except:
        pass
    if str(call.message.chat.id) not in [str(aid) for aid in ADMIN_CHAT_IDS]:
        return
    
    parts = call.data.split("_")
    server_num = parts[1]
    key_id = parts[2]
    
    api_url = OUTLINE_API_URL_1 if server_num == "1" else (OUTLINE_API_URL_2 if server_num == "2" else OUTLINE_API_URL_3)
    api_url = api_url.rstrip('/')
    
    target_key = None
    bytes_transferred = {}

    try:
        keys_resp = requests.get(f"{api_url}/access-keys", verify=False, timeout=15)
        if keys_resp.status_code == 200:
            keys_data = keys_resp.json().get("accessKeys", [])
            for k in keys_data:
                if str(k.get("id")) == str(key_id):
                    target_key = k
                    break
                    
            if target_key:
                try:
                    metrics_resp = requests.get(f"{api_url}/metrics/transfer", verify=False, timeout=15)
                    if metrics_resp.status_code == 200:
                        bytes_transferred = metrics_resp.json().get("bytesTransferredByUserId", {})
                except:
                    pass
    except Exception as e:
        print("Live fetch error, switching to persistent cache:", e)

    cached_info = None
    if not target_key:
        persistent_registry = load_persistent_keys()
        cached_info = persistent_registry.get(f"{server_num}_{key_id}")
        
    if target_key or cached_info:
        if target_key:
            full_name = target_key.get("name", "Unnamed Key")
            raw_access_url = target_key.get("accessUrl", "")
            final_key = f"{raw_access_url}#{full_name}" if full_name else raw_access_url
            limit_bytes = target_key.get("dataLimit", {}).get("bytes")
            plan_gb = f"{bytes_to_gb(limit_bytes)} GB" if limit_bytes else "Unlimited"
            
            usage_bytes = bytes_transferred.get(str(key_id), 0)
            usage_gb = f"{bytes_to_gb(usage_bytes)} GB" if bytes_transferred else "ဒေတာဖတ်မရပါ"
            
            date_match = re.search(r'\d{1,2}\.\d{1,2}\.(\d{4}|\d{2})', full_name)
            end_date = date_match.group(0) if date_match else "မသိရှိပါ"
            order_id_disp = get_order_id_for_key(full_name)
            server_name = f"Server {server_num} 🇸🇬"
        else:
            full_name = cached_info.get("name", "Unnamed Key")
            final_key = cached_info.get("access_url", "N/A")
            l_b = cached_info.get("limit_bytes")
            plan_gb = f"{bytes_to_gb(l_b)} GB" if l_b else "Unlimited"
            usage_gb = "ဆာဗာလိုင်းမရသဖြင့် မသိရှိနိုင်ပါ"
            end_date = cached_info.get("expire_date", "မသိရှိပါ")
            order_id_disp = cached_info.get("order_id", "N/A")
            server_name = f"Server {server_num} 🇸🇬 <i>(⚠️ ဆာဗာ Offline ဖြစ်နေပါသည်)</i>"

        order_line = f"🧾 <b>Order ID:</b> <code>{order_id_disp}</code>\n" if order_id_disp != "N/A" else ""
        markup = InlineKeyboardMarkup()
        markup.add(InlineKeyboardButton("🗑️ Key ဖျက်ရန် (Delete)", callback_data=f"delkey_ask_{server_num}_{key_id}"))

        detail_msg = (
            f"👤 <b>Customer Information✅</b>\n\n"
            f"🤖 <b>Name:</b> {html.escape(full_name)}\n"
            f"{order_line}"
            f"📡 <b>Server:</b> {server_name}\n"
            f"🧰 <b>Data Usage :</b> <code>{usage_gb}</code> / <code>{plan_gb}</code>\n"
            f"⏰ <b>Expired Date:</b> {end_date}\n"
            f"🔑 <b>VPN Key Link:</b>\n\n"
            f"<code>{final_key}</code>"
        )
        bot.send_message(call.message.chat.id, detail_msg, parse_mode="HTML", reply_markup=markup)
    else:
        bot.send_message(call.message.chat.id, "❌ အဆိုပါ Key ၏ အချက်အလက်များကို ဆာဗာနှင့် မှတ်တမ်းများထဲတွင် ရှာမတွေ့ပါခင်ဗျာ။")

@bot.callback_query_handler(func=lambda call: call.data.startswith("delkey_"))
def handle_admin_del_key(call):
    try:
        bot.answer_callback_query(call.id)
    except:
        pass
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
        persistent_registry = load_persistent_keys()
        uid = f"{server_num}_{key_id}"
        if uid in persistent_registry:
            del persistent_registry[uid]
            redis_set("persistent_keys_registry", persistent_registry)

        api_url = OUTLINE_API_URL_1 if server_num == "1" else (OUTLINE_API_URL_2 if server_num == "2" else OUTLINE_API_URL_3)
        try:
            del_res = requests.delete(f"{api_url}/access-keys/{key_id}", verify=False, timeout=15)
            bot.edit_message_text(f"✅ <b>Server {server_num} ပေါ်မှ Key (ID: {key_id}) အား အောင်မြင်စွာ ဖျက်ဆီးပြီးပါပြီဗျာ။</b>", chat_id=call.message.chat.id, message_id=call.message.message_id, parse_mode="HTML")
        except:
            bot.edit_message_text(f"✅ <b>မှတ်တမ်းများထဲမှ Key (ID: {key_id}) အား ဖျက်ဆီးပြီးပါပြီ။ (Server Down နေသဖြင့် Server ဘက်သို့ သီးသန့် အမိန့်မရောက်ခဲ့ပါ)</b>", chat_id=call.message.chat.id, message_id=call.message.message_id, parse_mode="HTML")

    elif action == "cancel":
        bot.edit_message_text("❌ Key ဖျက်ခြင်းကို ပယ်ဖျက်လိုက်ပါပြီခင်ဗျာ။", chat_id=call.message.chat.id, message_id=call.message.message_id)

@app.route('/cron-check', methods=['GET', 'POST'])
def cron_check():
    today = (datetime.utcnow() + timedelta(hours=6, minutes=30)).date()
    
    key_mappings = load_key_mappings()
    notified_count = 0
    deleted_count = 0

    for api_url in [OUTLINE_API_URL_1, OUTLINE_API_URL_2, OUTLINE_API_URL_3]:
        try:
            keys_resp = requests.get(f"{api_url}/access-keys", verify=False, timeout=15)
            metrics_resp = requests.get(f"{api_url}/metrics/transfer", verify=False, timeout=15)
            
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

                if should_delete:
                    try:
                        del_res = requests.delete(f"{api_url}/access-keys/{key_id}", verify=False, timeout=15)
                        if del_res.status_code in [200, 204]:
                            deleted_count += 1
                            for aid in ADMIN_CHAT_IDS:
                                try:
                                    bot.send_message(
                                        aid, 
                                        f"🗑️ <b>Customer Key Expired:</b>\n\nKey: <code>{full_name}</code> သည် သက်တမ်းကုန်ဆုံးပြီး ကျော်လွန်သွားပါသဖြင့် Server ပေါ်မှ အလိုအလျောက် ဖျက်ဆီးလိုက်ပါပြီခင်ဗျာ။", 
                                        parse_mode="HTML"
                                    )
                                except:
                                    pass
                    except:
                        pass
                    continue 

                if is_gb_full or is_expired_today:
                    target_chat_id = extract_chat_id_from_key_name(full_name)
                    if not target_chat_id:
                        id_match = re.search(r'\((\d{8,12})\)', full_name)
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
                                f"ဆက်လက် အသုံးပြုလိုပါက Bot ၏ '🛍️ Plan များဝယ်ရန်' မှတစ်ဆင့် ပြန်လည် ဝယ်ယူနိုင်ပါတယ်ဗျာ။ 🙏"
                            )
                            bot.send_message(target_chat_id, user_noti, parse_mode="HTML")
                            notified_count += 1
                        except:
                            pass

                    admin_noti = (
                        f"📢 <b>Customer သိပေးချက်</b>\n"
                        f"👤 အသုံးပြုသူ: {full_name}\n"
                        f"⚠️ အခြေအနေ: {reason_text}\n"
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
