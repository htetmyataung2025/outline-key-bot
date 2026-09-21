"""Purchase history (/history command)."""

from telebot.types import Message

from bot_app.extensions import bot
from bot_app.handlers.common import send_force_join_message
from bot_app.keyboards import get_back_inline_keyboard
from bot_app.services.orders import get_user_combined_purchase_records
from bot_app.utils import is_user_subscribed


@bot.message_handler(commands=["history"])
def handle_history(message: Message):
    chat_id = message.chat.id
    if not is_user_subscribed(chat_id):
        send_force_join_message(chat_id)
        return

    records = get_user_combined_purchase_records(chat_id)
    if not records:
        bot.reply_to(message, "📇 ဝယ်ယူမှတ်တမ်း မရှိသေးပါ။",
                     reply_markup=get_back_inline_keyboard())
        return

    lines = ["📇 <b>ဝယ်ယူမှတ်တမ်း</b>\n"]
    for r in records[-10:]:
        lines.append(f"• {r.get('timestamp','N/A')} | {r.get('plan_name','N/A')} | "
                     f"{r.get('disp_gb','N/A')} | Order: {r.get('order_id','N/A')}")

    bot.reply_to(message, "\n".join(lines), parse_mode="HTML",
                 reply_markup=get_back_inline_keyboard())
