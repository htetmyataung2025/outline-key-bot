import base64
import html
import json
import os
import random
import re
import string
from datetime import datetime, timedelta

import requests
import telebot
from dateutil.relativedelta import relativedelta
from flask import jsonify, request
from telebot.types import (
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    KeyboardButton,
    ReplyKeyboardMarkup,
    WebAppInfo,
)

from app.config import (
    ADMIN_CHAT_IDS,
    MY_PAYMENT_PHONES,
    OCR_API_KEY,
    OUTLINE_API_URL_1,
    OUTLINE_API_URL_2,
    OUTLINE_API_URL_3,
    PLANS,
    REQUIRED_CHANNEL,
    TELEGRAM_TOKEN,
)
from app.extensions import app, bot
from app.keyboards import (
    get_admin_deduct_type_keyboard,
    get_admin_rd_amounts_keyboard,
    get_admin_rd_count_keyboard,
    get_admin_rd_days_keyboard,
    get_admin_rd_mode_keyboard,
    get_back_inline_keyboard,
    get_force_join_keyboard,
    get_main_menu_keyboard,
    get_plan_keyboard,
    get_topup_amounts_keyboard,
)
from app.storage.kv import redis_get, redis_set
from app.storage.paths import (
    ADMIN_MSG_MAP_FILE,
    ALL_USERS_FILE,
    BROADCAST_STATE_FILE,
    CUSTOM_TOPUP_STATE_FILE,
    DEDUCT_STATE_FILE,
    EXPIRING_CREDITS_FILE,
    KEY_ORDERS_FILE,
    MAPPING_FILE,
    ORDERS_FILE,
    PERSISTENT_KEYS_FILE,
    REDEEM_FILE,
    REDEEM_STATE_FILE,
    RENEW_CHOICE_STATE_FILE,
    REPLACEMENT_MSG_MAP_FILE,
    REPLACEMENT_STATE_FILE,
    SALES_FILE,
    SEARCH_STATE_FILE,
    STATE_FILE,
    TOPUP_STATE_FILE,
    USED_REDEEMERS_FILE,
    USER_HISTORY_FILE,
    WALLET_FILE,
)
from app.texts import force_join_text, welcome_back_text, welcome_text
from app.utils import (
    bytes_to_gb,
    clean_ss_url,
    extract_chat_id_from_key_name,
    generate_random_redeem_code,
)
from app.services.billing import (
    load_all_wallets, load_expiring_credits, save_expiring_credits, load_claimed_redeem_users, save_claimed_redeem_user, get_user_balance_breakdown, get_user_balance, update_user_balance, add_expiring_bonus_to_wallet, admin_deduct_specific_funds,
)
from app.services.states import (
    set_admin_deduct_state, get_admin_deduct_state, set_topup_state, get_topup_state, set_custom_topup_state, get_custom_topup_state, set_renew_choice_state, get_renew_choice_state, set_broadcast_state, get_broadcast_state, set_manual_dispatch_state, get_manual_dispatch_state, set_search_state, get_search_state, set_redeem_state, get_redeem_state, set_replacement_state, get_replacement_state, clear_all_states,
)
from app.services.registry import (
    load_persistent_keys, save_persistent_key, sync_keys_to_persistent_registry, sync_legacy_redis_data_to_registry,
)
from app.services.orders import (
    load_all_user_history, save_user_purchase_record, get_user_combined_purchase_records, load_orders, save_order, load_key_orders, map_key_to_order, get_order_id_for_key, save_user_id, load_all_users, load_user_plans, save_user_plan, load_key_mappings, save_key_mapping, load_sales_history, save_sale_transaction, save_admin_msg_map, get_admin_msg_map, save_replacement_msg_map, get_replacement_msg_map, load_redeem_codes, save_redeem_codes,
)
from app.services.ocr import (
    parse_slip_ocr, clean_ocr_text_thoroughly, extract_transaction_last6, generate_order_id_from_slip,
)
from app.services.reports import (
    get_monthly_revenue_report,
)
from app.services.notifier import run_expiry_cron
from app.services.outline import (
    get_servers_total_usage, get_customer_summary_stats, search_users_by_query, get_user_next_key_number, get_user_ultimate_keys, renew_specific_unlimited_key, renew_or_create_unlimited_key, create_outline_key, fetch_key_from_server,
)

PROCESSED_CALLBACKS = set()

def is_callback_processed(call_id):
    if call_id in PROCESSED_CALLBACKS:
        return True
    PROCESSED_CALLBACKS.add(call_id)
    if len(PROCESSED_CALLBACKS) > 1000:
        PROCESSED_CALLBACKS.clear()
    return False
























































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

