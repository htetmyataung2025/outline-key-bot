"""Key replacement approval (admin callback)."""

import requests

from bot_app.config import ADMIN_CHAT_IDS
from bot_app.extensions import bot
from bot_app.helpers.callback_guard import is_callback_processed
from bot_app.helpers.deeplink import get_key_delivery_markup
from bot_app.services.outline import (_parse_expiry_from_name, create_outline_key,
                                      get_server_label, resolve_server_api_url)
from bot_app.timeutil import myanmar_now


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
        try:
            from bot_app.services.app_notify import push_app_notification
            push_app_notification(
                target_chat_id, "key_replace",
                "Key လဲလှယ်မှု ငြင်းပယ်ခံရပါတယ် ❌",
                "Admin မှ လဲလှယ်ရန် ငြင်းပယ်လိုက်ပါသည်။ အသေးစိတ်အတွက် Customer Service သို့ ဆက်သွယ်ပါ။")
        except Exception:
            pass
        bot.edit_message_text(call.message.text + "\n\n❌ <b>REJECTED</b>", chat_id=call.message.chat.id, message_id=call.message.message_id, parse_mode="HTML")
        return

    new_server_num = parts[1].replace("srv", "")
    old_server_num = parts[2]
    old_key_id = parts[3]
    target_chat_id = parts[4]
    rem_gb = float(parts[5])
    exp_date = parts[6]

    # Guard against approving a replacement for an already-expired key: the new
    # key is reissued with this same expiry, so it would arrive dead on arrival.
    exp_dt = _parse_expiry_from_name(exp_date)
    if exp_dt is not None and exp_dt.date() < myanmar_now().date():
        bot.answer_callback_query(
            call.id,
            "⌛ ဤ Key သည် သက်တမ်းကုန်ဆုံးပြီး ဖြစ်၍ လဲလှယ်၍ မရပါ။ Customer အား Plan အသစ် ဝယ်ယူရန် အကြောင်းကြားပေးပါ။",
            show_alert=True,
        )
        return

    api_url_old = resolve_server_api_url(old_server_num)
    api_url_old = api_url_old.rstrip('/') if api_url_old else ""
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
                f"📡 <b>Server အသစ်:</b> {get_server_label(new_server_num)}\n\n"
                f"🧰 <b>ကျန်ရှိသော Data:</b> {rem_gb} GB\n\n"
                f"⏰ <b>သက်တမ်းကုန်ဆုံးရက်:</b> {expire_date}\n\n"
                f"🔑 <b>VPN Key အသစ်:</b>\n\n"
                f"<code>{new_key}</code>\n\n"
                f"☝️ Key ကို တစ်ချက်နှိပ်ရုံဖြင့် Auto Copy ကူးနိုင်သလို၊ အောက်က Button များကို နှိပ်ပြီးလည်း တိုက်ရိုက်ထည့်သွင်း အသုံးပြုနိုင်ပါပြီခင်ဗျာ။"
            )
            bot.send_message(target_chat_id, success_msg, parse_mode="HTML", reply_markup=get_key_delivery_markup(new_key))
            try:
                from bot_app.services.app_notify import push_app_notification
                push_app_notification(
                    target_chat_id, "key_replace",
                    "Key အသစ် လဲလှယ်ပေးပြီးပါပြီ 🎉",
                    f"{get_server_label(new_server_num)} · Expire {expire_date}\n{new_key}")
            except Exception:
                pass
            bot.edit_message_text(call.message.text + f"\n\n✅ <b>REPLACED ({get_server_label(new_server_num)})</b>", chat_id=call.message.chat.id, message_id=call.message.message_id, parse_mode="HTML")
            bot.answer_callback_query(call.id, "✅ Key အသစ် အစားထိုး ပို့ပေးလိုက်ပါပြီခင်ဗျာ။")
    except Exception as e:
        bot.answer_callback_query(call.id, f"❌ Error: {str(e)}", show_alert=True)

# ----------------- MAIN MESSAGE DISPATCHER -----------------

