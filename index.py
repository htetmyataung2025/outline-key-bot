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
            keys_resp = requests.get(f"{api_url}/access-keys", verify=False, timeout=6)
            metrics_resp = requests.get(f"{api_url}/metrics/transfer", verify=False, timeout=6)

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
            res = requests.get(f"{api_url}/access-keys", verify=False, timeout=4)
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
            res = requests.get(f"{api_url}/access-keys", verify=False, timeout=4)
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
    chat_id = call.message.chat.id
    clear_all_states(chat_id)
    bot.answer_callback_query(call.id, "🔙 မူလ Menu သို့ ပြန်သွားပါပြီ။")
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
    bot.answer_callback_query(call.id)
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
    bot.answer_callback_query(call.id)
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
    bot.answer_callback_query(call.id)
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
    bot.answer_callback_query(call.id)
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
    bot.answer_callback_query(call.id, "✅ Code များထုတ်ပြီးပါပြီ!")
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
    bot.answer_callback_query(call.id)
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
    bot.answer_callback_query(call.id)
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
        keys_resp = requests.get(f"{api_url}/access-keys", verify=False, timeout=4)
        if keys_resp.status_code == 200:
            keys_data = keys_resp.json().get("accessKeys", [])
            for k in keys_data:
                if str(k.get("id")) == str(key_id):
                    target_key = k
                    break
                    
            if target_key:
                try:
                    metrics_resp = requests.get(f"{api_url}/metrics/transfer", verify=False, timeout=4)
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
        persistent_registry = load_persistent_keys()
        uid = f"{server_num}_{key_id}"
        if uid in persistent_registry:
            del persistent_registry[uid]
            redis_set("persistent_keys_registry", persistent_registry)

        api_url = OUTLINE_API_URL_1 if server_num == "1" else (OUTLINE_API_URL_2 if server_num == "2" else OUTLINE_API_URL_3)
        try:
            del_res = requests.delete(f"{api_url}/access-keys/{key_id}", verify=False, timeout=8)
            bot.edit_message_text(f"✅ <b>Server {server_num} ပေါ်မှ Key (ID: {key_id}) အား အောင်မြင်စွာ ဖျက်ဆီးပြီးပါပြီဗျာ။</b>", chat_id=call.message.chat.id, message_id=call.message.message_id, parse_mode="HTML")
        except:
            bot.edit_message_text(f"✅ <b>မှတ်တမ်းများထဲမှ Key (ID: {key_id}) အား ဖျက်ဆီးပြီးပါပြီ။ (Server Down နေသဖြင့် Server ဘက်သို့ သီးသန့် အမိန့်မရောက်ခဲ့ပါ)</b>", chat_id=call.message.chat.id, message_id=call.message.message_id, parse_mode="HTML")

    elif action == "cancel":
        bot.edit_message_text("❌ Key ဖျက်ခြင်းကို ပယ်ဖျက်လိုက်ပါပြီခင်ဗျာ။", chat_id=call.message.chat.id, message_id=call.message.message_id)

def get_user_next_key_number(user_name, target_chat_id=None):
    max_num = 0
    found_any = False
    clean_user = user_name.strip().lower()

    persistent_registry = load_persistent_keys()
    for k_data in persistent_registry.values():
        k_name = k_data.get("name", "")
        if (target_chat_id and f"({target_chat_id})" in k_name) or (clean_user in k_name.lower()):
            found_any = True
            num_match = re.search(r'\((\d+)\)\s*\d{1,2}\.\d{1,2}\.', k_name)
            if not num_match:
                num_match = re.search(r'\((\d+)\)', k_name)

            if num_match:
                try:
                    val = int(num_match.group(1))
                    if str(val) != str(target_chat_id) and val > max_num:
                        max_num = val
                except:
                    pass

    for api_url in [OUTLINE_API_URL_1, OUTLINE_API_URL_2, OUTLINE_API_URL_3]:
        try:
            res = requests.get(f"{api_url}/access-keys", verify=False, timeout=4)
            if res.status_code == 200:
                keys = res.json().get("accessKeys", [])
                for k in keys:
                    k_name = k.get("name", "")
                    if (target_chat_id and f"({target_chat_id})" in k_name) or (clean_user in k_name.lower()):
                        found_any = True
                        num_match = re.search(r'\((\d+)\)\s*\d{1,2}\.\d{1,2}\.', k_name)
                        if not num_match:
                            num_match = re.search(r'\((\d+)\)', k_name)

                        if num_match:
                            try:
                                val = int(num_match.group(1))
                                if str(val) != str(target_chat_id) and val > max_num:
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

def get_user_ultimate_keys(chat_id, server_num="1"):
    api_url = OUTLINE_API_URL_1 if str(server_num) == "1" else (OUTLINE_API_URL_2 if str(server_num) == "2" else OUTLINE_API_URL_3)
    user_keys = []
    try:
        res = requests.get(f"{api_url}/access-keys", verify=False, timeout=6)
        if res.status_code == 200:
            keys_data = res.json().get("accessKeys", [])
            for k in keys_data:
                k_name = k.get("name", "")
                if f"({chat_id})" in k_name and not "[gw]" in k_name.lower():
                    user_keys.append({
                        "id": k.get("id"),
                        "name": k_name,
                        "server": str(server_num)
                    })
    except:
        pass
    return user_keys

def renew_specific_unlimited_key(server_num, key_id, months_count=1, custom_days=None, order_id=None):
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
            
            target_key = None
            for k in keys_data:
                if str(k.get("id")) == str(key_id):
                    target_key = k
                    break
            
            if target_key:
                target_key_name = target_key.get("name", "")
                used_bytes = bytes_transferred.get(str(key_id), 0)
                new_fup_limit = used_bytes + add_bytes

                updated_name = re.sub(r'\d{1,2}\.\d{1,2}\.(\d{4}|\d{2})$', new_expire_date, target_key_name)
                if updated_name == target_key_name:
                    updated_name = f"{target_key_name.split('(')[0].strip()} {new_expire_date}"
                
                requests.put(f"{api_url}/access-keys/{key_id}/name", data={"name": updated_name}, verify=False, timeout=8)
                requests.put(f"{api_url}/access-keys/{key_id}/data-limit", json={"limit": {"bytes": new_fup_limit}}, verify=False, timeout=8)
                
                if order_id:
                    map_key_to_order(updated_name, order_id)

                raw_access_url = target_key.get("accessUrl", "")
                final_key = f"{raw_access_url}#{updated_name}"
                save_persistent_key(server_num, key_id, updated_name, final_key, new_fup_limit, order_id)
                return final_key, updated_name, new_expire_date
    except Exception as e:
        print("Specific Unlimited Renewal Error:", e)
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
                save_persistent_key(server_num, target_key_id, updated_name, final_key, new_fup_limit, order_id, target_chat_id)
                return final_key, updated_name, new_expire_date, True
    except Exception as e:
        print("Unlimited Renewal Error:", e)

    vpn_key, key_name, expire_date = create_outline_key(server_num, user_name, plan_info={"bytes": add_bytes}, target_chat_id=target_chat_id, months_count=months_count, custom_days=custom_days, is_giveaway=False, order_id=order_id)
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
    crown_str = " 👑" if str(target_chat_id) in [str(aid) for aid in ADMIN_CHAT_IDS] else ""
    
    if curr_max == 0:
        key_name = f"{user_name}{crown_str}{id_str}{gw_str} {expire_date}"
    else:
        key_name = f"{user_name}{crown_str}{id_str}{gw_str} ({next_number}) {expire_date}"
    
    api_url = OUTLINE_API_URL_1 if str(server_num) == "1" else (OUTLINE_API_URL_2 if str(server_num) == "2" else OUTLINE_API_URL_3)
    
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
                limit_bytes = plan_info.get("bytes", 0) * months_count

            if limit_bytes and limit_bytes > 0:
                requests.put(f"{api_url}/access-keys/{key_id}/data-limit", json={"limit": {"bytes": limit_bytes}}, verify=False, timeout=8)
            
            if order_id:
                map_key_to_order(key_name, order_id)

            raw_access_url = key_data.get("accessUrl", "")
            final_key = f"{raw_access_url}#{key_name}"
            
            save_persistent_key(server_num, key_id, key_name, final_key, limit_bytes, order_id, target_chat_id)
            return final_key, key_name, expire_date
    except Exception as e:
        print("Key Generation Error:", e)
    return None, None, None

def generate_random_redeem_code():
    chars = string.ascii_lowercase + string.digits
    return ''.join(random.choices(chars, k=10))

# ----------------- FORCE JOIN CHANNEL CALLBACK HANDLER -----------------
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
            "👇 အောက်ခြေက Menu Button တွေကို အသုံးပြုပြီး မိမိတို့ အလိုရှိရာကို ရွေးချယ်နိုင်ပါတယ်ခင်ဗျာ။"
        )
        bot.send_message(chat_id, welcome_text, reply_markup=get_main_menu_keyboard(chat_id))
    else:
        bot.answer_callback_query(call.id, "❌ Channel ထဲသို့ မဝင်ရောက်ရသေးပါခင်ဗျာ။ အရင်ဆုံး Join ပေးပါ။", show_alert=True)

# ----------------- COMMAND HANDLERS -----------------
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
        "👇 အောက်ခြေက Menu Button တွေကို အသုံးပြုပြီး မိမိတို့ အလိုရှိရာကို ရွေးချယ်နိုင်ပါတယ်ခင်ဗျာ။"
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

# 👮‍♂️ Admin Fund Deduction Command (/deduct <chat_id> <amount>)
@bot.message_handler(commands=['deduct'])
def handle_admin_deduct_command(message):
    chat_id = str(message.chat.id)
    if chat_id not in [str(aid) for aid in ADMIN_CHAT_IDS]:
        return

    parts = message.text.strip().split()
    if len(parts) < 3:
        usage_msg = (
            "⚠️ <b>ငွေပြန်နှုတ်ခြင်း Command အသုံးပြုပုံ:</b>\n\n"
            "👉 <code>/deduct &lt;Chat_ID&gt; &lt;ငွေပမာဏ&gt;</code>\n"
            "ဥပမာ- <code>/deduct 6818712501 2000</code>"
        )
        bot.reply_to(message, usage_msg, parse_mode="HTML")
        return

    target_id = parts[1].strip()
    amt_str = parts[2].strip()

    if not amt_str.isdigit():
        bot.reply_to(message, "❌ ငွေပမာဏကို ဂဏန်းသီးသန့်သာ ရိုက်ထည့်ပါခင်ဗျာ။")
        return

    amt = int(amt_str)
    deducted, m_bal, b_bal, final_bal = admin_deduct_specific_funds(target_id, amt, deduct_type="all")

    bot.reply_to(
        message,
        f"✅ <b>ငွေပြန်နှုတ်ခြင်း အောင်မြင်ပါသည်!</b>\n\n"
        f"👤 Target User ID: <code>{target_id}</code>\n"
        f"💵 နှုတ်ယူငွေ: <b>-{deducted:,} MMK</b>\n"
        f"💳 User ၏ လက်ရှိ ကျန်ငွေ: <b>{final_bal:,} MMK</b> (လက်ကျန်ငွေ ပမာဏ: {m_bal:,} Ks | Redeem: {b_bal:,} Ks)",
        parse_mode="HTML"
    )

    try:
        user_alert = (
            f"⚠️ <b>အသိပေးချက်:</b>\n\n"
            f"လူကြီးမင်း၏ Wallet ထဲမှ မမှန်ကန်သော နည်းလမ်းဖြင့် ရယူထားသော ပမာဏ (<b>-{deducted:,} MMK</b>) အား Admin မှ ပြန်လည်နှုတ်ယူလိုက်ပါသည်ခင်ဗျာ။\n\n"
            f"💳 လက်ရှိ သုံးနိုင်သော စုစုပေါင်း လက်ကျန်ငွေ: <b>{final_bal:,} MMK</b>"
        )
        bot.send_message(target_id, user_alert, parse_mode="HTML")
    except:
        pass

