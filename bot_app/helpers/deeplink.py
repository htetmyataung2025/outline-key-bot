"""One-tap key import links (Open in Outline / INCY).

Telegram inline URL buttons only accept http(s)/tg:// — a raw ``ss://`` link
is rejected with BUTTON_URL_INVALID — so the buttons point at a signed https
landing page (``/go/<token>`` in routes.py) that fires the target app's URL
scheme. Tokens are HMAC-signed (server, key_id) pairs; the ss:// secret never
travels in the button URL and the endpoint is not enumerable.

App support (researched 2026-10, see memory/2026-10-01_PROGRESS.md):
- Outline registers ``ss://`` on Android+iOS → direct link works.
- INCY documents ``incy://add/{url}`` → works with the raw ss:// appended.
- V2Box: ``v2box://install-config?url=<encoded config>`` (App Store changelog;
  needs an up-to-date app) → the page percent-encodes the ss:// URL.
"""

import base64
import hashlib
import hmac

from telebot.types import InlineKeyboardButton, InlineKeyboardMarkup

from bot_app.config import DASHBOARD_URL, TELEGRAM_TOKEN
from bot_app.keyboards import get_back_inline_keyboard
from bot_app.services.registry import load_persistent_keys

_GO_SALT = b"outline-key-bot:go-link-v1"


def _sig_secret() -> bytes:
    return hmac.new(_GO_SALT, TELEGRAM_TOKEN.encode(), hashlib.sha256).digest()


def make_go_token(server_num, key_id) -> str:
    """Opaque, unguessable handle for (server, key) — no key data embedded."""
    payload = f"{server_num}:{key_id}".encode()
    sig = hmac.new(_sig_secret(), payload, hashlib.sha256).hexdigest()[:16]
    return base64.urlsafe_b64encode(payload + b":" + sig.encode()).decode().rstrip("=")


def verify_go_token(token) -> tuple | None:
    """Return (server_num, key_id) for a valid token, else None."""
    try:
        raw = base64.urlsafe_b64decode(token + "=" * (-len(token) % 4)).decode()
        body, _, sig = raw.rpartition(":")
        if not body or len(sig) != 16:
            return None
        server, _, key_id = body.partition(":")
        if not server or not key_id:
            return None
        expected = hmac.new(_sig_secret(), body.encode(), hashlib.sha256).hexdigest()[:16]
        if not hmac.compare_digest(sig, expected):
            return None
        return server, key_id
    except Exception:
        return None


def _url_base(access_url: str) -> str:
    """ss:// config without the #name fragment — names get rewritten, bases don't."""
    return (access_url or "").split("#", 1)[0].strip()


def find_key_ref_by_url(access_url: str) -> tuple | None:
    """Locate (server_num, key_id) in the persistent registry for an access URL."""
    needle = _url_base(access_url)
    if not needle:
        return None
    for entry in load_persistent_keys().values():
        if _url_base(entry.get("access_url", "")) == needle:
            return str(entry.get("server")), str(entry.get("key_id"))
    return None


def get_key_import_keyboard(access_url: str) -> InlineKeyboardMarkup | None:
    """One-tap import buttons for a delivered key; None if the key is not
    in the registry (e.g. admin-pasted custom text) → callers fall back."""
    ref = find_key_ref_by_url(access_url)
    if not ref:
        return None
    go_url = f"{DASHBOARD_URL}/go/{make_go_token(*ref)}"
    markup = InlineKeyboardMarkup()
    markup.row(InlineKeyboardButton("📲 Outline တွင် တစ်ခါထဲ ထည့်ရန်", url=f"{go_url}?app=outline"))
    markup.row(InlineKeyboardButton("🟩 V2Box တွင် တစ်ခါထဲ ထည့်ရန်", url=f"{go_url}?app=v2box"))
    markup.row(InlineKeyboardButton("🧩 INCY တွင် တစ်ခါထဲ ထည့်ရန်", url=f"{go_url}?app=incy"))
    return markup


def get_key_delivery_markup(access_url: str) -> InlineKeyboardMarkup:
    """Import buttons + the usual back row; falls back to the plain back
    keyboard when no /go link can be built for this key."""
    markup = get_key_import_keyboard(access_url)
    if markup is None:
        return get_back_inline_keyboard()
    for row in get_back_inline_keyboard().keyboard:
        markup.row(*row)
    return markup
