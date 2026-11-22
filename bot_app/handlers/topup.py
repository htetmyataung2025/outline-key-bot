"""Topup amount selection, slip upload, admin approval."""

from telebot.types import InlineKeyboardButton, InlineKeyboardMarkup

from bot_app.config import ADMIN_CHAT_IDS
from bot_app.extensions import bot
from bot_app.handlers.common import send_force_join_message
from bot_app.helpers.callback_guard import is_callback_processed
from bot_app.helpers.payment_text import get_payment_instruction_text
from bot_app.keyboards import get_topup_amounts_keyboard
from bot_app.services.billing import update_user_balance
from bot_app.services.ocr import NOT_A_SLIP_NOTICE_BOT, extract_slip_facts, resolve_slip_amount
from bot_app.services.orders import load_all_users, save_user_id
from bot_app.services.profiles import touch_user
from bot_app.services.slips import get_slip_by_id, record_audit_log, record_slip, review_slip
from bot_app.services.states import (
    get_broadcast_state, get_slip_gate_state,
    get_topup_state, set_admin_reject_state, set_broadcast_state, set_custom_topup_state, set_slip_gate_state, set_topup_state,
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

    # Single source of truth: mark the queue slip APPROVED (which also
    # credits the wallet, notifies the user and audit-logs) so the admin
    # dashboard reflects a Telegram-side approval live. Only if the slip is
    # not in the queue (legacy orders) do we credit directly.
    result = review_slip(topup_id, "APPROVE", reviewed_by=call.from_user.id)
    if not result.get("success") and result.get("code") == 404:
        new_balance, _ = update_user_balance(target_chat_id, amount)
        # Legacy slip (predates the review queue): the credit above must
        # still leave the same audit trail as a queue approve.
        record_audit_log(
            call.from_user.id,
            "SLIP_APPROVE",
            "slip",
            topup_id,
            {"chat_id": target_chat_id, "amount": amount, "legacy": True},
        )
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


@bot.callback_query_handler(func=lambda call: call.data.startswith("reject_topup_"))
def handle_reject_topup_start(call):
    """First step of a Telegram-side rejection: park the slip in a per-admin
    state and ask for the reason (the next text that admin sends). The actual
    rejection runs in menu.handle_all_messages once the reason arrives —
    review_slip then syncs every admin notification, notifies the customer
    and audits SLIP_REJECT, exactly like the dashboard path."""
    bot.answer_callback_query(call.id)

    if str(call.message.chat.id) not in [str(aid) for aid in ADMIN_CHAT_IDS]:
        return

    topup_id = call.data[len("reject_topup_"):]
    slip = get_slip_by_id(topup_id)
    if not slip:
        bot.answer_callback_query(call.id, "⚠️ Slip ကို review queue ထဲ ရှာမတွေ့ပါခင်ဗျာ။", show_alert=True)
        return
    if slip.get("status") != "PENDING":
        bot.answer_callback_query(call.id, f"⚠️ ဒီ slip ကို {slip.get('status')} အဖြစ် သတ်မှတ်ပြီးသား ဖြစ်ပါသည်။", show_alert=True)
        return

    set_admin_reject_state(call.from_user.id, {"slip_id": topup_id})
    bot.send_message(
        call.message.chat.id,
        f"❌ <b>Top-Up ID: <code>{topup_id}</code> ကို ပယ်ဖျက်မည်။</b>\n\n"
        f"👇 ပယ်ဖျက်ရခြင်း အကြောင်းပြချက် (Reason) ကို ရိုက်ပို့ပေးပါခင်ဗျာ။\n"
        f"<i>နှင့်ထုတ်ရန် — <code>/cancel_reject</code> ဟု ရိုက်ပါ။</i>",
        parse_mode="HTML",
    )


@bot.message_handler(content_types=['photo'])
def handle_photo_messages(message):
    chat_id = message.chat.id
    save_user_id(chat_id)
    touch_user(message.from_user)

    if not is_user_subscribed(chat_id):
        send_force_join_message(chat_id)
        return

    # Admin Broadcast Photo — resumable chunked job (services/broadcast),
    # same engine as the text broadcast; caption also lands in the app.
    if str(chat_id) in [str(aid) for aid in ADMIN_CHAT_IDS] and get_broadcast_state(chat_id):
        set_broadcast_state(chat_id, False)
        from bot_app.services.broadcast import advance_broadcast, send_progress, start_broadcast
        photo_id = message.photo[-1].file_id
        caption_text = message.caption or ""
        job, created = start_broadcast(chat_id, "photo", caption_text, photo_id=photo_id)
        if not created:
            bot.send_message(chat_id, "⚠️ Broadcast တစ်ခု ပို့နေဆဲ ရှိပါတယ် — အရင်တစ်ခု ပြီးအောင် စောင့်ပေးပါ။")
            send_progress(bot, job, chat_id=chat_id)
            return
        bot.send_message(chat_id, f"⏳ ပုံပါသော Broadcast စာအား User စုစုပေါင်း ({len(job['recipients'])}) ဆီ အကုန် ပို့ပေးနေပါသည်...")
        job = advance_broadcast(bot, job=job)
        send_progress(bot, job, chat_id=chat_id)
        return

    # Top-Up Slip Handler
    user_first = message.from_user.first_name if message.from_user.first_name else ""
    user_last = message.from_user.last_name if message.from_user.last_name else ""
    user_name = f"{user_first} {user_last}".strip() or "HMA User"
    username = f"@{message.from_user.username}" if message.from_user.username else "No Username"

    selected_amt = get_topup_state(chat_id) or 1000
    set_topup_state(chat_id, None)
    set_custom_topup_state(chat_id, False)

    photo_file = bot.get_file(message.photo[-1].file_id)
    topup_id, tx_ref, ocr_amount, probable = extract_slip_facts(photo_file.file_path)

    # Bot Update #21: a photo with NO sign of a payment slip (an app
    # screenshot, a random picture) never enters the review queue. The
    # customer is told right away and gets one escape hatch — "this IS a
    # real slip" — which forwards the parked photo flagged as unverified.
    if not probable:
        set_slip_gate_state(chat_id, {
            "file_id": message.photo[-1].file_id,
            "topup_id": topup_id,
            "tx_ref": tx_ref,
            "selected_amt": selected_amt,
            "user_name": user_name,
            "username": username,
        })
        gate_markup = InlineKeyboardMarkup()
        gate_markup.add(InlineKeyboardButton(
            "✅ ပြေစာ အစစ်ပါ — Admin စစ်ပေးဖို့ ပို့မယ်",
            callback_data="slip_gate_send",
        ))
        bot.reply_to(message, NOT_A_SLIP_NOTICE_BOT, parse_mode="HTML", reply_markup=gate_markup)
        return

    _finalize_topup_slip(
        chat_id, user_name, username, selected_amt,
        topup_id, tx_ref, ocr_amount, message.photo[-1].file_id,
        reply_message=message,
    )


def _finalize_topup_slip(chat_id, user_name, username, selected_amt,
                         topup_id, tx_ref, ocr_amount, photo_file_id,
                         unverified=False, reply_message=None):
    """Record a slip, alert the admins and confirm to the customer.

    Shared by the normal photo flow and the Bot Update #21 gate escape
    hatch (``unverified=True`` — the customer vouched for a photo OCR
    could not verify, so the admin alert says a human must check it).
    """
    # Bot Update #20: the amount printed on the slip wins over the amount
    # the customer selected — a wrong selection must not be recorded.
    topup_amt, amount_status = resolve_slip_amount(selected_amt, ocr_amount)
    amount_note = ""
    if unverified:
        amount_note = (
            "\n\n⚠️ <b>စစ်ဆေးရန် လိုသည်:</b> Customer က 'ပြေစာ အစစ်ပါ' ဟု အတည်ပြု၍ ပို့လာသော slip ဖြစ်သည် — "
            "OCR ဖြင့် ပြေစာ လက္ခဏာ မတွေ့ခဲ့ပါ။ ပုံကို သေချာ စစ်ပြီးမှ Approve လုပ်ပါ။"
        )
    elif amount_status == "ocr" and ocr_amount != selected_amt:
        amount_note = (
            f"\n\n🤖 <b>OCR ပြင်ထည့်ထားသည်:</b> Customer ရွေးခဲ့သော {selected_amt:,} MMK → "
            f"ပြေစာပါ ပမာဏ <b>{topup_amt:,} MMK</b>"
        )
    elif amount_status == "selected":
        amount_note = (
            "\n\n⚠️ <i>OCR ဖြင့် ပမာဏ ဖတ်မရပါ — Customer ရွေးသော ပမာဏဖြင့် မှတ်ထားသည်။ "
            "ပုံကို သေချာ စစ်ပေးပါ။</i>"
        )

    admin_alert_text = (
        f"💰 <b>ငွေဖြည့်ပြေစာအသစ် (Top-Up Request)</b>\n\n"
        f"🧾 Top-Up ID: <code>{topup_id}</code>\n\n"
        f"👤 အသုံးပြုသူ: {user_name} ({username})\n\n"
        f"💵 ဖြည့်သွင်းငွေပမာဏ: <b>{topup_amt:,} MMK</b>\n\n"
        f"🆔 User Chat ID: <code>{chat_id}</code>"
        f"{amount_note}\n\n"
        f"<i>စစ်ဆေးပြီးပါက အောက်ပါ Approve / Reject ခလုတ်များဖြင့် သတ်မှတ်ပေးပါခင်ဗျာ။</i>"
    )

    markup = InlineKeyboardMarkup()
    markup.add(InlineKeyboardButton(f"✅ Approve (+{topup_amt:,} MMK)", callback_data=f"approve_topup_{chat_id}_{topup_amt}_{topup_id}"))
    markup.add(InlineKeyboardButton("❌ Reject", callback_data=f"reject_topup_{topup_id}"))

    admin_messages = []
    for aid in ADMIN_CHAT_IDS:
        try:
            sent = bot.send_photo(aid, photo_file_id, caption=admin_alert_text, parse_mode="HTML", reply_markup=markup)
            if sent is not None:
                admin_messages.append({"chat_id": sent.chat.id, "message_id": sent.message_id})
        except:
            pass

    record_slip(
        slip_id=topup_id,
        chat_id=chat_id,
        amount=topup_amt,
        username=username,
        file_id=photo_file_id,
        extracted_tx_id=tx_ref,
        admin_messages=admin_messages,
        admin_caption=admin_alert_text,
        ocr_amount=ocr_amount,
        selected_amount=selected_amt,
        unverified_photo=unverified,
    )

    correct_note = ""
    if amount_status == "ocr" and ocr_amount != selected_amt:
        correct_note = (
            f"\n\n🤖 <i>ပြေစာပါ ပမာဏ ({topup_amt:,} MMK) နှင့် ရွေးထားသော ပမာဏ ({selected_amt:,} MMK) "
            f"မတူသဖြင့် ပြေစာ ပမာဏ အတိုင်း ပြင်မှတ်ပေးထားပါသည်ခင်ဗျာ။</i>"
        )
    user_reply = (
        f"💌 <b>ငွေလွှဲပြေစာအား လက်ခံရရှိပါသည်ခင်ဗျာ။</b>\n\n"
        f"🧾 <b>Top-Up ID:</b> <code>{topup_id}</code>\n\n"
        f"💵 <b>ငွေပမာဏ:</b> {topup_amt:,} MMK\n\n"
        f"<i>Admin မှ ပြေစာစစ်ဆေးအတည်ပြုပြီးသည်နှင့် Wallet ထဲသို့ ချက်ချင်း ငွေထည့်ပေးပါမည်။ ကျေးဇူးတင်ပါသည်ခင်ဗျာ။ 🙏</i>"
        f"{correct_note}"
    )
    if reply_message is not None:
        bot.reply_to(reply_message, user_reply, parse_mode="HTML")
    else:
        bot.send_message(chat_id, user_reply, parse_mode="HTML")


@bot.callback_query_handler(func=lambda call: call.data == "slip_gate_send")
def handle_slip_gate_send(call):
    """Bot Update #21 escape hatch: the customer confirms the bounced
    photo IS a real slip — forward the parked photo into the review
    queue flagged as unverified."""
    chat_id = call.message.chat.id
    state = get_slip_gate_state(chat_id)
    if not state:
        bot.answer_callback_query(
            call.id,
            "⚠️ ဒီပုံအတွက် အချိန်ကုန်သွားပါပြီ — ပြေစာပုံကို ပြန်ပို့ပေးပါ။",
            show_alert=True,
        )
        return
    bot.answer_callback_query(call.id)
    set_slip_gate_state(chat_id, None)
    _finalize_topup_slip(
        chat_id,
        state.get("user_name") or "HMA User",
        state.get("username") or "No Username",
        state.get("selected_amt") or 1000,
        state.get("topup_id") or "#GATE",
        state.get("tx_ref") or "",
        None,
        state.get("file_id") or "",
        unverified=True,
    )
    try:
        bot.edit_message_text(
            "✅ <b>ပြေစာကို Admin စစ်ပေးဖို့ ပို့လိုက်ပါပြီ</b> — စစ်ဆေးပြီးတာနဲ့ Wallet ထဲ ထည့်ပေးပါမယ် ခင်ဗျာ။",
            chat_id=chat_id,
            message_id=call.message.message_id,
            parse_mode="HTML",
        )
    except Exception:
        pass

