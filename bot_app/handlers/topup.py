"""Topup amount selection, slip upload, admin approval."""

from telebot.types import InlineKeyboardButton, InlineKeyboardMarkup

from bot_app.config import ADMIN_CHAT_IDS
from bot_app.extensions import bot
from bot_app.handlers.common import send_force_join_message
from bot_app.helpers.callback_guard import is_callback_processed
from bot_app.helpers.payment_text import get_payment_instruction_text
from bot_app.keyboards import get_topup_amounts_keyboard
from bot_app.services.billing import update_user_balance
from bot_app.services.ocr import generate_order_id_from_slip
from bot_app.services.orders import load_all_users, save_user_id
from bot_app.services.slips import record_slip
from bot_app.services.states import (
    get_broadcast_state,
    get_topup_state, set_broadcast_state, set_custom_topup_state, set_topup_state,
)
from bot_app.utils import is_user_subscribed


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
    record_slip(
        slip_id=topup_id,
        chat_id=chat_id,
        amount=topup_amt,
        username=username,
        file_id=message.photo[-1].file_id,
    )


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

