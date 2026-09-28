"""Daily Reward (loyalty points) bot UX: claim + redeem-for-Starter.

Text entry (`🎁 Daily Reward`) is routed from ``handlers/menu.py`` into
``build_reward_view``; the callbacks below drive claim / redeem. Key
provisioning on redeem mirrors the wallet-purchase flow in ``handlers/shop.py``
and refunds the points if the server fails to mint a key.
"""

import random
import string

from telebot.types import InlineKeyboardButton, InlineKeyboardMarkup

from bot_app.config import PLANS, points_enabled, points_settings
from bot_app.extensions import bot
from bot_app.handlers.common import send_force_join_message
from bot_app.helpers.callback_guard import is_callback_processed
from bot_app.keyboards import get_back_inline_keyboard
from bot_app.services.orders import save_key_mapping, save_user_purchase_record
from bot_app.services.outline import create_outline_key
from bot_app.services.points import (
    claim_cooldown_remaining, effective_streak, get_points, redeem_starter,
    refund_starter, try_claim,
)
from bot_app.utils import is_user_subscribed

_STARTER_VALID_DAYS = 30


def _fmt_remaining(seconds: int) -> str:
    seconds = max(0, int(seconds))
    h, m = seconds // 3600, (seconds % 3600) // 60
    if h > 0:
        return f"{h} နာရီ {m} မိနစ်"
    if m > 0:
        return f"{m} မိနစ်"
    return f"{seconds} စက္ကန့်"


def _display_name(chat_id, fallback: str = "HMA Customer") -> str:
    try:
        info = bot.get_chat(chat_id)
        name = f"{info.first_name or ''} {getattr(info, 'last_name', '') or ''}".strip()
        return name or fallback
    except Exception:
        return fallback


def build_reward_view(chat_id):
    """Render the Daily Reward panel: balance, streak, cooldown, redeem state.

    Returns ``(text, InlineKeyboardMarkup)``.
    """
    cfg = points_settings()
    cap = int(cfg["balance_cap"])
    starter_cost = int(cfg["starter_cost"])
    streak_target = int(cfg["streak_target_days"])
    cooldown_h = int(cfg["claim_cooldown_h"])
    band_low, band_high = cfg["streak_reward"]

    rec = get_points(chat_id)
    points = int(rec.get("points", 0))
    streak = effective_streak(rec)
    cooldown = claim_cooldown_remaining(rec)
    ready = cooldown <= 0

    if ready:
        next_line = "✅ <b>ယခု Claim လုပ်နိုင်ပါပြီ!</b>"
    else:
        next_line = f"⏳ နောက် Claim အထိ: <b>{_fmt_remaining(cooldown)}</b>"

    if not rec.get("has_topped_up"):
        redeem_hint = "🔒 <i>လဲယူရန် အနည်းဆုံး တစ်ကြိမ် ငွေဖြည့်ရန် လိုအပ်ပါသည်။</i>"
    elif points < starter_cost:
        redeem_hint = f"💡 <i>လဲယူရန် နောက်ထပ် {starter_cost - points:,} Points လိုအပ်ပါသည်။</i>"
    else:
        redeem_hint = "✅ <i>Starter Plan လဲယူရန် အသင့်ဖြစ်ပါပြီ!</i>"

    text = (
        f"🎁 <b>Daily Reward — Points</b>\n\n"
        f"💎 <b>လက်ရှိ Points:</b> {points:,} / {cap:,}\n"
        f"🔥 <b>ဆက်တိုက် Claim:</b> {streak} ရက်\n"
        f"{next_line}\n\n"
        f"🎫 <b>Starter Plan</b> (25GB / {_STARTER_VALID_DAYS} ရက်) = <b>{starter_cost:,} Points</b>\n"
        f"{redeem_hint}\n\n"
        f"💡 <i>{cooldown_h} နာရီ တစ်ကြိမ် Claim လုပ်၍ Points ရယူပါ။ {streak_target} ရက် ဆက်တိုက် Claim လုပ်ပါက "
        f"Points ({band_low} မှ {band_high}) ကြား ရရှိရန် အာမခံပါသည်။</i>"
    )

    markup = InlineKeyboardMarkup()
    if ready:
        markup.row(InlineKeyboardButton("🎁 Claim Now", callback_data="points_claim"))
    else:
        markup.row(InlineKeyboardButton("🔄 Refresh", callback_data="points_view"))
    if rec.get("has_topped_up") and points >= starter_cost:
        markup.row(InlineKeyboardButton(
            f"🎫 Starter Plan လဲမည် ({starter_cost:,})", callback_data="points_redeem"))
    markup.row(InlineKeyboardButton("🔙 မူလ Menu သို့ ပြန်သွားရန်", callback_data="back_to_main"))
    return text, markup


