"""Nightly expiry cron: notify expiring/GB-full keys, delete overdue ones."""

import re
from datetime import datetime

from bot_app.timeutil import myanmar_today

import requests

from bot_app.config import ADMIN_CHAT_IDS
from bot_app.extensions import bot
from bot_app.services.outline import iter_configured_server_urls
from bot_app.services.orders import load_key_mappings
from bot_app.utils import extract_chat_id_from_key_name


# Expired keys are not purged the instant they lapse: a customer who renews a
# day or two late would otherwise lose their slot overnight. The nightly cron
# keeps an expired key until it is more than this many days overdue, then
# deletes it from the server.
EXPIRY_GRACE_DAYS = 7


def run_expiry_cron():
    """Scan all Outline servers; notify users/admins, delete overdue keys.

    Returns {"notified": int, "deleted": int}.
    """
    today = myanmar_today()

    key_mappings = load_key_mappings()
    notified_count = 0
    deleted_count = 0

    for api_url in iter_configured_server_urls():
        try:
            keys_resp = requests.get(f"{api_url}/access-keys", verify=False, timeout=8)
            metrics_resp = requests.get(f"{api_url}/metrics/transfer", verify=False, timeout=8)
        
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
                            # Expired already. Keep a grace window so a late-renewing
                            # customer isn't cut off the morning after expiry; only
                            # purge once the key is more than EXPIRY_GRACE_DAYS overdue.
                            if (today - key_expire_date).days > EXPIRY_GRACE_DAYS:
                                should_delete = True
                    except:
                        pass

                if should_delete:
                    try:
                        del_res = requests.delete(f"{api_url}/access-keys/{key_id}", verify=False, timeout=8)
                        if del_res.status_code in [200, 204]:
                            deleted_count += 1
                            for aid in ADMIN_CHAT_IDS:
                                try:
                                    bot.send_message(
                                        aid, 
                                        f"🗑️ <b>Customer Key Expired:</b>\n\nKey: <code>{full_name}</code> သည် သက်တမ်းကုန်ဆုံးပြီး {EXPIRY_GRACE_DAYS} ရက်ကျော် သက်တမ်းမတိုးသဖြင့် Server ပေါ်မှ အလိုအလျောက် ဖျက်ဆီးလိုက်ပါပြီခင်ဗျာ။", 
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
                        f"📢 <b>Customer သတိပေးချက်</b>\n"
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

    return {"notified": notified_count, "deleted": deleted_count}
