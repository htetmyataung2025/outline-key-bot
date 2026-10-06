"""Entry gate: /start + force-join verify (single answer)."""

import telebot
from telebot.types import MenuButtonDefault, WebAppInfo

from bot_app.config import DASHBOARD_URL, is_admin
from bot_app.extensions import bot
from bot_app.handlers.common import send_force_join_message
from bot_app.keyboards import get_main_menu_keyboard
from bot_app.services.orders import save_user_id
from bot_app.services.profiles import touch_user
from bot_app.services.states import clear_all_states
from bot_app.texts import welcome_back_text, welcome_text
from bot_app.utils import is_user_subscribed


@bot.message_handler(commands=['start'])
def send_welcome(message):
    chat_id = message.chat.id
    save_user_id(chat_id)
    touch_user(message.from_user)
    clear_all_states(chat_id)

    if not is_user_subscribed(chat_id):
        send_force_join_message(chat_id)
        return

    user_first = message.from_user.first_name if message.from_user.first_name else ""
    user_last = message.from_user.last_name if message.from_user.last_name else ""
    full_name = f"{user_first} {user_last}".strip() or "HMA User"

    # Admins open the Control Center straight from the menu button (short
    # label keeps the pill compact on mobile); the dashboard then asks for
    # Admin ID + password. Customers get Telegram's default menu button —
    # the old "Main Website" landing page is gone, so the reset also unpins
    # the dead pill for anyone who still has it from earlier /start calls.
    try:
        if is_admin(chat_id):
            bot.set_chat_menu_button(chat_id, telebot.types.MenuButtonWebApp(
                type="web_app",
                text="🎛 Control",
                web_app=WebAppInfo(url=DASHBOARD_URL))
            )
        else:
            bot.set_chat_menu_button(chat_id, MenuButtonDefault())
    except:
        pass
        
    bot.reply_to(message, welcome_text(full_name), reply_markup=get_main_menu_keyboard(chat_id))


@bot.callback_query_handler(func=lambda call: call.data == "verify_subscription")
def handle_verify_subscription(call):
    chat_id = call.message.chat.id
    if is_user_subscribed(chat_id):
        bot.answer_callback_query(call.id, "✅ Verification အောင်မြင်ပါသည်။")
        save_user_id(chat_id)
        touch_user(call.from_user)
        try:
            bot.delete_message(chat_id, call.message.message_id)
        except:
            pass
        bot.send_message(chat_id, welcome_back_text(), reply_markup=get_main_menu_keyboard(chat_id))
    else:
        bot.answer_callback_query(call.id, "❌ Channel ထဲသို့ မဝင်ရောက်ရသေးပါခင်ဗျာ။ အရင်ဆုံး Join ပေးပါ။", show_alert=True)
