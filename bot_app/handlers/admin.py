"""Admin wizard: redeem-code generation + key view/delete."""

import html
import re

import requests

from telebot.types import InlineKeyboardButton, InlineKeyboardMarkup

from bot_app.config import ADMIN_CHAT_IDS
from bot_app.extensions import bot
from bot_app.helpers.callback_guard import is_callback_processed
from bot_app.services.outline import resolve_server_api_url
from bot_app.keyboards import (
    get_admin_rd_amounts_keyboard, get_admin_rd_count_keyboard, get_admin_rd_days_keyboard,
    get_admin_rd_mode_keyboard, get_back_inline_keyboard, get_main_menu_keyboard,
)
from bot_app.services.orders import get_order_id_for_key, load_redeem_codes, save_redeem_codes
from bot_app.services.registry import load_persistent_keys
from bot_app.services.slips import record_audit_log
from bot_app.services.states import clear_all_states, set_manual_dispatch_state
from bot_app.storage.kv import redis_set
from bot_app.utils import bytes_to_gb, generate_random_redeem_code


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

    record_audit_log(
        user_id,
        "REDEEM_BATCH_CREATE",
        "redeem",
        str(count),
        {"amount": amt, "mode": mode, "count": count, "via": "telegram"},
    )

    if mode == "shared":
        mode_desc = "လူအများခွဲသုံး (၁၀၀၀ ~ ၃၀၀၀ Ks စီ)"
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


@bot.callback_query_handler(func=lambda call: call.data.startswith("viewkey_"))
def handle_view_key_detail(call):
    bot.answer_callback_query(call.id)
    if str(call.message.chat.id) not in [str(aid) for aid in ADMIN_CHAT_IDS]:
        return
    
    parts = call.data.split("_")
    server_num = parts[1]
    key_id = parts[2]
    
    api_url = resolve_server_api_url(server_num)
    api_url = api_url.rstrip('/') if api_url else ""
    
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

        record_audit_log(
            call.from_user.id,
            "KEY_DELETE",
            "key",
            str(key_id),
            {"server": str(server_num), "via": "telegram"},
        )

        api_url = resolve_server_api_url(server_num)
        api_url = api_url.rstrip('/') if api_url else ""
        try:
            requests.delete(f"{api_url}/access-keys/{key_id}", verify=False, timeout=8)
            bot.edit_message_text(f"✅ <b>Server {server_num} ပေါ်မှ Key (ID: {key_id}) အား အောင်မြင်စွာ ဖျက်ဆီးပြီးပါပြီဗျာ။</b>", chat_id=call.message.chat.id, message_id=call.message.message_id, parse_mode="HTML")
        except:
            bot.edit_message_text(f"✅ <b>မှတ်တမ်းများထဲမှ Key (ID: {key_id}) အား ဖျက်ဆီးပြီးပါပြီ။ (Server Down နေသဖြင့် Server ဘက်သို့ သီးသန့် အမိန့်မရောက်ခဲ့ပါ)</b>", chat_id=call.message.chat.id, message_id=call.message.message_id, parse_mode="HTML")

    elif action == "cancel":
        bot.edit_message_text("❌ Key ဖျက်ခြင်းကို ပယ်ဖျက်လိုက်ပါပြီခင်ဗျာ။", chat_id=call.message.chat.id, message_id=call.message.message_id)


# 🔑 Admin Manual Key Send Callback (custom 5-device plan orders)
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


# ▶️ Broadcast Continue Handler


@bot.callback_query_handler(func=lambda call: call.data == "broadcast_continue")
def handle_broadcast_continue(call):
    chat_id = call.message.chat.id
    if str(chat_id) not in [str(aid) for aid in ADMIN_CHAT_IDS]:
        bot.answer_callback_query(call.id, "⛔ Admin သီးသန့်ပါ။")
        return
    from bot_app.services.broadcast import advance_broadcast, send_progress

    job = advance_broadcast(bot)
    if not job or job.get("status") == "done":
        bot.answer_callback_query(call.id, "✅ Broadcast ပို့ပြီးပါပြီ!")
        return
    bot.answer_callback_query(call.id, "▶️ ဆက်ပို့နေပါတယ်…")
    send_progress(bot, job, chat_id=chat_id)