# 🎟️ Redeem Code Command
@bot.message_handler(commands=['redeem'])
def handle_redeem_command(message):
    chat_id = message.chat.id
    save_user_id(chat_id)
    clear_all_states(chat_id)
    if not is_user_subscribed(chat_id):
        send_force_join_message(chat_id)
        return

    is_admin = str(chat_id) in [str(aid) for aid in ADMIN_CHAT_IDS]
    if not is_admin:
        _, bonus_bal, _ = get_user_balance_breakdown(chat_id)
        if bonus_bal > 0:
            bot.send_message(
                chat_id,
                f"⚠️ <b>ခွင့်လွှတ်ပါခင်ဗျာ၊ လူကြီးမင်းတွင် လက်ရှိ အသုံးပြုနိုင်သော Redeem Bonus လက်ကျန်ငွေ ({bonus_bal:,} MMK) ရှိနေဆဲ ဖြစ်ပါသဖြင့် နောက်ထပ် Code အသစ်ကို ထပ်မံ ရယူခွင့် မရှိသေးပါခင်ဗျာ။</b>\n\n"
                f"💡 <i>အဆိုပါငွေဖြင့် Plan ဝယ်ယူအသုံးပြုပြီးမှ (သို့မဟုတ် ရက်စေ့ကုန်ဆုံးသွားမှ) သာ နောက်ထပ် Code ကို ထပ်မံ ရယူနိုင်ပါမည်။</i>",
                parse_mode="HTML",
                reply_markup=get_back_inline_keyboard()
            )
            return

    set_redeem_state(chat_id, True)
    bot.send_message(
        chat_id,
        "🎟️ <b>Wallet Redeem Code အသုံးပြုရန်:</b>\n\n"
        "👇 Admin ထံမှ ရရှိထားသော Redeem Code (ဥပမာ- <code>a8k2m9x4p1</code>) ကို ဒီ Chat ထဲသို့ Paste ချပို့ပေးပါခင်ဗျာ:",
        parse_mode="HTML",
        reply_markup=get_back_inline_keyboard()
    )

# ----------------- WALLET & DIRECT PURCHASE HANDLERS -----------------

def get_payment_instruction_text(amt):
    return (
        f"✅ <b>Wallet ထဲသို့ ငွေဖြည့်သွင်းရန်</b>\n"
        f"💵 ဖြည့်သွင်းမည့် ပမာဏ: <b>{amt:,} Ks</b>\n\n"
        f"━━━━━━━━━━━━━━━\n"
        f"💰 <b>ငွေလွှဲရမည့် အကောင့်အချက်အလက်များ:</b>\n\n"
        f"📱 <b>KBZ Pay</b> - <code>09699970092</code>\n"
        f"👤 Htet Myat Aung\n\n"
        f"📱 <b>Wave Pay</b> - <code>09699970092</code>\n"
        f"👤 Htet Myat Aung\n\n"
        f"📱 <b>AYA Pay</b> - <code>09699970092</code>\n"
        f"👤 Htet Myat Aung\n\n"
        f"📱 <b>Uab Pay</b> - <code>09699970092</code>\n"
        f"👤 Htet Myat Aung\n\n"
        f"📱 <b>CB Pay</b> - <code>09699970092</code>\n"
        f"👤 Htet Myat Aung\n\n"
        f"━━━━━━━━━━━━━━━\n\n"
        f"👉 အထက်ပါ အကောင့်တစ်ခုခုသို့ <b>{amt:,} Ks</b> တိတိကျကျ လွှဲပေးပါခင်ဗျာ။\n\n"
        f"🙏🏻 ငွေလွှဲပြီး 📸 <b>Screenshot (ပြေစာ)</b> လေး ပို့ပေးပါခင်ဗျာ🥰\n\n"
        f"<i>Admin မှ ပြေစာစစ်ဆေးအတည်ပြုပြီးသည်နှင့် Wallet ထဲသို့ ချက်ချင်း ငွေထည့်သွင်းပေးပါမည်။ ကျေးဇူးတင်ပါသည်ခင်ဗျာ။ 🙏</i>"
    )

@bot.callback_query_handler(func=lambda call: call.data.startswith("topup_amt_"))
def handle_topup_amount_select(call):
    bot.answer_callback_query(call.id)
    chat_id = call.message.chat.id
    raw_val = call.data.replace("topup_amt_", "")
    
    if raw_val == "custom":
        set_custom_topup_state(chat_id, True)
        set_topup_state(chat_id, None)
        custom_prompt = (
            "✍️ <b>စိတ်ကြိုက်ငွေပမာဏ ရိုက်ထည့်ရန်:</b>\n\n"
            "👇 ဖြည့်သွင်းလိုသော ငွေပမာဏကို ဂဏန်းသီးသန့် (ဥပမာ- <code>15000</code> သို့မဟုတ် <code>50000</code>) ရိုက်ပို့ပေးပါခင်ဗျာ:"
        )
        markup = InlineKeyboardMarkup()
        markup.row(InlineKeyboardButton("🔙 ငွေပမာဏ ပြန်ရွေးရန်", callback_data="btn_open_topup"))
        markup.row(InlineKeyboardButton("🔙 မူလ Menu သို့ ပြန်သွားရန်", callback_data="back_to_main"))
        bot.edit_message_text(custom_prompt, chat_id=chat_id, message_id=call.message.message_id, parse_mode="HTML", reply_markup=markup)
        return

    amt = int(raw_val)
    set_topup_state(chat_id, amt)
    set_custom_topup_state(chat_id, False)
    
    payment_text = get_payment_instruction_text(amt)
    markup = InlineKeyboardMarkup()
    markup.row(InlineKeyboardButton("🔙 ငွေပမာဏ ပြန်ရွေးရန်", callback_data="btn_open_topup"))
    markup.row(InlineKeyboardButton("🔙 မူလ Menu သို့ ပြန်သွားရန်", callback_data="back_to_main"))
    bot.edit_message_text(payment_text, chat_id=chat_id, message_id=call.message.message_id, parse_mode="HTML", reply_markup=markup)

@bot.callback_query_handler(func=lambda call: call.data == "btn_open_topup")
def handle_btn_open_topup(call):
    bot.answer_callback_query(call.id)
    set_custom_topup_state(call.message.chat.id, False)
    bot.edit_message_text(
        "💰 <b>Wallet ထဲသို့ ဖြည့်သွင်းလိုသော ငွေပမာဏကို ရွေးချယ်ပေးပါ:</b>",
        chat_id=call.message.chat.id,
        message_id=call.message.message_id,
        parse_mode="HTML",
        reply_markup=get_topup_amounts_keyboard()
    )

@bot.callback_query_handler(func=lambda call: call.data.startswith("approve_topup_"))
def handle_approve_topup(call):
    lock_key = f"appr_topup_{call.message.message_id}_{call.data}"
    if is_callback_processed(lock_key):
        bot.answer_callback_query(call.id, "⚠️ ငွေဖြည့်ပေးပြီးပါပြီ။")
        return

    if str(call.message.chat.id) not in [str(aid) for aid in ADMIN_CHAT_IDS]:
        return

    parts = call.data.split("_")
    target_chat_id = parts[2]
    amount = int(parts[3])
    topup_id = parts[4]

    new_balance, _ = update_user_balance(target_chat_id, amount)
    bot.answer_callback_query(call.id, f"✅ {amount:,} Ks ဖြည့်သွင်းပေးပြီးပါပြီ။")

    user_noti = (
        f"🎉 <b>ငွေဖြည့်သွင်းမှု အောင်မြင်ပါသည်!</b>\n\n"
        f"🧾 Top-Up ID: <code>{topup_id}</code>\n\n"
        f"💵 ဖြည့်သွင်းငွေ: <b>+{amount:,} MMK</b>\n\n"
        f"💳 လက်ရှိ Wallet လက်ကျန်ငွေ: <b>{new_balance:,} MMK</b>\n\n"
        f"'🛍️ Plan များဝယ်ရန်' Menu မှတစ်ဆင့် VPN Key များကို အချိန်မရွေး စိတ်ကြိုက် ချက်ချင်း ဝယ်ယူနိုင်ပါပြီခင်ဗျာ!"
    )
    try:
        bot.send_message(target_chat_id, user_noti, parse_mode="HTML")
    except:
        pass

    updated_caption = call.message.caption + f"\n\n✅ <b>APPROVED (+{amount:,} MMK)</b>"
    try:
        bot.edit_message_caption(chat_id=call.message.chat.id, message_id=call.message.message_id, caption=updated_caption, parse_mode="HTML", reply_markup=None)
    except:
        pass

# Customer Plan Review & Choice Logic for Ultimate VIP
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
        balance = get_user_balance(chat_id)
        is_admin = str(chat_id) in [str(aid) for aid in ADMIN_CHAT_IDS]
        
        _, bonus_bal, _ = get_user_balance_breakdown(chat_id)
        has_redeem_credit = (bonus_bal > 0) and not is_admin

        # 🌟 Ultimate VIP Plan အတွက် ကီးရှိနေလျှင် (၁ ခုဖြစ်စေ၊ များစွာဖြစ်စေ) သက်တမ်းတိုးရန် သို့မဟုတ် အသစ်ဝယ်ရန် ရွေးချယ်ခွင့်ပေးခြင်း
        if plan_code == "ultimate" and not has_redeem_credit:
            user_keys = get_user_ultimate_keys(chat_id, "1")
            if len(user_keys) > 0:
                markup = InlineKeyboardMarkup()
                for idx, uk in enumerate(user_keys, 1):
                    markup.row(InlineKeyboardButton(f"♻️ Key #{idx} ({uk['name'][:25]}) သက်တမ်းတိုးမည်", callback_data=f"renew_choice_{plan_code}_1_{uk['id']}"))
                markup.row(InlineKeyboardButton("➕ Key အသစ် အစအဆုံး ထပ်ဝယ်မည်", callback_data=f"renew_choice_{plan_code}_1_new"))
                markup.row(InlineKeyboardButton("🔙 Plan များသို့ ပြန်သွားရန်", callback_data="back_to_plans"))
                markup.row(InlineKeyboardButton("🔙 မူလ Menu သို့ ပြန်သွားရန်", callback_data="back_to_main"))

                choice_text = (
                    f"🌌 <b>Ultimate VIP Plan ဝယ်ယူခြင်း</b>\n\n"
                    f"💡 လူကြီးမင်းတွင် လက်ရှိ Active ဖြစ်နေသော Ultimate VIP Key <b>({len(user_keys)} ခု)</b> ရှိနေသည်ကို တွေ့ရှိရပါသည်။\n\n"
                    f"👇 အောက်ပါတို့မှ <b>သက်တမ်းတိုးမည့် Key အဟောင်း</b> ကို ရွေးချယ်ပါ (သို့မဟုတ်) <b>ကီးအသစ် အစအဆုံး ဝယ်ယူရန်</b> ရွေးချယ်ပေးပါခင်ဗျာ:"
                )
                try:
                    bot.edit_message_text(choice_text, chat_id=chat_id, message_id=call.message.message_id, parse_mode="HTML", reply_markup=markup)
                except Exception:
                    bot.send_message(chat_id, choice_text, parse_mode="HTML", reply_markup=markup)
                return

        markup = InlineKeyboardMarkup()
        if balance >= amount or is_admin:
            if plan.get("manual"):
                markup.row(InlineKeyboardButton(f"💳 Wallet ဖြင့် တန်းဝယ်မည် ({amount:,} Ks)", callback_data=f"buywallet_{plan_code}_VIP"))
            elif plan_code == "ultimate" or has_redeem_credit:
                srv1_label = "📡 Server 1 🇸🇬 (Redeem Credit)" if has_redeem_credit else "📡 Server 1 🇸🇬 (Main Server) ဖြင့် ဝယ်မည်"
                markup.row(InlineKeyboardButton(srv1_label, callback_data=f"buywallet_{plan_code}_1"))
            else:
                markup.row(InlineKeyboardButton("📡 Server 1 🇸🇬 ဖြင့် ဝယ်မည်", callback_data=f"buywallet_{plan_code}_1"))
                markup.row(InlineKeyboardButton("📡 Server 2 🇸🇬 ဖြင့် ဝယ်မည်", callback_data=f"buywallet_{plan_code}_2"))
                markup.row(InlineKeyboardButton("📡 Server 3 🇸🇬 ဖြင့် ဝယ်မည်", callback_data=f"buywallet_{plan_code}_3"))
        else:
            shortfall = amount - balance
            markup.row(InlineKeyboardButton(f"💰 ငွေ {shortfall:,} Ks ထပ်ဖြည့်ရန်", callback_data="btn_open_topup"))
            
        markup.row(InlineKeyboardButton("🔙 Plan များသို့ ပြန်သွားရန်", callback_data="back_to_plans"))
        markup.row(InlineKeyboardButton("🔙 မူလ Menu သို့ ပြန်သွားရန်", callback_data="back_to_main"))

        balance_disp = "♾️ Unlimited" if is_admin else f"{balance:,} MMK"
        balance_status = "✅ ဝယ်ယူရန် လုံလောက်ပါသည်" if (balance >= amount or is_admin) else f"⚠️ ငွေမလုံလောက်ပါ (ထပ်ဖြည့်ရန်: {amount - balance:,} Ks)"
        
        server_notice = "\n💡 <i>(Redeem ငွေ လက်ကျန်ပါရှိသဖြင့် Server 1 မှသာ ထုတ်ပေးမည် ဖြစ်ပါသည်)</i>" if has_redeem_credit else ""

        text = (
            f"🛍️ <b>ဝယ်ယူမည့် Plan အချက်အလက်</b>\n\n"
            f"📮 <b>Plan:</b> {plan['name']}\n\n"
            f"🗃️ <b>Data:</b> {plan['data']}\n\n"
            f"💵 <b>ကျသင့်ငွေ:</b> {amount:,} MMK\n\n"
            f"━━━━━━━━━━━━━━━\n"
            f"💳 <b>လူကြီးမင်း၏ လက်ကျန်ငွေ:</b> <b>{balance_disp}</b>\n"
            f"အခြေအနေ: <b>{balance_status}</b>\n"
            f"━━━━━━━━━━━━━━━\n{server_notice}\n"
            f"👇 ဝယ်ယူလိုပါက အောက်ပါ ဆာဗာခလုတ်များမှ မိမိနှစ်သက်ရာကို ရွေးချယ်နှိပ်ပါခင်ဗျာ:"
        )
        try:
            bot.edit_message_text(text, chat_id=chat_id, message_id=call.message.message_id, parse_mode="HTML", reply_markup=markup)
        except Exception:
            bot.send_message(chat_id, text, parse_mode="HTML", reply_markup=markup)

