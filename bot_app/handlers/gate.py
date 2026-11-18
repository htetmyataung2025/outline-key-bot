import os
import re
import time

import telebot
from telebot.types import MenuButtonDefault, WebAppInfo

from bot_app.config import (
    DASHBOARD_URL,
    PLANS,
    is_admin,
)
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

    # App account linking: https://t.me/<bot>?start=link_<code> from the
    # H&E VPN app. Stores code -> this chat in Redis for 10 minutes; the
    # app polls /api/app/auth/poll and exchanges it for an account token.
    _text = getattr(message, "text", "") or ""
    _parts = _text.split(maxsplit=1) if isinstance(_text, str) else []
    if len(_parts) == 2 and _parts[1].strip().startswith("link_"):
        _code = _parts[1].strip()[len("link_"):].strip()
        if re.fullmatch(r"[A-Za-z0-9\-_]{8,64}", _code or ""):
            try:
                from bot_app.storage.kv import redis_set
                _u = message.from_user
                _full = " ".join(
                    x for x in [getattr(_u, "first_name", ""), getattr(_u, "last_name", "")]
                    if x
                ).strip()
                redis_set(f"app_link:{_code}", {
                    "chat_id": chat_id,
                    "name": _full,
                    "username": getattr(_u, "username", "") or "",
                    "exp": int(time.time()) + 600,
                })
                bot.send_message(
                    chat_id,
                    "✅ <b>H&E VPN App နှင့် ချိတ်ဆက်ပြီးပါပြီ!</b>\n\n"
                    "App ထဲမှာ လူကြီးမင်းရဲ့ Wallet လက်ကျန်ငွေ၊ Points နှင့် "
                    "ဝယ်ယူမှု မှတ်တမ်းတွေကို ကြည့်နိုင်ပါပြီ။ App သို့ ပြန်သွားပါ။",
                    parse_mode="HTML",
                )
            except Exception:
                pass
            return

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
        admin_mode = os.environ.get("ADMIN_MENU_BUTTON", "control").lower().strip()
        miniapp_url = os.environ.get("MINI_APP_URL", "").strip()
        btn_text = os.environ.get("MENU_BUTTON_TEXT", "Open App").strip() or "Open App"

        if is_admin(chat_id) and admin_mode != "miniapp":
            bot.set_chat_menu_button(chat_id, telebot.types.MenuButtonWebApp(
                type="web_app",
                text="Control",
                web_app=WebAppInfo(url=DASHBOARD_URL))
            )
        elif miniapp_url:
            bot.set_chat_menu_button(chat_id, telebot.types.MenuButtonWebApp(
                type="web_app",
                text=btn_text,
                web_app=WebAppInfo(url=miniapp_url))
            )
        else:
            bot.set_chat_menu_button(chat_id, MenuButtonDefault())
    except Exception:
        pass
        
    bot.reply_to(message, welcome_text(full_name), reply_markup=get_main_menu_keyboard(chat_id))

    # Deep link from the H&E VPN app's Plans screen:
    # https://t.me/<bot>?start=buy_<plan_code> opens that plan's purchase
    # screen directly, under the welcome message.
    _btext = getattr(message, "text", "") or ""
    parts = _btext.split(maxsplit=1) if isinstance(_btext, str) else []
    if len(parts) == 2 and parts[1].strip().startswith("buy_"):
        plan_code = parts[1].strip()[4:].strip().lower()
        if plan_code in PLANS:
            try:
                from bot_app.handlers.shop import send_plan_purchase
                send_plan_purchase(chat_id, plan_code)
            except Exception:
                pass


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
