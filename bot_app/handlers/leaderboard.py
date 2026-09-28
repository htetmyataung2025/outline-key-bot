"""Points Leaderboard bot UX: 7-Day (weekly, auto-reset) & Total boards.

The player list is rendered as styled HTML text (medals + highlighted self
row); inline buttons drive only the 7-Day↔Total toggle, Refresh and Back. Names
are resolved from the profile store — zero ``bot.get_chat`` calls per render.
``/lb_reset`` (admin-only, no menu UI) re-anchors the weekly period to today.
"""

from telebot.apihelper import ApiTelegramException
from telebot.types import InlineKeyboardButton, InlineKeyboardMarkup

from bot_app.config import is_admin, points_enabled
from bot_app.extensions import bot
from bot_app.services.leaderboard import build_leaderboard
from bot_app.services.points import load_all_points
from bot_app.services.profiles import load_all_profiles
from bot_app.timeutil import myanmar_now

_MEDALS = {1: "🥇", 2: "🥈", 3: "🥉"}
_DISABLED = "🏆 <b>Leaderboard ကို ယာယီ ပိတ်ထားပါသည်။</b>"


def _rank_label(rank: int) -> str:
    return _MEDALS.get(rank, f"{rank}.")


def build_leaderboard_view(chat_id, mode: str = "7d"):
    """Return ``(text, InlineKeyboardMarkup)`` for the given board mode."""
    board = build_leaderboard(load_all_points(), load_all_profiles(),
                              mode, chat_id, myanmar_now())
    mode = board["mode"]
    subtitle = "💎 စုစုပေါင်း (Total)" if mode == "total" else "🗓 ဒီအပတ် (7 ရက်)"
    lines = [f"🏆 <b>Points Leaderboard</b> — {subtitle}", ""]

    if not board["rows"]:
        empty = ("ဒီအပတ် ဘယ်သူမှ Points မရသေးပါ။" if mode != "total"
                 else "Points စာရင်း မရှိသေးပါ။")
        lines.append(empty)
    else:
        for row in board["rows"]:
            name = f"<b>{row['name']}</b>" if row["is_me"] else row["name"]
            prefix = "▶ " if row["is_me"] else ""
            lines.append(f"{prefix}{_rank_label(row['rank'])} {name} — <b>{row['score']:,}</b>")

    me = board["me"]
    if me:
        lines.append("─────────────")
        if me["rank"]:
            lines.append(f"▶ <b>{me['rank']}. {me['name']} (သင်) — {me['score']:,}</b>")
        else:
            lines.append(f"▶ <b>{me['name']} (သင်)</b> — Points မရသေးပါ")

    return "\n".join(lines), _markup(mode)


def _markup(mode: str) -> InlineKeyboardMarkup:
    markup = InlineKeyboardMarkup()
    if mode == "total":
        markup.row(InlineKeyboardButton("🗓 7-Day", callback_data="lb_7d"),
                   InlineKeyboardButton("💎 Total ✓", callback_data="lb_total"))
        refresh = "lb_refresh_total"
    else:
        markup.row(InlineKeyboardButton("🗓 7-Day ✓", callback_data="lb_7d"),
                   InlineKeyboardButton("💎 Total", callback_data="lb_total"))
        refresh = "lb_refresh_7d"
    markup.row(InlineKeyboardButton("🔄 Refresh", callback_data=refresh),
               InlineKeyboardButton("🔙 မူလ Menu", callback_data="back_to_main"))
    return markup


def _edit_in_place(chat_id, message_id, text, markup):
    try:
        bot.edit_message_text(text, chat_id=chat_id, message_id=message_id,
                              parse_mode="HTML", reply_markup=markup)
    except ApiTelegramException as e:
        # Identical content (e.g. re-tapping the active board) → no-op, never a
        # duplicate message; only a genuinely un-editable message falls back.
        if "message is not modified" in str(getattr(e, "description", "") or e).lower():
            return
        bot.send_message(chat_id, text, parse_mode="HTML", reply_markup=markup)
    except Exception:
        bot.send_message(chat_id, text, parse_mode="HTML", reply_markup=markup)


@bot.callback_query_handler(
    func=lambda c: c.data in ("lb_7d", "lb_total", "lb_refresh_7d", "lb_refresh_total"))
def handle_leaderboard_toggle(call):
    bot.answer_callback_query(call.id)
    chat_id = call.message.chat.id
    if not points_enabled():
        _edit_in_place(chat_id, call.message.message_id, _DISABLED, None)
        return
    mode = "total" if call.data in ("lb_total", "lb_refresh_total") else "7d"
    text, markup = build_leaderboard_view(chat_id, mode)
    _edit_in_place(chat_id, call.message.message_id, text, markup)


@bot.message_handler(commands=["lb_reset"])
def handle_lb_reset(message):
    """Admin-only: re-anchor the 7-Day period to today (board resets to empty).
    No menu button — a hidden typed command for the owner."""
    chat_id = message.chat.id
    if not is_admin(chat_id):
        return
    from bot_app.services.settings import get_system_settings, save_system_settings

    today = myanmar_now().strftime("%Y-%m-%d")
    current = get_system_settings().get("points") or {}
    save_system_settings({"points": {**current, "leaderboard_epoch": today}},
                         updated_by=str(chat_id))
    bot.send_message(
        chat_id,
        "♻️ <b>7-Day Leaderboard ကို reset လုပ်ပြီးပါပြီ။</b>\n\n"
        f"အသစ် စတင်ရက်: <b>{today}</b>\n"
        "နောက် ၇ ရက် cycle ကို ဒီနေ့ကနေ ပြန်စပါမည်။",
        parse_mode="HTML",
    )
