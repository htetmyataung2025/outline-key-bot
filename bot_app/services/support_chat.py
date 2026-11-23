"""In-app Support Chat: customer (native app) <-> admins (Telegram).

Flow
----
- The customer writes from the app (``POST /api/app/support/send``); the
  message is appended to their thread here and forwarded to every admin
  on Telegram with presence buttons attached.
- An admin answers with Telegram's *Reply* gesture on a forwarded
  message; the webhook routes that text back into the thread and the
  customer gets it in the app + as a phone notification.
- When the owner is away, the Muse support agent answers safe
  questions through the agent endpoints (``/api/app/support/agent/*``,
  secret-header auth). Presence is a handover flag: while the owner is
  marked present the agent stays out completely.

Storage (Redis KV, file fallback in dev/tests):
- ``support_thread:<chat_id>`` — list of {from, text, ts}, newest last,
  capped at ``_MAX_MSGS``. ``from`` is "user" | "admin" | "Muse".
- ``support_index`` — {chat_id: {name, updated, escalated}} thread index.
- ``support_fwd_map`` — {"<admin_chat>:<message_id>": customer chat_id}.
- ``support_presence`` — {"ts": epoch} owner-present marker (1 h TTL).

All functions are best-effort: a support failure must never break the
webhook or the money flows.
"""

import html
import time

from telebot.types import InlineKeyboardButton, InlineKeyboardMarkup

from bot_app.config import ADMIN_CHAT_IDS
from bot_app.extensions import bot
from bot_app.storage.kv import redis_delete, redis_get, redis_set

_MAX_MSGS = 100
_MAX_FWD = 300
_PRESENCE_TTL_S = 60 * 60
_INDEX_KEY = "support_index"
_FWD_KEY = "support_fwd_map"
_PRESENCE_KEY = "support_presence"


def _now() -> int:
    return int(time.time())


def _thread_key(chat_id) -> str:
    return f"support_thread:{chat_id}"


# --- thread storage ---------------------------------------------------------

def load_thread(chat_id) -> list:
    items = redis_get(_thread_key(chat_id))
    return items if isinstance(items, list) else []


def _save_thread(chat_id, msgs) -> None:
    redis_set(_thread_key(chat_id), msgs[-_MAX_MSGS:])


def _load_index() -> dict:
    idx = redis_get(_INDEX_KEY)
    return idx if isinstance(idx, dict) else {}


def _touch_index(chat_id, name=None, escalated=None) -> None:
    idx = _load_index()
    entry = idx.get(str(chat_id)) or {}
    if name:
        entry["name"] = name
    entry["updated"] = _now()
    if escalated is not None:
        entry["escalated"] = bool(escalated)
    idx[str(chat_id)] = entry
    redis_set(_INDEX_KEY, idx)


def append_message(chat_id, sender: str, text: str, mtype: str = None,
                   file_id: str = None) -> dict:
    msg = {"from": sender, "text": text, "ts": _now()}
    if mtype:
        msg["type"] = mtype
    if file_id:
        msg["file_id"] = file_id
    msgs = load_thread(chat_id)
    msgs.append(msg)
    _save_thread(chat_id, msgs)
    if sender == "user":
        _touch_index(chat_id, escalated=False)
    else:
        _touch_index(chat_id)
    return msg


def clear_thread(chat_id) -> None:
    """Delete a customer's whole support thread (Bot Update #14).

    The app calls this when the customer leaves the Support Chat: the
    owner wants the history wiped on exit so every visit starts fresh.
    Removes the thread, its index entry and any admin forward-map
    entries pointing at it. Best-effort like everything in this module.
    """
    try:
        redis_delete(_thread_key(chat_id))
    except Exception:
        pass
    try:
        idx = _load_index()
        if str(chat_id) in idx:
            del idx[str(chat_id)]
            redis_set(_INDEX_KEY, idx)
    except Exception:
        pass
    try:
        fwd = redis_get(_FWD_KEY)
        if isinstance(fwd, dict):
            kept = {k: v for k, v in fwd.items() if str(v) != str(chat_id)}
            if len(kept) != len(fwd):
                redis_set(_FWD_KEY, kept)
    except Exception:
        pass


# --- owner presence (handover flag) -----------------------------------------

def owner_present() -> bool:
    data = redis_get(_PRESENCE_KEY)
    if not isinstance(data, dict):
        return False
    ts = data.get("ts")
    return isinstance(ts, (int, float)) and (_now() - int(ts)) < _PRESENCE_TTL_S