# 🌟 Ultimate VIP Key Choice Handler (Key အဟောင်းတိုးမည်လား၊ အသစ်ဝယ်မည်လား)
@bot.callback_query_handler(func=lambda call: call.data.startswith("renew_choice_"))
def handle_renew_choice(call):
    bot.answer_callback_query(call.id)
    chat_id = call.message.chat.id
    parts = call.data.split("_")
    plan_code = parts[2]
    server_num = parts[3]
    choice_val = parts[4]

    plan = PLANS.get(plan_code)
    if not plan:
        return

    amount = plan["price"]
    balance = get_user_balance(chat_id)
    is_admin = str(chat_id) in [str(aid) for aid in ADMIN_CHAT_IDS]

    if not is_admin and balance < amount:
        bot.answer_callback_query(call.id, "❌ လက်ကျန်ငွေ မလုံလောက်ပါ။", show_alert=True)
        return

    order_id = "#" + "".join(random.choices(string.ascii_uppercase + string.digits, k=6))
    new_bal, used_bonus_days = update_user_balance(chat_id, -amount)
    
    chat_info = bot.get_chat(chat_id)
    user_first = chat_info.first_name if chat_info.first_name else ""
    user_last = chat_info.last_name if chat_info.last_name else ""
    user_name = f"{user_first} {user_last}".strip() or "HMA Customer"

    bot.answer_callback_query(call.id, "⏳ VPN Key ဆောင်ရွက်နေပါသည်...")

    vpn_key = None
    key_name = None
    expire_date = None
    disp_gb = plan["data"]
    apply_days = None if is_admin else used_bonus_days

    if choice_val == "new":
        vpn_key, key_name, expire_date = create_outline_key(server_num, user_name, plan_info=plan, target_chat_id=chat_id, months_count=1, custom_days=apply_days, is_giveaway=False, order_id=order_id)
    else:
        today = datetime.now()
        if apply_days:
            expire_date = (today + timedelta(days=apply_days)).strftime("%d.%m.%Y")
        else:
            expire_date = (today + relativedelta(months=1)).strftime("%d.%m.%Y")
        
        vpn_key, key_name, expire_date = renew_specific_unlimited_key(server_num, choice_val, months_count=1, custom_days=apply_days, order_id=order_id)

    if not vpn_key:
        update_user_balance(chat_id, amount)
        bot.send_message(chat_id, "❌ ဆာဗာလိုင်းမရသဖြင့် မဆောင်ရွက်နိုင်ပါ။ ငွေအား ပြန်လည်ထည့်သွင်းပေးထားပါသည်။", reply_markup=get_back_inline_keyboard())
        return

    save_sale_transaction(server_num, chat_id, plan_code, plan['name'], 1, amount, order_id=order_id)
    save_user_purchase_record(
        chat_id=chat_id,
        order_id=order_id,
        plan_name=plan['name'],
        disp_gb=disp_gb,
        months_count=1,
        price_str=f"{amount:,} Ks",
        server_num=server_num,
        expire_date=expire_date,
        vpn_key=vpn_key
    )

    clean_name = user_name.strip().lower()
    save_key_mapping(clean_name, chat_id)

    exp_info_text = f"⏰ <b>သက်တမ်းကုန်ဆုံးရက်:</b> {expire_date}"
    if apply_days:
        exp_info_text += f" <i>(Redeem Wallet ငွေအလိုက် {apply_days} ရက် သက်တမ်း)</i>"

    user_disp_bal = "♾️ Unlimited" if is_admin else f"{new_bal:,} MMK"
    success_text = (
        f"🎉 <b>ဝယ်ယူမှု အောင်မြင်ပါသည်ခင်ဗျာ!</b>\n\n"
        f"🧾 <b>Order ID:</b> <code>{order_id}</code>\n\n"
        f"🛍️ <b>Plan:</b> {plan['name']} ({disp_gb})\n\n"
        f"📡 <b>Server:</b> Singapore Server {server_num} 🇸🇬\n\n"
        f"{exp_info_text}\n\n"
        f"💳 <b>ကျန်ရှိသော လက်ကျန်ငွေ:</b> <code>{user_disp_bal}</code>\n\n"
        f"🔑 <b>လူကြီးမင်း၏ VPN Key:</b>\n\n"
        f"<code>{vpn_key}</code>\n\n"
        f"☝️ အပေါ်က Key ကို <b>တစ်ချက်တည်း နှိပ်လိုက်ရုံဖြင့်</b> Auto Copy ကူးသွားပါလိမ့်မယ်ခင်ဗျာ။ V2BOX VPN App ထဲသို့ ထည့်သွင်းအသုံးပြုနိုင်ပါပြီ။"
    )
    try:
        bot.edit_message_text(success_text, chat_id=chat_id, message_id=call.message.message_id, parse_mode="HTML", reply_markup=get_back_inline_keyboard())
    except Exception:
        bot.send_message(chat_id, success_text, parse_mode="HTML", reply_markup=get_back_inline_keyboard())

