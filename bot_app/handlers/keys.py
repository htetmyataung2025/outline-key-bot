"""Key replacement approval (admin callback)."""

import requests

from bot_app.config import ADMIN_CHAT_IDS
from bot_app.extensions import bot
from bot_app.helpers.callback_guard import is_callback_processed
from bot_app.services.outline import create_outline_key, resolve_server_api_url


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

