"""Redeem code entry point (/redeem command + inline button)."""

from bot_app.config import ADMIN_CHAT_IDS
from bot_app.extensions import bot
from bot_app.handlers.common import send_force_join_message
from bot_app.keyboards import get_back_inline_keyboard
from bot_app.services.billing import get_user_balance_breakdown
from bot_app.services.orders import save_user_id
from bot_app.services.profiles import touch_user
from bot_app.services.states import clear_all_states, set_redeem_state
from bot_app.utils import is_user_subscribed


@bot.message_handler(commands=['redeem'])
def handle_redeem_command(message):
    chat_id = message.chat.id
    save_user_id(chat_id)
    touch_user(message.from_user)
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