@bot.callback_query_handler(func=lambda call: call.data.startswith("buywallet_"))
def handle_buy_with_wallet(call):
    chat_id = call.message.chat.id
    lock_key = f"buy_wallet_{call.message.message_id}_{call.data}"
    if is_callback_processed(lock_key):
        bot.answer_callback_query(call.id, "⚠️ စာရင်းလုပ်ဆောင်နေပါသည်...")
        return

    parts = call.data.split("_")
    plan_code = parts[1]
    server_num = parts[2]
    plan = PLANS.get(plan_code)

    if not plan:
        bot.answer_callback_query(call.id, "❌ Plan ရှာမတွေ့ပါ။")
        return

    amount = plan["price"]
    balance = get_user_balance(chat_id)
    is_admin = str(chat_id) in [str(aid) for aid in ADMIN_CHAT_IDS]

    if not is_admin and balance < amount:
        bot.answer_callback_query(call.id, "❌ လက်ကျန်ငွေ မလုံလောက်ပါ။ ကျေးဇူးပြု၍ ငွေအရင်ဖြည့်ပေးပါ။", show_alert=True)
        return

    bot.answer_callback_query(call.id, "⏳ VPN Key ထုတ်ပေးနေပါသည်...")

    order_id = "#" + "".join(random.choices(string.ascii_uppercase + string.digits, k=6))
    new_bal, used_bonus_days = update_user_balance(chat_id, -amount)
    
    chat_info = bot.get_chat(chat_id)
    user_first = chat_info.first_name if chat_info.first_name else ""
    user_last = chat_info.last_name if chat_info.last_name else ""
    user_name = f"{user_first} {user_last}".strip() or "HMA Customer"

    if plan.get("manual"):
        save_sale_transaction("VIP", chat_id, plan_code, plan["name"], plan.get("months", 1), amount, order_id=order_id)
        
        admin_alert = (
            f"⚡ <b>စိတ်ကြိုက်သုံး 5 Device Plan အော်ဒါအသစ် (ငွေပေးချေပြီး)</b>\n\n"
            f"🧾 Order ID: <code>{order_id}</code>\n"
            f"👤 ဝယ်ယူသူ: {user_name}\n"
            f"🆔 Chat ID: <code>{chat_id}</code>\n"
            f"🛍️ Plan: <b>{plan['name']}</b>\n"
            f"💵 ဖြတ်တောက်ပြီးငွေ: <b>{amount:,} MMK</b>\n\n"
            f"👇 အောက်ပါခလုတ်ကိုနှိပ်၍ Key အား ပေးပို့ပေးပါခင်ဗျာ:"
        )
        markup = InlineKeyboardMarkup()
        markup.add(InlineKeyboardButton("🔑 Send Key to Customer", callback_data=f"ask_send_key_{chat_id}_{order_id}"))
        
        for aid in ADMIN_CHAT_IDS:
            try:
                bot.send_message(aid, admin_alert, parse_mode="HTML", reply_markup=markup)
            except:
                pass

        user_disp_bal = "♾️ Unlimited" if is_admin else f"{new_bal:,} MMK"
        user_msg = (
            f"🎉 <b>အော်ဒါမှာယူမှု အောင်မြင်ပါသည်!</b>\n\n"
            f"🧾 <b>Order ID:</b> <code>{order_id}</code>\n"
            f"🛍️ <b>Plan:</b> {plan['name']}\n"
            f"💵 <b>ကျသင့်ငွေ:</b> -{amount:,} MMK\n"
            f"💳 <b>လက်ကျန်ငွေ:</b> {user_disp_bal}\n\n"
            f"💡 <i>ဤ Plan သည် စိတ်ကြိုက်သုံး Plan ဖြစ်သဖြင့် Admin မှ ခေတ္တအတွင်း Key အား ပြင်ဆင်၍ ပို့ပေးပါမည်ခင်ဗျာ။ စောင့်ဆိုင်းပေးပါရန် မေတ္တာရပ်ခံအပ်ပါသည်။</i>"
        )
        try:
            bot.edit_message_text(user_msg, chat_id=chat_id, message_id=call.message.message_id, parse_mode="HTML", reply_markup=get_back_inline_keyboard())
        except Exception:
            bot.send_message(chat_id, user_msg, parse_mode="HTML", reply_markup=get_back_inline_keyboard())
        return
    
    vpn_key = None
    key_name = None
    expire_date = None
    disp_gb = plan["data"]

    apply_days = None if is_admin else used_bonus_days

    if plan_code == "ultimate":
        vpn_key, key_name, expire_date, _ = renew_or_create_unlimited_key(server_num, user_name, chat_id, months_count=1, custom_days=apply_days, order_id=order_id)
    else:
        vpn_key, key_name, expire_date = create_outline_key(server_num, user_name, plan_info=plan, target_chat_id=chat_id, months_count=1, custom_days=apply_days, is_giveaway=False, order_id=order_id)

    if not vpn_key:
        update_user_balance(chat_id, amount)
        bot.send_message(chat_id, "❌ ဆာဗာလိုင်းမရသဖြင့် Key မွေးမရပါ။ ကျသင့်ငွေအား Wallet ထဲသို့ ပြန်လည် ထည့်သွင်းပေးထားပါသည်။", reply_markup=get_back_inline_keyboard())
        return

    save_sale_transaction(server_num, chat_id, plan_code, plan['name'], 1, amount, order_id=order_id)
    save_user_purchase_record(
        chat_id=chat_id,
        order_id=order_id,
        plan_name=plan['name'],
        disp_gb=disp_gb,
        months_count=1,
        price_str=f"{amount:,} Ks",
        server_num=server_num,
        expire_date=expire_date,
        vpn_key=vpn_key
    )

    clean_name = user_name.strip().lower()
    save_key_mapping(clean_name, chat_id)

    exp_info_text = f"⏰ <b>သက်တမ်းကုန်ဆုံးရက်:</b> {expire_date}"
    if apply_days:
        exp_info_text += f" <i>(Redeem Wallet ငွေအလိုက် {apply_days} ရက် သက်တမ်း)</i>"

    user_disp_bal = "♾️ Unlimited" if is_admin else f"{new_bal:,} MMK"
    success_text = (
        f"🎉 <b>ဝယ်ယူမှု အောင်မြင်ပါသည်ခင်ဗျာ!</b>\n\n"
        f"🧾 <b>Order ID:</b> <code>{order_id}</code>\n\n"
        f"🛍️ <b>Plan:</b> {plan['name']} ({disp_gb})\n\n"
        f"📡 <b>Server:</b> Singapore Server {server_num} 🇸🇬\n\n"
        f"{exp_info_text}\n\n"
        f"💳 <b>ကျန်ရှိသော လက်ကျန်ငွေ:</b> <code>{user_disp_bal}</code>\n\n"
        f"🔑 <b>လူကြီးမင်း၏ VPN Key:</b>\n\n"
        f"<code>{vpn_key}</code>\n\n"
        f"☝️ အပေါ်က Key ကို <b>တစ်ချက်တည်း နှိပ်လိုက်ရုံဖြင့်</b> Auto Copy ကူးသွားပါလိမ့်မယ်ခင်ဗျာ။ V2BOX VPN App ထဲသို့ ထည့်သွင်းအသုံးပြုနိုင်ပါပြီ။"
    )
    try:
        bot.edit_message_text(success_text, chat_id=chat_id, message_id=call.message.message_id, parse_mode="HTML", reply_markup=get_back_inline_keyboard())
    except Exception:
        bot.send_message(chat_id, success_text, parse_mode="HTML", reply_markup=get_back_inline_keyboard())

    for aid in ADMIN_CHAT_IDS:
        try:
            bot.send_message(
                aid,
                f"🛍️ <b>Instant Auto Purchase Alert</b>\n\n"
                f"🧾 Order ID: <code>{order_id}</code>\n"
                f"👤 Customer: {user_name} (ID: <code>{chat_id}</code>)\n"
                f"🛍️ Plan: {plan['name']}\n"
                f"📡 Server: Server {server_num}\n"
                f"💵 ရရှိငွေ: {amount:,} MMK\n"
                f"⏰ သက်တမ်း: {expire_date} ({f'Redeem ငွေဖြင့် {apply_days} ရက်' if apply_days else '၁ လပြည့်'})",
                parse_mode="HTML"
            )
        except:
            pass

@bot.callback_query_handler(func=lambda call: call.data == "back_to_plans")
def handle_back_to_plans(call):
    bot.answer_callback_query(call.id)
    chat_id = call.message.chat.id
    bot.edit_message_text(
        "🧸 ကျေးဇူးပြု၍ ဝယ်ယူလိုသော VPN Plan ကို ရွေးချယ်ပေးပါခင်ဗျာ:",
        chat_id=chat_id,
        message_id=call.message.message_id,
        reply_markup=get_plan_keyboard()
    )

# 🔑 Admin Manual Key Send Callback
@bot.callback_query_handler(func=lambda call: call.data.startswith("ask_send_key_"))
def handle_ask_send_key_callback(call):
    bot.answer_callback_query(call.id)
    if str(call.message.chat.id) not in [str(aid) for aid in ADMIN_CHAT_IDS]:
        return
    
    parts = call.data.split("_")
    target_chat_id = parts[3]
    order_id = parts[4]
    
    order_info = {
        "target_chat_id": target_chat_id,
        "order_id": order_id,
        "plan_name": "စိတ်ကြိုက်သုံး Plan (5 Device)",
        "disp_gb": "Unlimited Data (5 Device)",
        "months": 1
    }
    set_manual_dispatch_state(call.message.chat.id, order_info)
    
    prompt_txt = (
        f"🔑 <b>Customer ထံ ပို့ပေးမည့် Key Link (သို့မဟုတ် စာသား) အား ပေးပို့ပါ:</b>\n\n"
        f"🧾 Order ID: <code>{order_id}</code>\n"
        f"👤 Chat ID: <code>{target_chat_id}</code>\n\n"
        f"👇 အောက်တွင် မိမိထုတ်ထားသော VPN Key Link အား Paste ချ၍ ပေးပို့ပေးပါခင်ဗျာ -"
    )
    bot.send_message(call.message.chat.id, prompt_txt, parse_mode="HTML", reply_markup=get_back_inline_keyboard())

# 🎟️ Redeem Code Trigger Callback
@bot.callback_query_handler(func=lambda call: call.data == "btn_open_redeem")
def handle_btn_open_redeem(call):
    bot.answer_callback_query(call.id)
    chat_id = call.message.chat.id

    is_admin = str(chat_id) in [str(aid) for aid in ADMIN_CHAT_IDS]
    if not is_admin:
        _, bonus_bal, _ = get_user_balance_breakdown(chat_id)
        if bonus_bal > 0:
            bot.send_message(
                chat_id,
                f"⚠️ <b>ခွင့်လွှတ်ပါခင်ဗျာ၊ လူကြီးမင်းတွင် လက်ရှိ အသုံးပြုနိုင်သော Redeem Bonus လက်ကျန်ငွေ ({bonus_bal:,} MMK) ရှိနေဆဲ ဖြစ်ပါသဖြင့် နောက်ထပ် Code အသစ်ကို ထပ်မံ ရယူခွင့် မရှိသေးပါခင်ဗျာ။</b>\n\n"
                f"💡 <i>အဆိုပါငွေဖြင့် Plan ဝယ်ယူအသုံးပြုပြီးမှ (သို့မဟုတ် ရက်စေ့ကုန်ဆုံးသွားမှ) သာ နောက်ထပ် Code အသစ်ကို ရယူနိုင်ပါမည်ခင်ဗျာ။</i>",
                parse_mode="HTML",
                reply_markup=get_back_inline_keyboard()
            )
            return

    set_redeem_state(chat_id, True)
    redeem_guide = (
        "🎟️ <b>Wallet Redeem Code အသုံးပြုရန်:</b>\n\n"
        "👇 Admin ထံမှ ရရှိထားသော Redeem Code (ဥပမာ- <code>a8k2m9x4p1</code>) ကို ဒီ Chat ထဲသို့ Paste ချပို့ပေးပါခင်ဗျာ:"
    )
    bot.send_message(chat_id, redeem_guide, parse_mode="HTML", reply_markup=get_back_inline_keyboard())

# 📸 Photo Message Handler
@bot.message_handler(content_types=['photo'])
def handle_photo_messages(message):
    chat_id = message.chat.id
    save_user_id(chat_id)

    if not is_user_subscribed(chat_id):
        send_force_join_message(chat_id)
        return

    # Admin Broadcast Photo
    if str(chat_id) in [str(aid) for aid in ADMIN_CHAT_IDS] and get_broadcast_state(chat_id):
        set_broadcast_state(chat_id, False)
        all_users = load_all_users()
        success_count = 0
        photo_id = message.photo[-1].file_id
        caption_text = message.caption or ""

        bot.send_message(chat_id, f"⏳ ပုံပါသော Broadcast စာအား User စုစုပေါင်း ({len(all_users)}) ဆီ အကုန် ပို့ပေးနေပါသည်...")
        for uid in all_users:
            if str(uid) in [str(aid) for aid in ADMIN_CHAT_IDS]: continue
            try:
                bot.send_photo(uid, photo_id, caption=caption_text, parse_mode="HTML")
                success_count += 1
            except:
                pass
        bot.send_message(chat_id, f"✅ <b>Broadcast ပို့ပြီးပါပြီ!</b>\n\nရောက်ရှိသူ: <b>{success_count} / {len(all_users)}</b>", parse_mode="HTML")
        return

    # Top-Up Slip Handler
    user_first = message.from_user.first_name if message.from_user.first_name else ""
    user_last = message.from_user.last_name if message.from_user.last_name else ""
    user_name = f"{user_first} {user_last}".strip() or "HMA User"
    username = f"@{message.from_user.username}" if message.from_user.username else "No Username"
    
    topup_amt = get_topup_state(chat_id) or 1000
    set_topup_state(chat_id, None)
    set_custom_topup_state(chat_id, False)

    photo_file = bot.get_file(message.photo[-1].file_id)
    topup_id = generate_order_id_from_slip(photo_file.file_path)

    admin_alert_text = (
        f"💰 <b>ငွေဖြည့်ပြေစာအသစ် (Top-Up Request)</b>\n\n"
        f"🧾 Top-Up ID: <code>{topup_id}</code>\n\n"
        f"👤 အသုံးပြုသူ: {user_name} ({username})\n\n"
        f"💵 ဖြည့်သွင်းငွေပမာဏ: <b>{topup_amt:,} MMK</b>\n\n"
        f"🆔 User Chat ID: <code>{chat_id}</code>\n\n"
        f"<i>စစ်ဆေးပြီးပါက အောက်ပါ Approve ခလုတ်ကို နှိပ်၍ ငွေထည့်သွင်းပေးပါခင်ဗျာ။</i>"
    )
    
    markup = InlineKeyboardMarkup()
    markup.add(InlineKeyboardButton(f"✅ Approve (+{topup_amt:,} MMK)", callback_data=f"approve_topup_{chat_id}_{topup_amt}_{topup_id}"))

    for aid in ADMIN_CHAT_IDS:
        try:
            bot.send_photo(aid, message.photo[-1].file_id, caption=admin_alert_text, parse_mode="HTML", reply_markup=markup)
        except:
            pass

    user_reply = (
        f"💌 <b>ငွေလွှဲပြေစာအား လက်ခံရရှိပါသည်ခင်ဗျာ။</b>\n\n"
        f"🧾 <b>Top-Up ID:</b> <code>{topup_id}</code>\n\n"
        f"💵 <b>ငွေပမာဏ:</b> {topup_amt:,} MMK\n\n"
        f"<i>Admin မှ ပြေစာစစ်ဆေးအတည်ပြုပြီးသည်နှင့် Wallet ထဲသို့ ချက်ချင်း ငွေထည့်ပေးပါမည်။ ကျေးဇူးတင်ပါသည်ခင်ဗျာ။ 🙏</i>"
    )
    bot.reply_to(message, user_reply, parse_mode="HTML")

