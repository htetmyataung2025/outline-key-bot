"""Wallet balance view + admin deduct dialog (command + type select)."""

from bot_app.config import ADMIN_CHAT_IDS
from bot_app.extensions import bot
from bot_app.keyboards import get_back_inline_keyboard
from bot_app.services.billing import admin_deduct_specific_funds
from bot_app.services.slips import record_audit_log
from bot_app.services.states import set_admin_deduct_state


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

    record_audit_log(
        message.from_user.id,
        "BALANCE_DEDUCT",
        "user",
        target_id,
        {"amount": deducted, "new_balance": final_bal, "requested": amt, "via": "telegram"},
    )

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