_DISABLED_NOTICE = "🎁 Daily Reward စနစ်ကို ယာယီ ပိတ်ထားပါသည်။"


def _reward_disabled() -> bool:
    try:
        return not points_enabled()
    except Exception:
        return False


def _refresh_panel(chat_id, message_id):
    text, markup = build_reward_view(chat_id)
    try:
        bot.edit_message_text(text, chat_id=chat_id, message_id=message_id,
                              parse_mode="HTML", reply_markup=markup)
    except Exception:
        bot.send_message(chat_id, text, parse_mode="HTML", reply_markup=markup)


@bot.callback_query_handler(func=lambda call: call.data == "points_view")
def handle_points_view(call):
    bot.answer_callback_query(call.id)
    _refresh_panel(call.message.chat.id, call.message.message_id)


@bot.callback_query_handler(func=lambda call: call.data == "points_claim")
def handle_points_claim(call):
    chat_id = call.message.chat.id
    if _reward_disabled():
        bot.answer_callback_query(call.id, _DISABLED_NOTICE, show_alert=True)
        return
    if not is_user_subscribed(chat_id):
        bot.answer_callback_query(call.id)
        send_force_join_message(chat_id)
        return

    res = try_claim(chat_id)
    if not res.get("ok"):
        if res.get("error") == "cooldown":
            bot.answer_callback_query(
                call.id, f"⏳ နောက် Claim အထိ {_fmt_remaining(res.get('next_in_s', 0))} ကျန်ပါသည်။",
                show_alert=True)
        else:
            bot.answer_callback_query(call.id, "⏳ ခဏစောင့်ပြီး ထပ်ကြိုးစားပါ။", show_alert=True)
        _refresh_panel(chat_id, call.message.message_id)
        return

    awarded = res.get("awarded", 0)
    if res.get("is_streak_bonus"):
        popup = f"🎉 +{awarded:,} Points ({res.get('streak_days')} ရက် ဆက်တိုက်! 🔥)"
    else:
        popup = f"🎉 +{awarded:,} Points ရရှိပါပြီ!"
    if res.get("discarded", 0) > 0:
        popup += " (Points အပြည့် ဖြစ်နေပါပြီ)"
    bot.answer_callback_query(call.id, popup, show_alert=True)
    _refresh_panel(chat_id, call.message.message_id)


@bot.callback_query_handler(func=lambda call: call.data == "points_redeem")
def handle_points_redeem_confirm(call):
    """Show a confirmation step before spending points on a Starter Plan."""
    bot.answer_callback_query(call.id)
    chat_id = call.message.chat.id
    if _reward_disabled():
        bot.answer_callback_query(call.id, _DISABLED_NOTICE, show_alert=True)
        return
    starter_cost = int(points_settings()["starter_cost"])
    rec = get_points(chat_id)
    if not rec.get("has_topped_up"):
        bot.answer_callback_query(call.id, "🔒 လဲယူရန် အနည်းဆုံး တစ်ကြိမ် ငွေဖြည့်ရန် လိုအပ်ပါသည်။", show_alert=True)
        return
    if int(rec.get("points", 0)) < starter_cost:
        bot.answer_callback_query(call.id, "❌ Points မလုံလောက်ပါ။", show_alert=True)
        return

    text = (
        f"🎫 <b>Starter Plan လဲယူခြင်း</b>\n\n"
        f"💎 သုံးစွဲမည့် Points: <b>{starter_cost:,}</b>\n"
        f"🛍️ ရရှိမည့် Plan: <b>Starter Plan (25GB / {_STARTER_VALID_DAYS} ရက်)</b>\n\n"
        f"👇 လဲယူရန် သေချာပါက အောက်ပါခလုတ်ကို နှိပ်ပါ:"
    )
    markup = InlineKeyboardMarkup()
    markup.row(InlineKeyboardButton("✅ အတည်ပြု လဲယူမည်", callback_data="points_redeem_do"))
    markup.row(InlineKeyboardButton("🔙 ပြန်သွားရန်", callback_data="points_view"))
    try:
        bot.edit_message_text(text, chat_id=chat_id, message_id=call.message.message_id,
                              parse_mode="HTML", reply_markup=markup)
    except Exception:
        bot.send_message(chat_id, text, parse_mode="HTML", reply_markup=markup)