def set_owner_present(present: bool) -> bool:
    redis_set(_PRESENCE_KEY, {"ts": _now()} if present else {"ts": 0})
    return owner_present()


# --- agent typing indicator (Bot Update #24) --------------------------------
# The app shows a Messenger-style "typing…" bubble while the support agent
# composes a reply. The flag is a short-TTL timestamp: the agent sets it
# when it starts working on a thread, refreshes it if composing runs long,
# and clears it when the reply (or an escalation) lands — so a crashed run
# can never leave a customer staring at dots for more than the TTL.

_TYPING_KEY = "support_typing:"  # + chat_id -> {"ts": epoch}
_TYPING_TTL_S = 45


def set_agent_typing(chat_id, typing: bool) -> None:
    key = _TYPING_KEY + str(chat_id)
    if typing:
        redis_set(key, {"ts": _now()})
    else:
        redis_delete(key)


def agent_typing(chat_id) -> bool:
    data = redis_get(_TYPING_KEY + str(chat_id))
    if not isinstance(data, dict):
        return False
    ts = data.get("ts")
    return isinstance(ts, (int, float)) and (_now() - int(ts)) < _TYPING_TTL_S


# --- customer -> admins -------------------------------------------------------

def _presence_markup() -> InlineKeyboardMarkup:
    markup = InlineKeyboardMarkup()
    markup.row(
        InlineKeyboardButton("🙋 ရောက်ပြီ — Muse ရပ်", callback_data="sup_here"),
        InlineKeyboardButton("🤖 Muse ဆက်ဖြေ", callback_data="sup_away"),
    )
    return markup


def forward_to_admins(chat_id, name: str, text: str) -> None:
    """Forward a customer message to every admin; remember the message
    ids so an admin's Telegram Reply can be routed back to this thread."""
    header = (
        "💬 <b>Support Chat</b>\n"
        f"👤 {html.escape(name or '')} (<code>{chat_id}</code>)\n\n"
        f"{html.escape(text)}"
    )
    fwd = redis_get(_FWD_KEY)
    if not isinstance(fwd, dict):
        fwd = {}
    for aid in ADMIN_CHAT_IDS:
        try:
            res = bot.send_message(aid, header, parse_mode="HTML",
                                   reply_markup=_presence_markup())
            mid = getattr(res, "message_id", None)
            if mid:
                fwd[f"{aid}:{mid}"] = str(chat_id)
        except Exception:
            pass
    # Keep the map bounded (oldest entries drop out first).
    if len(fwd) > _MAX_FWD:
        fwd = dict(list(fwd.items())[-_MAX_FWD:])
    redis_set(_FWD_KEY, fwd)


def customer_say(chat_id, name: str, text: str) -> dict:
    chat_id = str(chat_id)
    msg = append_message(chat_id, "user", text)
    _touch_index(chat_id, name=name)
    try:
        forward_to_admins(chat_id, name, text)
    except Exception:
        pass
    return msg


def customer_say_photo(chat_id, name: str, image_bytes: bytes,
                       caption: str = "") -> dict | None:
    """Customer sends a photo (e.g. an error screenshot) from the app.

    Telegram hosts the image: the photo is forwarded to every admin and
    the Telegram file_id of the first successful send is stored in the
    thread, so the app and the agent can fetch the bytes back through
    the photo proxy endpoints. Returns the thread message, or None when
    the photo reached no admin (nothing is stored then, so the app can
    ask the customer to retry).
    """
    import io

    chat_id = str(chat_id)
    header = (
        "💬 <b>Support Chat</b>\n"
        f"👤 {html.escape(name or '')} (<code>{chat_id}</code>)\n\n"
        "📷 <i>ပုံ ပို့ထားပါတယ်</i>"
    )
    if caption:
        header += f"\n{html.escape(caption)}"
    fwd = redis_get(_FWD_KEY)
    if not isinstance(fwd, dict):
        fwd = {}
    file_id = None
    for aid in ADMIN_CHAT_IDS:
        try:
            bio = io.BytesIO(image_bytes)
            bio.name = "support-photo.jpg"
            res = bot.send_photo(aid, bio, caption=header, parse_mode="HTML",
                                 reply_markup=_presence_markup())
            photos = getattr(res, "photo", None) or []
            if photos and file_id is None:
                file_id = getattr(photos[-1], "file_id", None)
            mid = getattr(res, "message_id", None)
            if mid:
                fwd[f"{aid}:{mid}"] = str(chat_id)
        except Exception:
            pass
    if len(fwd) > _MAX_FWD:
        fwd = dict(list(fwd.items())[-_MAX_FWD:])
    redis_set(_FWD_KEY, fwd)
    if not file_id:
        return None
    msg = append_message(chat_id, "user", caption or "", mtype="photo",
                         file_id=file_id)
    _touch_index(chat_id, name=name)
    return msg