def send_force_join_message(chat_id):
    bot.send_message(chat_id, force_join_text(), parse_mode="HTML", reply_markup=get_force_join_keyboard())




@bot.callback_query_handler(func=lambda call: call.data == "back_to_main")
def handle_back_to_main_callback(call):
    bot.answer_callback_query(call.id, "🔙 မူလ Menu သို့ ပြန်သွားပါပြီ။")
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





@bot.callback_query_handler(func=lambda call: call.data == "verify_subscription")
def handle_verify_subscription(call):
    bot.answer_callback_query(call.id, "✅ Verification အောင်မြင်ပါသည်။")
    chat_id = call.message.chat.id
    if is_user_subscribed(chat_id):
        save_user_id(chat_id)
        try:
            bot.delete_message(chat_id, call.message.message_id)
        except:
            pass
        bot.send_message(chat_id, welcome_back_text(), reply_markup=get_main_menu_keyboard(chat_id))
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

    user_first = message.from_user.first_name if message.from_user.first_name else ""
    user_last = message.from_user.last_name if message.from_user.last_name else ""
    full_name = f"{user_first} {user_last}".strip() or "HMA User"

    try:
        bot.set_chat_menu_button(chat_id, telebot.types.MenuButtonWebApp(
            type="web_app",
            text="Main Website",
            web_app=WebAppInfo(url="https://h-e.feature.hma.qzz.io"))
        )
    except:
        pass
        
    bot.reply_to(message, welcome_text(full_name), reply_markup=get_main_menu_keyboard(chat_id))

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
    bot.answer_callback_query(call.id)
    lock_key = f"appr_topup_{call.message.message_id}_{call.data}"
    if is_callback_processed(lock_key):
        return

    if str(call.message.chat.id) not in [str(aid) for aid in ADMIN_CHAT_IDS]:
        return

    parts = call.data.split("_")
    target_chat_id = parts[2]
    amount = int(parts[3])
    topup_id = parts[4]

    new_balance, _ = update_user_balance(target_chat_id, amount)

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

        if plan_code == "ultimate" and not has_redeem_credit:
            user_keys = get_user_ultimate_keys(chat_id, "1")
            if len(user_keys) > 0:
                markup = InlineKeyboardMarkup()
                for idx, uk in enumerate(user_keys, 1):
                    markup.row(InlineKeyboardButton(f"♻️ Key #{idx} ({uk['name'][:25]}) သက်တမ်းတိုးမည်", callback_data=f"renew_choice_{plan_code}_1_{uk['id']}"))
                markup.row(InlineKeyboardButton("➕ Key အသစ် ထပ်ဝယ်မည်", callback_data=f"renew_choice_{plan_code}_1_new"))
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

        balance_disp = "♾️" if is_admin else f"{balance:,} MMK"
        balance_status = "✅ ဝယ်ယူရန် လုံလောက်ပါသည်" if (balance >= amount or is_admin) else f"⚠️ ငွေမလုံလောက်ပါ (ထပ်ဖြည့်ရန်: {amount - balance:,} Ks)"
        
        server_notice = "\n💡 <i>(Redeem ငွေ လက်ကျန်ပါရှိသဖြင့် Server 1 မှသာ ထုတ်ပေးမည် ဖြစ်ပါသည်)</i>" if has_redeem_credit else ""

        text = (
            f"🛍️ <b>ဝယ်ယူမည့် Plan အချက်အလက်</b>\n\n"
            f"📮 <b>Plan:</b> {plan['name']}\n\n"
            f"🗃️ <b>Data:</b> {plan['data']} ( ၁လစာ )\n\n"
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

    user_disp_bal = "♾️" if is_admin else f"{new_bal:,} MMK"
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
    bot.answer_callback_query(call.id)
    lock_key = f"buy_wallet_{call.message.message_id}_{call.data}"
    if is_callback_processed(lock_key):
        return

    parts = call.data.split("_")
    plan_code = parts[1]
    server_num = parts[2]
    plan = PLANS.get(plan_code)
    chat_id = call.message.chat.id

    if not plan:
        return

    amount = plan["price"]
    balance = get_user_balance(chat_id)
    is_admin = str(chat_id) in [str(aid) for aid in ADMIN_CHAT_IDS]

    if not is_admin and balance < amount:
        bot.answer_callback_query(call.id, "❌ လက်ကျန်ငွေ မလုံလောက်ပါ။ ကျေးဇူးပြု၍ ငွေအရင်ဖြည့်ပေးပါ။", show_alert=True)
        return

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

        user_disp_bal = "♾️" if is_admin else f"{new_bal:,} MMK"
        user_msg = (
            f"🎉 <b>အော်ဒါမှာယူမှု အောင်မြင်ပါသည်!</b>\n\n"
            f"🧾 <b>Order ID:</b> <code>{order_id}</code>\n\n"
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

    user_disp_bal = "♾️" if is_admin else f"{new_bal:,} MMK"
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
                f"🛍️ <b>Custromer ကီးဝယ်ယူသွားပါပြီခင်ဗျာ။</b>\n\n"
                f"🧾 Order ID: <code>{order_id}</code>\n"
                f"👤 Customer: {user_name} (ID: <code>{chat_id}</code>)\n"
                f"🛍️ Plan: {plan['name']}\n"
                f"📡 Server: Server {server_num}\n"
                f"💵 ရရှိငွေ: {amount:,} MMK\n"
                f"⏰ သက်တမ်း: {expire_date} ({f'Redeem ငွေဖြင့် {apply_days} ရက်' if apply_days else '၁လစာ'})",
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

@bot.callback_query_handler(func=lambda call: call.data.startswith("replace_"))
def handle_admin_replace_callback(call):
    bot.answer_callback_query(call.id)
    lock_key = f"repl_{call.message.message_id}_{call.data}"
    if is_callback_processed(lock_key):
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
        main_bal_disp = "♾️" if is_admin else f"{main_bal:,} MMK"
        total_bal_disp = "♾️" if is_admin else f"{total_bal:,} MMK"

        user_first = message.from_user.first_name if message.from_user.first_name else ""
        user_last = message.from_user.last_name if message.from_user.last_name else ""
        full_name = f"{user_first} {user_last}".strip() or "HMA User"

        wallet_text = (
            f"💳 <b>လူကြီးမင်း၏ Wallet အချက်အလက်</b>\n\n"
            f"👤 <b>အသုံးပြုသူ:</b> {full_name}{crown}\n"
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
                disp_total_bal = "♾️" if is_admin else f"{new_balance:,} MMK"

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
                disp_total_bal = "♾️" if is_admin else f"{new_balance:,} MMK"

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
    result = run_expiry_cron()
    return jsonify({"status": "cron completed", **result}), 200

@app.route('/health', methods=['GET'])
def health():
    return jsonify({"status": "ok", "time": (datetime.utcnow() + timedelta(hours=6, minutes=30)).strftime("%Y-%m-%d %H:%M:%S")}), 200


@app.route('/', defaults={'path': ''}, methods=['POST', 'GET'])
@app.route('/<path:path>', methods=['POST', 'GET'])
def index(path):
    if request.method == 'POST':
        try:
            json_string = request.get_data().decode('utf-8')
            update = telebot.types.Update.de_json(json_string)
            if update:
                bot.process_new_updates([update])
        except Exception as e:
            print("Webhook Processing Error:", e)
        return jsonify({"status": "ok"}), 200
    return "Bot is running perfectly!", 200


# --- Local run / VPS run support ---
# Vercel မှာ import လုပ်ရုံနဲ့ Flask app ကို serve လုပ်တယ်။
# Local/VPS မှာ `python index.py` နဲ့ run ရင် polling (သို့) Flask webhook server ရွေးနိုင်တယ်။
if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Outline Key Bot runner")
    parser.add_argument("--mode", choices=["polling", "webhook"], default=os.environ.get("BOT_MODE", "polling"),
                        help="polling: Telegram long-polling (local test အတွက်လွယ်), webhook: Flask server")
    parser.add_argument("--port", type=int, default=int(os.environ.get("PORT", "5000")))
    parser.add_argument("--webhook-url", default=os.environ.get("WEBHOOK_URL", ""),
                        help="webhook mode မှာ Telegram ကို setWebhook လုပ်မည့် public URL (ဥပမာ https://yourdomain.com/)")
    args = parser.parse_args()

    if args.mode == "polling":
        print("🤖 Polling mode ဖြင့် Bot စတင်နေသည်... (Ctrl+C ဖြင့် ရပ်ရန်)")
        try:
            bot.remove_webhook()
        except Exception as e:
            print(f"remove_webhook သတိ: {e}")
        bot.infinity_polling(skip_pending=True, timeout=30)
    else:
        if args.webhook_url:
            try:
                bot.remove_webhook()
                bot.set_webhook(url=f"{args.webhook_url.rstrip('/')}/")
                print(f"✅ Webhook set: {args.webhook_url.rstrip('/')}/")
            except Exception as e:
                print(f"⚠️ setWebhook မအောင်မြင်ပါ: {e}")
        print(f"🌐 Webhook Flask server on port {args.port} ...")
        app.run(host="0.0.0.0", port=args.port, debug=False)