@bot.callback_query_handler(func=lambda call: call.data == "points_redeem_do")
def handle_points_redeem_do(call):
    bot.answer_callback_query(call.id)
    chat_id = call.message.chat.id

    if _reward_disabled():
        bot.answer_callback_query(call.id, _DISABLED_NOTICE, show_alert=True)
        return
    if not is_user_subscribed(chat_id):
        send_force_join_message(chat_id)
        return

    # One redemption per tap: guard the deduction against a double-fire.
    lock_key = f"points_redeem_{call.message.message_id}_{chat_id}"
    if is_callback_processed(lock_key):
        return

    res = redeem_starter(chat_id)
    if not res.get("ok"):
        reason = {
            "needs_topup": "🔒 လဲယူရန် အနည်းဆုံး တစ်ကြိမ် ငွေဖြည့်ရန် လိုအပ်ပါသည်။",
            "insufficient_points": "❌ Points မလုံလောက်ပါ။",
        }.get(res.get("error"), "❌ လဲယူ၍ မရနိုင်သေးပါ။")
        bot.answer_callback_query(call.id, reason, show_alert=True)
        _refresh_panel(chat_id, call.message.message_id)
        return

    # Points already deducted — now mint the Starter key; refund on any failure.
    order_id = "PTS-" + "".join(random.choices(string.ascii_uppercase + string.digits, k=6))
    user_name = _display_name(chat_id)
    plan = PLANS.get("starter") or {"name": "Starter Plan", "data": "25 GB", "bytes": 25 * 1000**3}
    vpn_key = key_name = expire_date = None
    try:
        vpn_key, key_name, expire_date = create_outline_key(
            "1", user_name, plan_info=plan, target_chat_id=chat_id,
            custom_days=_STARTER_VALID_DAYS, is_giveaway=True, order_id=order_id,
        )
    except Exception:
        vpn_key = None

    if not vpn_key:
        refund = refund_starter(chat_id)
        spent = int(points_settings()["starter_cost"])
        bot.send_message(
            chat_id,
            f"❌ <b>ဆာဗာလိုင်းမရသဖြင့် Key ထုတ်မရပါ။</b>\n\n"
            f"💎 သုံးထားသော <b>{spent:,} Points</b> အား ပြန်လည် ထည့်သွင်းပေးထားပါသည် "
            f"(လက်ကျန်: {refund.get('new_balance', 0):,} Points)။ ကျေးဇူးပြု၍ ခဏနေ ပြန်ကြိုးစားပါ။",
            parse_mode="HTML", reply_markup=get_back_inline_keyboard())
        return

    save_user_purchase_record(
        chat_id=chat_id, order_id=order_id, plan_name=f"{plan['name']} (Points Reward)",
        disp_gb=plan.get("data", "25 GB"), months_count=1, price_str="0 Ks (Points)",
        server_num="1", expire_date=expire_date, vpn_key=vpn_key,
    )
    save_key_mapping(user_name.strip().lower(), chat_id)

    success_text = (
        f"🎉 <b>Points ဖြင့် Starter Plan လဲယူမှု အောင်မြင်ပါသည်!</b>\n\n"
        f"🧾 <b>Order ID:</b> <code>{order_id}</code>\n\n"
        f"🛍️ <b>Plan:</b> {plan['name']} ({plan.get('data', '25 GB')})\n\n"
        f"📡 <b>Server:</b> Singapore Server 1 🇸🇬\n\n"
        f"⏰ <b>သက်တမ်းကုန်ဆုံးရက်:</b> {expire_date}\n\n"
        f"💎 <b>ကျန်ရှိ Points:</b> {res.get('new_balance', 0):,}\n\n"
        f"🔑 <b>လူကြီးမင်း၏ VPN Key:</b>\n\n"
        f"<code>{vpn_key}</code>\n\n"
        f"☝️ အပေါ်က Key ကို <b>တစ်ချက်တည်း နှိပ်လိုက်ရုံဖြင့်</b> Auto Copy ကူးသွားပါလိမ့်မယ်ခင်ဗျာ။ "
        f"V2BOX VPN App ထဲသို့ ထည့်သွင်းအသုံးပြုနိုင်ပါပြီ။"
    )
    try:
        bot.edit_message_text(success_text, chat_id=chat_id, message_id=call.message.message_id,
                              parse_mode="HTML", reply_markup=get_back_inline_keyboard())
    except Exception:
        bot.send_message(chat_id, success_text, parse_mode="HTML", reply_markup=get_back_inline_keyboard())