def fetch_photo_bytes(file_id: str) -> bytes | None:
    """Download a support photo back from Telegram (best effort)."""
    if not file_id:
        return None
    try:
        info = bot.get_file(file_id)
        path = getattr(info, "file_path", None)
        if not path:
            return None
        data = bot.download_file(path)
        return bytes(data) if isinstance(data, (bytes, bytearray)) else None
    except Exception:
        return None


# --- admin -> customer --------------------------------------------------------

def admin_reply(admin_chat_id, reply_to_message_id, text: str) -> bool:
    """Route an admin's Telegram Reply back into the customer's thread.

    Returns True when the replied-to message was a support forward.
    """
    fwd = redis_get(_FWD_KEY)
    if not isinstance(fwd, dict):
        return False
    customer = fwd.get(f"{admin_chat_id}:{reply_to_message_id}")
    if not customer:
        return False
    append_message(customer, "admin", text)
    # An admin actively answering counts as being present.
    set_owner_present(True)
    # Support replies deliberately stay OUT of the app inbox: chat
    # back-and-forth would eat its 30-item cap and push out real
    # announcements (owner decision, 2026-11-20). The app detects new
    # support replies straight from the thread for its notification.
    return True


def admin_reply_photo(admin_chat_id, reply_to_message_id, file_id: str,
                      caption: str = "") -> bool:
    """Route an admin's Telegram photo Reply back into the thread."""
    fwd = redis_get(_FWD_KEY)
    if not isinstance(fwd, dict):
        return False
    customer = fwd.get(f"{admin_chat_id}:{reply_to_message_id}")
    if not customer:
        return False
    append_message(customer, "admin", caption or "", mtype="photo",
                   file_id=file_id)
    # An admin actively answering counts as being present.
    set_owner_present(True)
    return True


# --- Muse agent ---------------------------------------------------------------

def agent_reply(chat_id, text: str) -> tuple:
    """Post a reply as the Muse support agent.

    Returns ("ok", msg) | ("owner_present", None) — the presence guard is
    re-checked here so a race with the owner arriving can never produce
    a double answer.
    """
    if owner_present():
        return "owner_present", None
    chat_id = str(chat_id)
    msg = append_message(chat_id, "Muse", text)
    set_agent_typing(chat_id, False)
    # No inbox push here either — see admin_reply (30-item inbox cap).
    note = (
        "🤖 <b>H&E Agent ဖြေပြီး</b>\n"
        f"👤 Customer: <code>{chat_id}</code>\n\n"
        f"{html.escape(text)}"
    )
    for aid in ADMIN_CHAT_IDS:
        try:
            bot.send_message(aid, note, parse_mode="HTML")
        except Exception:
            pass
    return "ok", msg


def escalate(chat_id, summary: str) -> None:
    """Hand a thread to the owner unanswered (money/complaint cases)."""
    chat_id = str(chat_id)
    set_agent_typing(chat_id, False)
    _touch_index(chat_id, escalated=True)
    note = (
        "🚨 <b>Support Escalation</b>\n"
        f"👤 Customer: <code>{chat_id}</code>\n\n"
        f"{html.escape(summary)}"
    )
    for aid in ADMIN_CHAT_IDS:
        try:
            bot.send_message(aid, note, parse_mode="HTML")
        except Exception:
            pass


def pending_threads() -> list:
    """Threads whose last message is an unanswered customer message."""
    idx = _load_index()
    out = []
    for cid, meta in idx.items():
        msgs = load_thread(cid)
        if not msgs or msgs[-1].get("from") != "user":
            continue
        out.append({
            "chat_id": cid,
            "name": (meta or {}).get("name", ""),
            "updated": (meta or {}).get("updated"),
            "escalated": bool((meta or {}).get("escalated")),
            "messages": msgs,
        })
    out.sort(key=lambda t: t.get("updated") or 0)
    return out