# ⚡️ Fetch Key From Server
def fetch_key_from_server(api_url, input_value):
    if not api_url or "dummyKey" in api_url:
        return None, None, None
        
    api_url = api_url.rstrip('/')
    server_num = "1" if api_url == OUTLINE_API_URL_1.rstrip('/') else ("2" if api_url == OUTLINE_API_URL_2.rstrip('/') else "3")
    
    try:
        keys_resp = requests.get(f"{api_url}/access-keys", verify=False, timeout=5)
        bytes_transferred = {}
        try:
            metrics_resp = requests.get(f"{api_url}/metrics/transfer", verify=False, timeout=4)
            if metrics_resp.status_code == 200:
                bytes_transferred = metrics_resp.json().get("bytesTransferredByUserId", {})
        except:
            bytes_transferred = {}
        
        if keys_resp.status_code == 200:
            keys_data = keys_resp.json().get("accessKeys", [])
            sync_keys_to_persistent_registry(server_num, keys_data)
            
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
                return target_key, bytes_transferred, server_num
    except Exception as e:
        print(f"Fetch Key Error on {api_url}:", e)
        
    persistent_registry = load_persistent_keys()
    input_raw = input_value.strip().lower()
    for uid, k_data in persistent_registry.items():
        if k_data.get("server") == server_num:
            k_name = k_data.get("name", "").lower()
            acc_url = k_data.get("access_url", "").lower()
            if (input_raw.startswith("ss://") and clean_ss_url(input_raw) in clean_ss_url(acc_url)) or (input_raw in k_name):
                dummy_key = {
                    "id": k_data.get("key_id"),
                    "name": k_data.get("name"),
                    "accessUrl": k_data.get("access_url", "").split("#")[0],
                    "dataLimit": {"bytes": k_data.get("limit_bytes")} if k_data.get("limit_bytes") else {}
                }
                return dummy_key, {}, server_num

    return None, None, None

