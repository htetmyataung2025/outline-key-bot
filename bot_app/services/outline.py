"""Outline VPN server client: keys, usage, search, renew/create."""

import re
from datetime import timedelta

import requests
from dateutil.relativedelta import relativedelta
from bot_app.timeutil import myanmar_now
from telebot.types import InlineKeyboardButton, InlineKeyboardMarkup

from bot_app.config import ADMIN_CHAT_IDS, OUTLINE_API_URL_1, OUTLINE_API_URL_2, OUTLINE_API_URL_3
from bot_app.services.orders import load_key_orders, map_key_to_order
from bot_app.services.registry import (load_persistent_keys, save_persistent_key,
                                 sync_keys_to_persistent_registry,
                                 sync_legacy_redis_data_to_registry)
from bot_app.utils import bytes_to_gb, clean_ss_url, extract_chat_id_from_key_name


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
                extracted_cid = extract_chat_id_from_key_name(k_name)
                if (extracted_cid and str(extracted_cid) == str(chat_id)) or (f"({chat_id})" in k_name):
                    if not "[gw]" in k_name.lower():
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
    today = myanmar_now()
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
    today = myanmar_now()
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
            target_access_url = None
            
            for k in keys_data:
                k_name = k.get("name", "")
                extracted_cid = extract_chat_id_from_key_name(k_name)
                if (extracted_cid and str(extracted_cid) == str(target_chat_id)) or (f"({target_chat_id})" in k_name):
                    if not "[gw]" in k_name.lower():
                        target_key_id = k.get("id")
                        target_key_name = k_name
                        target_access_url = k.get("accessUrl", "")
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

                raw_access_url = target_access_url
                final_key = f"{raw_access_url}#{updated_name}"
                save_persistent_key(server_num, target_key_id, updated_name, final_key, new_fup_limit, order_id, target_chat_id)
                return final_key, updated_name, new_expire_date, True
    except Exception as e:
        print("Unlimited Renewal Error:", e)

    vpn_key, key_name, expire_date = create_outline_key(server_num, user_name, plan_info={"bytes": add_bytes}, target_chat_id=target_chat_id, months_count=months_count, custom_days=custom_days, is_giveaway=False, order_id=order_id)
    return vpn_key, key_name, expire_date, False

def create_outline_key(server_num, user_name, plan_info=None, custom_gb=None, target_chat_id=None, custom_days=None, months_count=1, is_giveaway=False, custom_expire_date=None, order_id=None):
    today = myanmar_now()
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

# ----------------- FORCE JOIN CHANNEL CALLBACK HANDLER -----------------

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
