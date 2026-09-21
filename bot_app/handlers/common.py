"""Shared handler helpers: force-join prompt, admin check, /myid diagnostic."""

from bot_app.config import admin_chat_ids, is_admin
from bot_app.extensions import bot
from bot_app.keyboards import get_force_join_keyboard
from bot_app.texts import force_join_text


def send_force_join_message(chat_id) -> None:
    """Prompt a non-subscribed user to join the channel (with Verify button)."""
    bot.send_message(chat_id, force_join_text(), parse_mode="HTML",
                     reply_markup=get_force_join_keyboard())


@bot.message_handler(commands=["myid"])
def handle_myid(message):
    """Show the caller's Telegram ids — setup/debug helper for admin access.

    Registered before the force-join gate (and before the text router) so it
    always answers, even for a user who is locked out of the channel gate.
    Admins additionally see exactly which ids the running deployment parsed,
    which is the fastest way to debug a missing/renamed ADMIN_CHAT_IDS env var.
    """
    chat_id = message.chat.id
    user_id = getattr(message.from_user, "id", None) or chat_id
    ids = admin_chat_ids()
    admin_ok = is_admin(chat_id)

    lines = [
        "🆔 <b>သင့် Telegram ID</b>",
        "",
        f"👤 Chat ID : <code>{chat_id}</code>",
        f"🆔 User ID : <code>{user_id}</code>",
        f"👑 Admin : {'✅ ဖြစ်ပါသည်' if admin_ok else '❌ မဟုတ်ပါ'}",
    ]

    if admin_ok:
        shown = ", ".join(ids) if ids else "(none)"
        lines += ["", f"⚙️ ဒီ deployment ဖတ်ထားတဲ့ admin IDs ({len(ids)}): <code>{shown}</code>"]
        if not ids:
            lines += ["", "⚠️ <b>ADMIN_CHAT_IDS မရှိပါ။</b> Vercel → Settings → Environment "
                          "Variables မှာ ထည့်ပြီး <b>Redeploy</b> လုပ်ပါ — env var အသစ်က "
                          "deployment အသစ်မှာသာ ရောက်ပါတယ်။"]
    else:
        lines += ["", "💡 Admin ဖြစ်ပါက ဒီ <b>Chat ID</b> ကို Vercel → ADMIN_CHAT_IDS ထဲ "
                      "ထည့်ပြီး Redeploy လုပ်ပါ။ (စာလုံးပွား/ကော်မာ/နေရာလွတ် ပါလည်း "
                      "ဖတ်နိုင်ပါတယ်)"]

    bot.reply_to(message, "\n".join(lines), parse_mode="HTML")