# 🔄 Admin Key Replacement Approval Callback Handler
@bot.callback_query_handler(func=lambda call: call.data.startswith("replace_"))
def handle_admin_replace_callback(call):
    lock_key = f"repl_{call.message.message_id}_{call.data}"
    if is_callback_processed(lock_key):
        bot.answer_callback_query(call.id, "⚠️ လုပ်ဆောင်ပြီးပါပြီ။")
        return

    if str(call.message.chat.id) not in [str(aid) for aid in ADMIN_CHAT_IDS]:
        return

    parts = call.data.split("_")
    action = parts[1]

    if action == "reject":
        target_chat_id = parts[2]
        try:
            bot.send_message(target_chat_id, "❌ <b>လူကြီးမင်း တောင်းဆိုထားသော Key အစားထိုးခြင်းအား Admin မှ ငြင်းပယ်လိုက်ပါသည်ခင်ဗျာ။</b>", parse_mode="HTML")
        except:
            pass
        bot.edit_message_text(call.message.text + "\n\n❌ <b>REJECTED</b>", chat_id=call.message.chat.id, message_id=call.message.message_id, parse_mode="HTML")
        return

    new_server_num = parts[1].replace("srv", "")
    old_server_num = parts[2]
    old_key_id = parts[3]
    target_chat_id = parts[4]
    rem_gb = float(parts[5])
    exp_date = parts[6]

    api_url_old = OUTLINE_API_URL_1 if old_server_num == "1" else (OUTLINE_API_URL_2 if old_server_num == "2" else OUTLINE_API_URL_3)
    try:
        requests.delete(f"{api_url_old}/access-keys/{old_key_id}", verify=False, timeout=8)
    except:
        pass

    try:
        chat_info = bot.get_chat(target_chat_id)
        user_first = chat_info.first_name if chat_info.first_name else ""
        user_last = chat_info.last_name if chat_info.last_name else ""
        user_name = f"{user_first} {user_last}".strip() or "HMA Customer"

        new_key, _, expire_date = create_outline_key(
            new_server_num, user_name, custom_gb=rem_gb, target_chat_id=target_chat_id, custom_expire_date=exp_date
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
            bot.edit_message_text(call.message.text + f"\n\n✅ <b>REPLACED (Server {new_server_num} 🇸🇬)</b>", chat_id=call.message.chat.id, message_id=call.message.message_id, parse_mode="HTML")
            bot.answer_callback_query(call.id, "✅ Key အသစ် အစားထိုး ပို့ပေးလိုက်ပါပြီခင်ဗျာ။")
    except Exception as e:
        bot.answer_callback_query(call.id, f"❌ Error: {str(e)}", show_alert=True)

# ----------------- MAIN MESSAGE DISPATCHER -----------------

@bot.message_handler(func=lambda message: True)
def handle_all_messages(message):
    input_value = message.text.strip()
    chat_id = message.chat.id
    save_user_id(chat_id)

    if not is_user_subscribed(chat_id):
        send_force_join_message(chat_id)
        return

    # ✍️ စိတ်ကြိုက်ငွေပမာဏ ကီးဘုတ်မှ ရိုက်ထည့်ခြင်း Handler
    if get_custom_topup_state(chat_id):
        clean_amt_str = re.sub(r'[^\d]', '', input_value)
        if clean_amt_str and clean_amt_str.isdigit():
            amt = int(clean_amt_str)
            if amt < 500:
                bot.reply_to(message, "⚠️ အနည်းဆုံး ဖြည့်သွင်းငွေမှာ <b>500 Ks</b> ဖြစ်ပါသည်ခင်ဗျာ။ ကျေးဇူးပြု၍ ပြန်လည်ရိုက်ထည့်ပေးပါ:", parse_mode="HTML")
                return
            set_custom_topup_state(chat_id, False)
            set_topup_state(chat_id, amt)
            payment_text = get_payment_instruction_text(amt)
            markup = InlineKeyboardMarkup()
            markup.row(InlineKeyboardButton("🔙 ငွေပမာဏ ပြန်ရွေးရန်", callback_data="btn_open_topup"))
            markup.row(InlineKeyboardButton("🔙 မူလ Menu သို့ ပြန်သွားရန်", callback_data="back_to_main"))
            bot.send_message(chat_id, payment_text, parse_mode="HTML", reply_markup=markup)
            return
        else:
            bot.reply_to(message, "❌ ဂဏန်းသီးသန့် (ဥပမာ- <code>15000</code>) သာ ရိုက်ထည့်ပေးပါခင်ဗျာ:", parse_mode="HTML")
            return

    # 💸 Admin ငွေနှုတ်သည့် Dialog State Handler
    if str(chat_id) in [str(aid) for aid in ADMIN_CHAT_IDS]:
        deduct_state = get_admin_deduct_state(chat_id)
        if deduct_state:
            step = deduct_state.get("step")
            dtype = deduct_state.get("type", "all")
            
            # Step 1: Customer ID လက်ခံခြင်း
            if step == "ask_user":
                target_user_id = input_value.strip()
                if not target_user_id.isdigit():
                    bot.reply_to(message, "❌ Customer ၏ Telegram Chat ID ကို ဂဏန်းသီးသန့်သာ ရိုက်ထည့်ပါခင်ဗျာ:")
                    return
                deduct_state["target_user_id"] = target_user_id
                deduct_state["step"] = "ask_amount"
                set_admin_deduct_state(chat_id, deduct_state)

                m_b, b_b, t_b = get_user_balance_breakdown(target_user_id)
                bot.reply_to(
                    message,
                    f"👤 <b>Customer ID:</b> <code>{target_user_id}</code>\n"
                    f"💵 လက်ကျန်ငွေ ပမာဏ: <b>{m_b:,} Ks</b>\n"
                    f"🎁 Redeem Bonus: <b>{b_b:,} Ks</b>\n"
                    f"💎 စုစုပေါင်းလက်ကျန်: <b>{t_b:,} Ks</b>\n\n"
                    f"👇 <b>နှုတ်ယူလိုသော ငွေပမာဏ</b> ကို ဂဏန်းသီးသန့် ရိုက်ပို့ပေးပါခင်ဗျာ:",
                    parse_mode="HTML"
                )
                return

            # Step 2: ငွေပမာဏ လက်ခံပြီး အမှန်တကယ် နှုတ်ယူခြင်း
            elif step == "ask_amount":
                clean_amt = re.sub(r'[^\d]', '', input_value)
                if not clean_amt.isdigit() or int(clean_amt) <= 0:
                    bot.reply_to(message, "❌ မှန်ကန်သော ငွေပမာဏကို ဂဏန်းသီးသန့် ရိုက်ထည့်ပါခင်ဗျာ:")
                    return

                target_user_id = deduct_state.get("target_user_id")
                amt_to_deduct = int(clean_amt)
                set_admin_deduct_state(chat_id, None)

                deducted, m_bal, b_bal, final_bal = admin_deduct_specific_funds(target_user_id, amt_to_deduct, deduct_type=dtype)

                bot.reply_to(
                    message,
                    f"✅ <b>ငွေပြန်နှုတ်ခြင်း အောင်မြင်ပါသည်!</b>\n\n"
                    f"👤 Customer ID: <code>{target_user_id}</code>\n"
                    f"💵 နှုတ်ယူငွေ: <b>-{deducted:,} MMK</b>\n"
                    f"💳 User ၏ လက်ရှိ ကျန်ငွေ: <b>{final_bal:,} MMK</b> (လက်ကျန်ငွေ ပမာဏ: {m_bal:,} Ks | Redeem: {b_bal:,} Ks)",
                    parse_mode="HTML"
                )

                try:
                    bot.send_message(
                        target_user_id,
                        f"⚠️ <b>အသိပေးချက်:</b>\n\nလူကြီးမင်း၏ Wallet ထဲမှ (<b>-{deducted:,} MMK</b>) အား Admin မှ ပြန်လည်နှုတ်ယူလိုက်ပါသည်ခင်ဗျာ။\n\n💳 လက်ရှိ သုံးနိုင်သော စုစုပေါင်း လက်ကျန်ငွေ: <b>{final_bal:,} MMK</b>",
                        parse_mode="HTML"
                    )
                except:
                    pass
                return

    # 🔑 Admin Manual Dispatch State Handler
    if str(chat_id) in [str(aid) for aid in ADMIN_CHAT_IDS]:
        manual_state = get_manual_dispatch_state(chat_id)
        if manual_state:
            set_manual_dispatch_state(chat_id, None)
            target_user_id = manual_state.get("target_chat_id")
            order_id = manual_state.get("order_id")
            plan_name = manual_state.get("plan_name", "စိတ်ကြိုက်သုံး Plan (5 Device)")
            disp_gb = manual_state.get("disp_gb", "Unlimited Data (5 Device)")
            months_count = manual_state.get("months", 1)

            today = datetime.now()
            expire_date = (today + relativedelta(months=months_count)).strftime("%d.%m.%Y")

            save_user_purchase_record(
                chat_id=target_user_id,
                order_id=order_id,
                plan_name=plan_name,
                disp_gb=disp_gb,
                months_count=months_count,
                price_str="-",
                server_num="VIP",
                expire_date=expire_date,
                vpn_key=input_value
            )
            save_persistent_key("VIP", f"custom_{order_id}", f"{plan_name} ({target_user_id}) {expire_date}", input_value, None, order_id, target_user_id)

            success_message = (
                f"🎉 <b>လူကြီးမင်း၏ VPN Key ရောက်ရှိပါပြီခင်ဗျာ!</b>\n\n"
                f"🧾 <b>Order ID:</b> <code>{order_id}</code>\n\n"
                f"🛍️ <b>Plan:</b> {plan_name} ({disp_gb})\n\n"
                f"⏰ <b>သက်တမ်းကုန်ဆုံးရက်:</b> {expire_date}\n\n"
                f"🔑 <b>လူကြီးမင်း၏ VPN Key:</b>\n\n"
                f"<code>{input_value}</code>\n\n"
                f"☝️ အပေါ်က Key ကို <b>တစ်ချက်တည်း နှိပ်လိုက်ရုံဖြင့်</b> Auto Copy ကူးသွားပါလိမ့်မယ်ခင်ဗျာ။ V2BOX VPN App ထဲသို့ ထည့်သွင်းအသုံးပြုနိုင်ပါပြီ။"
            )
            try:
                bot.send_message(target_user_id, success_message, parse_mode="HTML")
                bot.reply_to(message, f"✅ <b>Order ID: {order_id} အတွက် Customer ထံသို့ Key အား အောင်မြင်စွာ ပို့ပေးလိုက်ပါပြီခင်ဗျာ။</b>", parse_mode="HTML")
            except Exception as e:
                bot.reply_to(message, f"❌ Customer ထံ ပို့မရပါ - {str(e)}")
            return

    # 📢 Admin Broadcast Text
    if str(chat_id) in [str(aid) for aid in ADMIN_CHAT_IDS] and get_broadcast_state(chat_id):
        set_broadcast_state(chat_id, False)
        all_users = load_all_users()
        success_count = 0
        bot.send_message(chat_id, f"⏳ Broadcast စာအား User စုစုပေါင်း ({len(all_users)}) ဆီ အကုန် ပို့ပေးနေပါသည်...")
        for uid in all_users:
            if str(uid) in [str(aid) for aid in ADMIN_CHAT_IDS]: continue
            try:
                bot.send_message(uid, input_value, parse_mode="HTML")
                success_count += 1
            except:
                pass
        bot.send_message(chat_id, f"✅ <b>Broadcast ပို့ပြီးပါပြီ!</b>\n\nရောက်ရှိသူ: <b>{success_count} / {len(all_users)}</b>", parse_mode="HTML")
        return

    # 🛍️ Plan များဝယ်ရန်
    if input_value in ["🛍️ Plan များဝယ်ရန်", "Plan များဝယ်ရန်", "🛍️ Plan များ ကြည့်ရန်", "Plan များ ကြည့်ရန်"]:
        clear_all_states(chat_id)
        bot.send_message(chat_id, "🧸 လူကြီးမင်း ဝယ်ယူလိုသော VPN Plan ကို ရွေးချယ်ပေးပါခင်ဗျာ:", reply_markup=get_plan_keyboard())
        return

    # 💰 ငွေဖြည့်ရန်
    if input_value in ["💰 ငွေဖြည့်ရန်", "ငွေဖြည့်ရန်", "💰 ငွေဖြည့်ရန် (Top-Up)"]:
        clear_all_states(chat_id)
        bot.send_message(
            chat_id,
            "💰 <b>Wallet ထဲသို့ ဖြည့်သွင်းလိုသော ငွေပမာဏကို ရွေးချယ်ပေးပါ:</b>\n\n"
            "💡 <i>ငွေကြိုတင် ဖြည့်ထားခြင်းဖြင့် Plan များကို ၂၄ နာရီလုံး Bot မှ ချက်ချင်း Auto ထုတ်ယူနိုင်ပါသည်ခင်ဗျာ။</i>",
            parse_mode="HTML",
            reply_markup=get_topup_amounts_keyboard()
        )
        return

    # 💳 လက်ကျန်ငွေ
    if input_value in ["💳 လက်ကျန်ငွေ", "လက်ကျန်ငွေ", "💳 လက်ကျန်ငွေ / Wallet"]:
        clear_all_states(chat_id)
        is_admin = str(chat_id) in [str(aid) for aid in ADMIN_CHAT_IDS]
        main_bal, bonus_bal, total_bal = get_user_balance_breakdown(chat_id)
        
        bonus_detail_str = ""
        if bonus_bal > 0:
            expiring_data = load_expiring_credits().get(str(chat_id), [])
            lines = []
            for g in expiring_data:
                if g.get("remaining", 0) > 0:
                    lines.append(f"   • <b>+{g['remaining']:,} Ks</b> (သက်တမ်းကုန်မည့်ရက်: <code>{g['expire_disp']}</code>)")
            if lines:
                bonus_detail_str = "\n⏳ <b>ရက်စွဲပါ လက်ကျန်ငွေများ:</b>\n" + "\n".join(lines) + "\n"

        crown = " 👑" if is_admin else ""
        main_bal_disp = "♾️ Unlimited" if is_admin else f"{main_bal:,} MMK"
        total_bal_disp = "♾️ Unlimited" if is_admin else f"{total_bal:,} MMK"

        wallet_text = (
            f"💳 <b>လူကြီးမင်း၏ Wallet အချက်အလက်</b>\n\n"
            f"👤 <b>အသုံးပြုသူ:</b> {message.from_user.first_name}{crown}\n"
            f"🆔 <b>Chat ID:</b> <code>{chat_id}</code>\n\n"
            f"💵 <b>လက်ကျန်ငွေ ပမာဏ:</b> {main_bal_disp}\n"
            f"🎁 <b>Redeem လက်ကျန်ငွေ:</b> {bonus_bal:,} MMK\n"
            f"{bonus_detail_str}"
            f"━━━━━━━━━━━━━━━\n"
            f"💎 <b>စုစုပေါင်း သုံးနိုင်သောငွေ:</b> <b>{total_bal_disp}</b>\n"
            f"━━━━━━━━━━━━━━━\n\n"

        )
        markup = InlineKeyboardMarkup()
        markup.row(
            InlineKeyboardButton("💰 ငွေဖြည့်ရန်", callback_data="btn_open_topup"),
            InlineKeyboardButton("🎟️ Redeem Code သုံးမည်", callback_data="btn_open_redeem")
        )
        markup.row(InlineKeyboardButton("🔙 မူလ Menu သို့ ပြန်သွားရန်", callback_data="back_to_main"))
        bot.send_message(chat_id, wallet_text, parse_mode="HTML", reply_markup=markup)
        return

    # 🧰 Data ပမာဏစစ်ရန်
    if input_value in ["🧰 Data ပမာဏစစ်ရန်", "Data ပမာဏစစ်ရန်", "🧰 Data လက်ကျန်စစ်ရန်", "🧰 Data Usage စစ်ရန်"]:
        clear_all_states(chat_id)
        check_guide = (
            "👇 <b>လက်ကျန် Data စစ်ဆေးရန်:</b>\n\n"
            "ဝယ်ယူထားသော VPN Key Link (<code>ss://...</code>) အား ဤ Chat ထဲသို့ Paste ချ၍ ပေးပို့စစ်ဆေးနိုင်ပါသည်ခင်ဗျာ။"
        )
        bot.send_message(chat_id, check_guide, parse_mode="HTML", reply_markup=get_back_inline_keyboard())
        return

    # 📇 ဝယ်ယူမှုမှတ်တမ်း
    if input_value in ["📇 ဝယ်ယူမှုမှတ်တမ်း", "ဝယ်ယူမှုမှတ်တမ်း"]:
        clear_all_states(chat_id)
        records = get_user_combined_purchase_records(chat_id)
        if not records:
            empty_msg = (
                "📇 <b>လူကြီးမင်း၏ ဝယ်ယူမှုမှတ်တမ်း</b>\n\n"
                "<i>လက်ရှိတွင် ဝယ်ယူထားသော မှတ်တမ်း မရှိသေးပါခင်ဗျာ။ '🛍️ Plan များဝယ်ရန်' မှတစ်ဆင့် စတင်ဝယ်ယူနိုင်ပါသည်ခင်ဗျာ။</i>"
            )
            bot.send_message(chat_id, empty_msg, parse_mode="HTML", reply_markup=get_back_inline_keyboard())
            return

        history_texts = []
        for idx, rec in enumerate(reversed(records), 1):
            srv_name = f"Singapore Server {rec.get('server', '1')} 🇸🇬" if rec.get('server') != "VIP" else "VIP Server 🇸🇬"
            vpn_k = rec.get('vpn_key', '')
            key_block = f"<code>{vpn_k}</code>" if vpn_k != "N/A" else "<i>(Key လဲလှယ်ရန် Menu ရှိ '♻️ Key လဲရန်' အသုံးပြုနိုင်ပါသည်)</i>"
            
            item_txt = (
                f"<b>#{idx} | ဝယ်ယူမှု အချက်အလက်</b>\n\n"
                f"🧾 <b>Order ID:</b> <code>{rec.get('order_id', 'N/A')}</code>\n\n"
                f"📅 <b>အချိန်:</b> <code>{rec.get('timestamp', 'N/A')}</code>\n\n"
                f"🛍️ <b>Plan:</b> {rec.get('plan_name', '')} ({rec.get('disp_gb', '')})\n\n"
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

    # ♻️ Key လဲရန်
    if input_value in ["♻️ Key လဲရန်", "Key လဲရန်"]:
        clear_all_states(chat_id)
        set_replacement_state(chat_id, True)
        replace_guide = (
            "♻️ <b>VPN Key အစားထိုး လဲလှယ်ရန်:</b>\n\n"
            "👇 အဆင်မပြေ ဖြစ်နေသော VPN Key (<code>ss://...</code>) ကို ဒီ Chat ထဲသို့ Paste ချ ပေးပို့ပေးပါခင်ဗျာ။\n"
            "<i>(Bot မှ ကျန်ရှိသော ရက်/Data များကို စစ်ဆေး၍ Admin ထံ အစားထိုး တောင်းဆိုပေးပါမည်။)</i>"
        )
        bot.send_message(chat_id, replace_guide, parse_mode="HTML", reply_markup=get_back_inline_keyboard())
        return

    # 👨‍💻 Admin ဆက်သွယ်ရန်
    if input_value in ["👨‍💻 Admin ဆက်သွယ်ရန်", "Admin ဆက်သွယ်ရန်", "👨‍💻 Admin သို့ ဆက်သွယ်ရန်"]:
        clear_all_states(chat_id)
        admin_link_markup = InlineKeyboardMarkup()
        admin_link_markup.add(InlineKeyboardButton("💬 စာပို့ရန် နှိပ်ပါ", url="https://t.me/H_M_A_2026"))
        admin_link_markup.add(InlineKeyboardButton("🔙 မူလ Menu သို့ ပြန်သွားရန်", callback_data="back_to_main"))
        bot.send_message(chat_id, "👇 အောက်ကခလုတ်ကိုနှိပ်ပြီး Admin ထံ တိုက်ရိုက်စာပို့ ဆက်သွယ်နိုင်ပါပြီဗျာ။", reply_markup=admin_link_markup)
        return

    # 🎟️ Wallet Amount Redeem Code စစ်ဆေးခြင်း Handler
    if get_redeem_state(chat_id):
        set_redeem_state(chat_id, False)
        
        is_admin = str(chat_id) in [str(aid) for aid in ADMIN_CHAT_IDS]
        if not is_admin:
            _, bonus_bal, _ = get_user_balance_breakdown(chat_id)
            if bonus_bal > 0:
                bot.send_message(
                    chat_id,
                    f"⚠️ <b>ခွင့်လွှတ်ပါခင်ဗျာ၊ လူကြီးမင်းတွင် လက်ရှိ အသုံးပြုနိုင်သော Redeem Bonus လက်ကျန်ငွေ ({bonus_bal:,} MMK) ရှိနေဆဲ ဖြစ်ပါသဖြင့် နောက်ထပ် Code အသစ်ကို ထပ်မံ ရယူခွင့် မရှိသေးပါခင်ဗျာ။</b>\n\n"
                    f"💡 <i>အဆိုပါငွေဖြင့် Plan ဝယ်ယူအသုံးပြုပြီးမှ (သို့မဟုတ် ရက်စေ့ကုန်ဆုံးသွားမှ) သာ နောက်ထပ် Code အသစ်ကို ရယူနိုင်ပါမည်ခင်ဗျာ။</i>",
                    parse_mode="HTML",
                    reply_markup=get_back_inline_keyboard()
                )
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
            validity_days = int(code_info.get("validity_days", 1))
            mode = code_info.get("mode", "single")
            user_str_id = str(chat_id)
            claimed_users = code_info.get("claimed_users", [])

            # လူအများခွဲသုံးစနစ်
            if mode == "shared":
                if not is_admin and user_str_id in claimed_users:
                    bot.send_message(chat_id, "⚠️ <b>သင်သည် ဤ Code အား ရယူပြီးဖြစ်ပါသည်ခင်ဗျာ။</b>\n<i>(Code တစ်ခုလျှင် လူတစ်ဦး ၁ ကြိမ်သာ ရယူနိုင်ပါသည်)</i>", parse_mode="HTML", reply_markup=get_back_inline_keyboard())
                    return
                
                remaining = int(code_info.get("remaining", 0))
                if remaining < 500:
                    del codes[matched_code_key]
                    save_redeem_codes(codes)
                    bot.send_message(chat_id, "❌ <b>ဤ Code ၏ သတ်မှတ်ထားသော ပမာဏ ပြည့်သွားပါပြီဖြစ်၍ အသုံးပြု၍ မရတော့ပါခင်ဗျာ။</b>", parse_mode="HTML", reply_markup=get_back_inline_keyboard())
                    return

                possible_amounts = [1000, 2000, 3000]
                valid_options = [opt for opt in possible_amounts if opt <= remaining]

                if not valid_options:
                    awarded_amt = remaining
                else:
                    weights = [70, 20, 10][:len(valid_options)]
                    awarded_amt = random.choices(valid_options, weights=weights, k=1)[0]
                
                new_balance, exp_disp = add_expiring_bonus_to_wallet(chat_id, awarded_amt, validity_days)
                remaining -= awarded_amt
                claimed_users.append(user_str_id)
                code_info["remaining"] = remaining
                code_info["claimed_users"] = claimed_users
                
                if remaining < 500:
                    del codes[matched_code_key]
                else:
                    codes[matched_code_key] = code_info
                    
                save_redeem_codes(codes)

                user_name = message.from_user.first_name if message.from_user.first_name else "Winner"
                crown_icon = " 👑" if is_admin else ""
                disp_total_bal = "♾️ Unlimited" if is_admin else f"{new_balance:,} MMK"

                success_msg = (
                    f"🎉 <b>ဂုဏ်ယူပါတယ်ခင်ဗျာ! Redeem Code အောင်မြင်စွာ အသုံးပြုပြီးပါပြီ။</b>\n\n"
                    f"👤 <b>အသုံးပြုသူ:</b> {user_name}{crown_icon}\n"
                    f"🎟️ <b>Code:</b> <code>{matched_code_key}</code>\n"
                    f"💵 <b>ရရှိသော Wallet ငွေ:</b> <b>+{awarded_amt:,} MMK</b>\n"
                    f"⏰ <b>ငွေသက်တမ်း:</b> <b>{validity_days} ရက် (ကုန်ဆုံးရက်: {exp_disp})</b>\n\n"
                    f"💳 <b>လက်ရှိ သုံးနိုင်သော စုစုပေါင်းငွေ:</b> <b>{disp_total_bal}</b>\n\n"
                    f"💡 <i>ဤငွေဖြင့် ဝယ်ယူသော Key ၏ သက်တမ်းသည်လည်း {validity_days} ရက် ဖြစ်ပါမည်ခင်ဗျာ။</i>"
                )
                bot.send_message(chat_id, success_msg, parse_mode="HTML", reply_markup=get_back_inline_keyboard())

                for aid in ADMIN_CHAT_IDS:
                    try:
                        bot.send_message(
                            aid, 
                            f"🎟️ <b>Shared Redeem Code Claimed:</b>\n\nCustomer: {user_name}{crown_icon} (ID: <code>{chat_id}</code>) သည် Code <code>{matched_code_key}</code> မှ <b>{awarded_amt:,} MMK</b> ({validity_days} ရက် သက်တမ်း) ရယူသွားပါပြီ။\n(လက်ကျန် ပမာဏ: {remaining:,} MMK)",
                            parse_mode="HTML"
                        )
                    except:
                        pass
                return

            # တစ်ဦးတည်းသုံးစနစ်
            else:
                amt_to_add = int(code_info.get("amount", 1000))
                del codes[matched_code_key]
                save_redeem_codes(codes)
                
                new_balance, exp_disp = add_expiring_bonus_to_wallet(chat_id, amt_to_add, validity_days)
                user_name = message.from_user.first_name if message.from_user.first_name else "Winner"
                crown_icon = " 👑" if is_admin else ""
                disp_total_bal = "♾️ Unlimited" if is_admin else f"{new_balance:,} MMK"

                success_msg = (
                    f"🎉 <b>ဂုဏ်ယူပါတယ်ခင်ဗျာ! Redeem Code အောင်မြင်စွာ အသုံးပြုပြီးပါပြီ။</b>\n\n"
                    f"👤 <b>အသုံးပြုသူ:</b> {user_name}{crown_icon}\n"
                    f"🎟️ <b>Code:</b> <code>{matched_code_key}</code>\n"
                    f"💵 <b>ရရှိသော Wallet ငွေ:</b> <b>+{amt_to_add:,} MMK</b>\n"
                    f"⏰ <b>ငွေသက်တမ်း:</b> <b>{validity_days} ရက် (ကုန်ဆုံးရက်: {exp_disp})</b>\n\n"
                    f"💳 <b>လက်ရှိ သုံးနိုင်သော စုစုပေါင်းငွေ:</b> <b>{disp_total_bal}</b>\n\n"
                    f"💡 <i>ဤငွေဖြင့် ဝယ်ယူသော Key ၏ သက်တမ်းသည်လည်း {validity_days} ရက် ဖြစ်ပါမည်ခင်ဗျာ။</i>"
                )
                bot.send_message(chat_id, success_msg, parse_mode="HTML", reply_markup=get_back_inline_keyboard())

                for aid in ADMIN_CHAT_IDS:
                    try:
                        bot.send_message(
                            aid, 
                            f"🎟️ <b>Single Redeem Code Claimed:</b>\n\nCustomer: {user_name}{crown_icon} (ID: <code>{chat_id}</code>) သည် Code <code>{matched_code_key}</code> ဖြင့် <b>{amt_to_add:,} MMK</b> ({validity_days} ရက် သက်တမ်း) ရယူသွားပါပြီခင်ဗျာ။",
                            parse_mode="HTML"
                        )
                    except:
                        pass
                return
        else:
            bot.send_message(chat_id, "❌ <b>ထည့်သွင်းထားသော Redeem Code မှားယွင်းနေပါသည် (သို့မဟုတ်) အသုံးပြုပြီးသား ဖြစ်နေပါသည်ခင်ဗျာ။</b>", parse_mode="HTML", reply_markup=get_back_inline_keyboard())
            return

    # 🔍 Cus ရှာရန် (Admin)
    if input_value == "🔍 Cus ရှာရန်":
        clear_all_states(chat_id)
        if str(chat_id) not in [str(aid) for aid in ADMIN_CHAT_IDS]:
            bot.reply_to(message, "❌ ခွင့်လွှတ်ပါ၊ ဒီ ခလုတ်သည် Admin သီးသန့် အသုံးပြုနိုင်သော ခလုတ်ဖြစ်ပါသည်။")
            return
        
        bot.send_message(chat_id, "⏳ Customer စာရင်းများကို တွက်ချက်နေပါသည်...")
        summary_msg = get_customer_summary_stats()
        set_search_state(chat_id, True)
        bot.send_message(chat_id, summary_msg, parse_mode="HTML", reply_markup=get_back_inline_keyboard())
        return

    # 🎟️ Gen RD Code (Admin)
    if input_value == "🎟️ Gen RD Code":
        clear_all_states(chat_id)
        if str(chat_id) not in [str(aid) for aid in ADMIN_CHAT_IDS]:
            bot.reply_to(message, "❌ ခွင့်လွှတ်ပါ၊ ဒီ ခလုတ်သည် Admin သီးသန့် ဖြစ်ပါသည်။")
            return
        bot.send_message(
            chat_id,
            "🎟️ <b>Wallet Amount Redeem Code ထုတ်ရန်:</b>\n\nကျေးဇူးပြု၍ မည်သည့် <b>ငွေပမာဏ</b> အတွက် Code ထုတ်ယူမည်ကို ရွေးချယ်ပေးပါခင်ဗျာ:",
            parse_mode="HTML",
            reply_markup=get_admin_rd_amounts_keyboard()
        )
        return

    # 💸 ငွေနှုတ်ရန် (Admin Menu Button)
    if input_value == "💸 ငွေနှုတ်ရန်":
        clear_all_states(chat_id)
        if str(chat_id) not in [str(aid) for aid in ADMIN_CHAT_IDS]:
            bot.reply_to(message, "❌ ခွင့်လွှတ်ပါ၊ ဒီ ခလုတ်သည် Admin သီးသန့် ဖြစ်ပါသည်။")
            return
        bot.send_message(
            chat_id,
            "💸 <b>Customer များထံမှ ငွေပြန်လည်နှုတ်ယူခြင်း:</b>\n\nကျေးဇူးပြု၍ မည်သည့် လက်ကျန်ငွေအမျိုးအစားကို နှုတ်ယူလိုသည်ကို ရွေးချယ်ပေးပါခင်ဗျာ:",
            parse_mode="HTML",
            reply_markup=get_admin_deduct_type_keyboard()
        )
        return

    # 📢 Broadcast စာပို့ရန် (Admin)
    if input_value == "📢 Broadcast စာပို့ရန်":
        clear_all_states(chat_id)
        if str(chat_id) not in [str(aid) for aid in ADMIN_CHAT_IDS]:
            bot.reply_to(message, "❌ ခွင့်လွှတ်ပါ၊ ဒီ ခလုတ်သည် Admin သီးသန့် ဖြစ်ပါသည်။")
            return
        all_users = load_all_users()
        set_broadcast_state(chat_id, True)
        bot.send_message(chat_id, f"📢 <b>Broadcast စာပို့ရန်:</b> (User စုစုပေါင်း: {len(all_users)})\n\n👇 ပို့လိုသော စာသား သို့မဟုတ် ဓာတ်ပုံ ပို့ပေးပါခင်ဗျာ:", parse_mode="HTML", reply_markup=get_back_inline_keyboard())
        return

    if str(chat_id) in [str(aid) for aid in ADMIN_CHAT_IDS] and get_search_state(chat_id):
        set_search_state(chat_id, False)
        bot.send_message(chat_id, f"⏳ <b>'{input_value}'</b> ဖြင့် ရှာဖွေနေပါသည်...", parse_mode="HTML")
        matches, search_markup = search_users_by_query(input_value)
        if matches:
            search_markup.add(InlineKeyboardButton("🔙 မူလ Menu သို့ ပြန်သွားရန်", callback_data="back_to_main"))
            bot.send_message(chat_id, f"🔎 <b>ရှာဖွေတွေ့ရှိသော စာရင်း ({len(matches)} ခု):</b>\n\n👇 အသေးစိတ်ကြည့်ရန် နှိပ်ပါ -", parse_mode="HTML", reply_markup=search_markup)
        else:
            bot.send_message(chat_id, f"❌ <b>'{input_value}'</b> ဖြင့် ရှာမတွေ့ပါခင်ဗျာ။", parse_mode="HTML", reply_markup=get_back_inline_keyboard())
        return

    # Key Replacement Request Flow
    if get_replacement_state(chat_id):
        set_replacement_state(chat_id, False)
        bot.send_message(chat_id, "⏳ Key အား စစ်ဆေးနေပါသည်...")
        
        target_key, bytes_transferred, server_num = fetch_key_from_server(OUTLINE_API_URL_1, input_value)
        if not target_key: target_key, bytes_transferred, server_num = fetch_key_from_server(OUTLINE_API_URL_2, input_value)
        if not target_key: target_key, bytes_transferred, server_num = fetch_key_from_server(OUTLINE_API_URL_3, input_value)

        if target_key:
            full_name = target_key.get("name", "HMA User")
            key_id = str(target_key.get("id"))
            date_match = re.search(r'\d{1,2}\.\d{1,2}\.(\d{4}|\d{2})', full_name)
            exp_date = date_match.group(0) if date_match else "30.09.2026"

            limit_bytes = target_key.get("dataLimit", {}).get("bytes", 0)
            usage_bytes = bytes_transferred.get(key_id, 0)
            total_gb = bytes_to_gb(limit_bytes) if limit_bytes else 500
            used_gb = bytes_to_gb(usage_bytes)
            rem_gb = max(0, round(total_gb - used_gb, 2))

            alert_text = (
                f"♻️ <b>KEY REPLACEMENT REQUEST</b>\n\n"
                f"👤 ဝယ်ယူသူ: {message.from_user.first_name}\n"
                f"🆔 Chat ID: <code>{chat_id}</code>\n"
                f"📡 Server: Server {server_num}\n"
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
            markup.row(InlineKeyboardButton("❌ Reject", callback_data=f"replace_reject_{chat_id}_{key_id}"))

            for aid in ADMIN_CHAT_IDS:
                try: bot.send_message(aid, alert_text, parse_mode="HTML", reply_markup=markup)
                except: pass

            bot.send_message(chat_id, "✅ <b>Key စစ်ဆေးမှု အောင်မြင်ပါသည်။ Admin မှ အမြန်ဆုံး လဲလှယ်ပေးပါမည်။</b>", parse_mode="HTML", reply_markup=get_back_inline_keyboard())
            return
        else:
            bot.send_message(chat_id, "❌ ပေးပို့ထားသော Key ရှာမတွေ့ပါ။", parse_mode="HTML", reply_markup=get_back_inline_keyboard())
            return

    if input_value == "📊 Total Data Usage":
        clear_all_states(chat_id)
        if str(chat_id) not in [str(aid) for aid in ADMIN_CHAT_IDS]: return
        bot.send_message(chat_id, "📡 Data Usage တွက်ချက်နေပါသည်...")
        report_text = get_servers_total_usage()
        bot.send_message(chat_id, report_text, parse_mode="HTML", reply_markup=get_back_inline_keyboard())
        return

    if input_value in ["💰 လစဉ် ဝင်ငွေ", "လစဉ် ဝင်ငွေ"]:
        clear_all_states(chat_id)
        if str(chat_id) not in [str(aid) for aid in ADMIN_CHAT_IDS]: return
        bot.send_message(chat_id, "💰 ရောင်းရငွေ စာရင်း တွက်ချက်နေပါသည်...")
        rev_report = get_monthly_revenue_report()
        bot.send_message(chat_id, rev_report, parse_mode="HTML", reply_markup=get_back_inline_keyboard())
        return

    if input_value in ["🤖 Bot Refresh", "/refresh"]:
        clear_all_states(chat_id)
        bot.send_message(chat_id, "🤖 <b>Bot စနစ်အား Refresh ပြုလုပ်ပြီးပါပြီခင်ဗျာ!</b>", parse_mode="HTML", reply_markup=get_main_menu_keyboard(chat_id))
        return

    # Admin Reply Key Send Flow
    if str(chat_id) in [str(aid) for aid in ADMIN_CHAT_IDS] and message.reply_to_message:
        reply_caption = message.reply_to_message.caption or message.reply_to_message.text or ""
        if "User Chat ID:" in reply_caption:
            try:
                target_user_id = re.search(r'User Chat ID:\s*(?:<code>)?(\d+)(?:`)/?', reply_caption).group(1)
            except:
                pass

    if input_value.startswith('/'):
        return

    # ⚡️ Data ပမာဏစစ်ဆေးခြင်း (User Paste Key)
    target_key, bytes_transferred, server_num = fetch_key_from_server(OUTLINE_API_URL_1, input_value)
    if not target_key: target_key, bytes_transferred, server_num = fetch_key_from_server(OUTLINE_API_URL_2, input_value)
    if not target_key: target_key, bytes_transferred, server_num = fetch_key_from_server(OUTLINE_API_URL_3, input_value)

    if target_key:
        try:
            full_name = target_key.get("name", "HMA User")
            key_id = str(target_key.get("id"))
            
            display_name = full_name
            date_match_str = None
            for m in re.finditer(r'\d{1,2}\.\d{1,2}\.(\d{4}|\d{2})', full_name):
                date_match_str = m.group(0)

            if date_match_str: display_name = display_name.replace(date_match_str, "")
            display_name = display_name.replace("[GW]", "").replace("[gw]", "").split("tg")[0].replace("_", " ").strip() or "HMA Customer"

            if date_match_str:
                e_parts = date_match_str.split('.')
                day, month, year_str = int(e_parts[0]), int(e_parts[1]), e_parts[2]
                year = int("20" + year_str) if len(year_str) == 2 else int(year_str)
                end_date = f"{day}.{month}.{year}"
                has_date = True
            else:
                has_date = False

            limit_bytes = target_key.get("dataLimit", {}).get("bytes")
            plan_gb_val = bytes_to_gb(limit_bytes) if limit_bytes else 500
            plan_gb = f"{plan_gb_val} GB" if limit_bytes else "Unlimited"
            
            if bytes_transferred:
                usage_bytes = bytes_transferred.get(str(key_id), 0)
                usage_gb = bytes_to_gb(usage_bytes)
                usage_gb_str = f"{usage_gb} GB"
                rem_gb_str = f"{max(0, round(plan_gb_val - usage_gb, 2))} GB" if limit_bytes else "Unlimited"
            else:
                usage_gb_str = "ဆာဗာလိုင်းမရသဖြင့် မသိရှိနိုင်ပါ"
                rem_gb_str = plan_gb
            
            order_id_disp = get_order_id_for_key(full_name)
            ord_line = f"🧾 Order ID : <code>{order_id_disp}</code>\n" if order_id_disp != "N/A" else ""
            server_disp = f"Singapore Server {server_num} 🇸🇬" if bytes_transferred else f"Singapore Server {server_num} 🇸🇬 <i>(⚠️ Server Offline)</i>"

            result_text = (
                f"👤 အသုံးပြုသူ : {display_name}\n\n"
                f"{ord_line}\n\n"
                f"📡 Server : {server_disp}\n\n"
                f"🛍️ ဝယ်ယူထားသော Plan : {plan_gb}\n\n"
                f"🧰 အသုံးပြုပြီးသား Data : {usage_gb_str}\n\n"
                f"🗃️ ကျန်ရှိသော Data : <b>{rem_gb_str}</b>\n\n"
                f"⏰ သက်တမ်းကုန်ဆုံးရက်: {end_date if has_date else 'မသိရှိပါ'}"
            )
            bot.reply_to(message, result_text, parse_mode="HTML", reply_markup=get_back_inline_keyboard())
            return
        except Exception as e:
            bot.reply_to(message, f"❌ ဒေတာတွက်ချက်မှု မှားယွင်းနေပါသည်- {str(e)}")
            return

    not_found_msg = (
        "❌ <b>ခွင့်လွှတ်ပါဗျာ၊ တစ်ခုခုမှားနေပါတယ်ခင်ဗျာ။</b>\n\n"
        "💡 <i>Menu ခလုတ်များ Refresh လုပ်လိုပါက အောက်ပါ '🤖 Bot Refresh' ခလုတ် သို့မဟုတ် /start ကို နှိပ်ပေးပါခင်ဗျာ။</i>"
    )
    bot.reply_to(message, not_found_msg, parse_mode="HTML", reply_markup=get_main_menu_keyboard(chat_id))

@app.route('/cron-check', methods=['GET', 'POST'])
def cron_check():
    now = datetime.utcnow() + timedelta(hours=6, minutes=30)
    today = now.date()
    key_mappings = load_key_mappings()
    notified_count = 0
    deleted_count = 0

    expiring_data = load_expiring_credits()
    exp_changed = False
    for uid, grants in list(expiring_data.items()):
        valid_grants = []
        expired_sum = 0
        for g in grants:
            try:
                exp_dt = datetime.strptime(g["expire_at"], "%Y-%m-%d %H:%M:%S")
                if now > exp_dt:
                    expired_sum += g.get("remaining", 0)
                else:
                    valid_grants.append(g)
            except:
                pass
                
        if expired_sum > 0:
            exp_changed = True
            expiring_data[uid] = valid_grants
            try:
                bot.send_message(uid, f"⚠️ <b>အသိပေးချက်:</b>\n\nလူကြီးမင်း၏ Wallet ထဲမှ ရက်သတ်မှတ်ချက်ပါ Redeem Bonus ငွေ (<b>-{expired_sum:,} MMK</b>) သည် သက်တမ်းစေ့သွားသဖြင့် ပျက်ပြယ်သွားပါပြီခင်ဗျာ။", parse_mode="HTML")
            except:
                pass
                
    if exp_changed:
        save_expiring_credits(expiring_data)

    for api_url in [OUTLINE_API_URL_1, OUTLINE_API_URL_2, OUTLINE_API_URL_3]:
        try:
            keys_resp = requests.get(f"{api_url}/access-keys", verify=False, timeout=8)
            metrics_resp = requests.get(f"{api_url}/metrics/transfer", verify=False, timeout=8)
            if keys_resp.status_code != 200: continue
                
            keys_data = keys_resp.json().get("accessKeys", [])
            bytes_transferred = metrics_resp.json().get("bytesTransferredByUserId", {}) if metrics_resp.status_code == 200 else {}

            for key in keys_data:
                full_name = key.get("name", "")
                key_id = str(key.get("id"))
                limit_bytes = key.get("dataLimit", {}).get("bytes")
                usage_bytes = bytes_transferred.get(key_id, 0)
                
                is_gb_full = limit_bytes and usage_bytes >= limit_bytes
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
                        
                        if key_expire_date == today: is_expired_today = True
                        elif today > key_expire_date: should_delete = True
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
                                try: bot.send_message(aid, f"🗑️ <b>Auto Delete:</b>\n\n{ord_txt}Key: <code>{full_name}</code> အား သက်တမ်းကုန်သဖြင့် ဖျက်ဆီးလိုက်ပါပြီ။", parse_mode="HTML")
                                except: pass
                    except: pass
                    continue

                if is_gb_full or is_expired_today:
                    target_chat_id = None
                    id_match = re.search(r'\((\d+)\)', full_name)
                    if id_match: target_chat_id = id_match.group(1)

                    reason_text = "ဝယ်ယူထားသော Data GB ပြည့်သွားပါပြီ" if is_gb_full else "ယနေ့ သက်တမ်းကုန်ဆုံးပါပြီ"
                    if target_chat_id:
                        try:
                            user_noti = f"⚠️ <b>သတိပေးချက်:</b>\n\nလူကြီးမင်း၏ VPN Key ({full_name}) သည် <b>{reason_text}</b>။ '🛍️ Plan များဝယ်ရန်' မှတစ်ဆင့် ပြန်လည်ဝယ်ယူနိုင်ပါပြီခင်ဗျာ။"
                            bot.send_message(target_chat_id, user_noti, parse_mode="HTML")
                            notified_count += 1
                        except: pass
        except: pass

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
