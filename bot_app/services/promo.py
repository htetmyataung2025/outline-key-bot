"""Facebook promo keys (Bot Update #18).

The owner posts a promo code on Facebook; a customer who sends that
code in the in-app Support Chat gets one free trial key from the
support agent: 10 GB / 5 days on Server 2, named after the customer.
``create_outline_key`` ends the key name with the expiry date, so the
nightly expiry cron deletes the key automatically when the 5 days
are up. The app's My Keys list is device-local storage, so delivery
is three-way: the agent pastes the key in Support Chat, a Telegram
DM carries a tap-to-copy copy, and the purchase record puts it in
the app's History (a tap there adds it to My Keys). Re-sending the
code re-delivers the same key and repairs a missing History record.

One claim per Telegram account and a hard cap on total claims, both
recorded in KV under ``promo_claims:<code-lower>`` as
``{chat_id: {"ts", "key_name", "expire_date"}}``.
"""

import random
import string
import time

from bot_app.config import is_admin
from bot_app.extensions import bot
from bot_app.helpers.deeplink import get_key_delivery_markup
from bot_app.services.app_notify import push_app_notification
from bot_app.services.orders import (
    load_all_user_history,
    save_key_mapping,
    save_user_purchase_record,
)
from bot_app.services.outline import create_outline_key
from bot_app.services.profiles import get_user_profile
from bot_app.services.registry import load_persistent_keys
from bot_app.storage.kv import redis_delete, redis_get, redis_set, redis_set_nx

PROMO_CODE = "HEFREEFORYOU"
PROMO_SERVER = "2"
PROMO_GB = 10
PROMO_DAYS = 5
PROMO_CAP = 100

_CLAIMS_KEY = f"promo_claims:{PROMO_CODE.lower()}"
_LOCK_KEY = f"{_CLAIMS_KEY}:lock"
_LOCK_TTL_S = 20


def _load_claims() -> dict:
    data = redis_get(_CLAIMS_KEY)
    return data if isinstance(data, dict) else {}


def _dm_key(chat_id: str, vpn_key: str, expire_date: str) -> None:
    """Send the key to the customer's Telegram (tap-to-copy <code>).

    Support Chat text cannot be selected/copied in the app, and the
    app's My Keys list is device-local storage — so the Telegram DM is
    the reliable delivery copy, mirroring the points-redeem flow. The
    key also sits in the app's History (purchase record), where a tap
    adds it to My Keys. Best-effort: a blocked bot must not fail a
    claim that already succeeded.
    """
    try:
        bot.send_message(
            chat_id,
            "🎉 <b>Facebook Promo Key ရရှိပါပြီ!</b>\n\n"
            f"🔑 <b>Key:</b>\n<code>{vpn_key}</code>\n\n"
            f"📦 <b>Data:</b> {PROMO_GB} GB\n"
            f"⏰ <b>သက်တမ်း:</b> {PROMO_DAYS} ရက် (Expire {expire_date})\n"
            f"📡 <b>Server:</b> Server {PROMO_SERVER} (Singapore)\n\n"
            "Key ကို နှိပ်ပြီး copy ကူးနိုင်ပါတယ်။ H&E VPN App ထဲမှာလည်း "
            "Profile → မှတ်တမ်း ထဲက 'Free Promo' ကို နှိပ်ရင် My Keys ထဲ "
            "ထည့်ပြီး တန်း ချိတ်သုံးနိုင်ပါတယ်။",
            parse_mode="HTML",
            reply_markup=get_key_delivery_markup(vpn_key),
        )
    except Exception as e:
        print("Promo DM Error:", e)


def _repair_claim(chat_id: str, claim: dict) -> str:
    """Re-deliver an existing claim: make sure the purchase record the
    app's History reads actually exists (the first claim writes it
    best-effort) and return the key from the registry, or "" if the
    key can no longer be found."""
    key_name = (claim or {}).get("key_name") or ""
    entry = None
    try:
        for k_data in load_persistent_keys().values():
            if k_data.get("name") == key_name:
                entry = k_data
                break
    except Exception as e:
        print("Promo repair registry Error:", e)
    if not entry:
        return ""
    vpn_key = (entry.get("access_url") or "").strip()
    if not vpn_key:
        return ""
    order_id = claim.get("order_id") or entry.get("order_id") or "N/A"
    try:
        history = load_all_user_history().get(str(chat_id), [])
        if not any(r.get("order_id") == order_id for r in history):
            save_user_purchase_record(
                chat_id=chat_id,
                order_id=order_id,
                plan_name="Free Promo (Facebook)",
                disp_gb=f"{PROMO_GB} GB",
                months_count=1,
                price_str="0 Ks (Promo)",
                server_num=str(entry.get("server") or PROMO_SERVER),
                expire_date=entry.get("expire_date")
                or claim.get("expire_date", ""),
                vpn_key=vpn_key,
            )
    except Exception as e:
        print("Promo repair record Error:", e)
    return vpn_key


def promo_bot_message() -> str:
    """The message the Telegram bot sends for ``/start promo`` (Bot
    Update #22). The Facebook post no longer prints the code: people
    follow the post's bot link and the bot hands out the code together
    with the full claim steps — including linking the app first, since
    an unlinked app cannot use Support Chat, where the code is claimed.
    """
    return (
        "🎉 <b>H&E VPN အခမဲ့ Key Promo</b>\n\n"
        f"သင့်ရဲ့ Promo Code: <code>{PROMO_CODE}</code> (နှိပ်ပြီး copy လုပ်ထားပါ)\n\n"
        "<b>Key ရယူနည်း:</b>\n"
        "၁။ H&E VPN App ကို ဖွင့်ပါ\n"
        "၂။ App ထဲမှာ <b>Telegram အကောင့် ချိတ်ပါ</b> — Profile ထဲက "
        "\"Telegram ချိတ်ရန်\" ကို နှိပ်လိုက်ရင် ဒီ Bot ဆီ ပြန်ရောက်လာမယ်, "
        "Start နှိပ်ရုံပဲ (မချိတ်ရသေးရင် Support Chat သုံးလို့ မရပါဘူး)\n"
        "၃။ App → Profile → <b>Support Chat</b> ထဲ ဝင်ပြီး code ကို ပို့ပါ\n"
        f"၄။ ခဏအတွင်း <b>{PROMO_GB} GB / {PROMO_DAYS} ရက်</b> Key ရပါမယ် — "
        "ဒီ Telegram DM ထဲလည်း ပို့ပေးမှာဖြစ်ပြီး App → Profile → "
        "မှတ်တမ်း (History) ကနေလည်း နှိပ်ပြီး သုံးနိုင်ပါတယ်\n\n"
        f"⚠️ တစ်ယောက် တစ်ခါပဲ, လူ {PROMO_CAP} ပြည့်ရင် ပိတ်ပါမယ် ခင်ဗျာ။"
    )


def promo_status() -> dict:
    claims = _load_claims()
    return {
        "claimed": len(claims),
        "cap": PROMO_CAP,
        "remaining": max(0, PROMO_CAP - len(claims)),
    }


def claim_promo_key(chat_id, fallback_name: str = "") -> dict:
    """Issue the promo key for ``chat_id`` (one per account, capped).

    Returns ``{"ok": True, "vpn_key", "key_name", "expire_date", ...}``
    or ``{"ok": False, "error": <already_claimed|cap_reached|busy|
    key_creation_failed|bad_chat_id>}``. A failed creation is NOT
    recorded, so the customer can simply send the code again.
    """
    chat_id = str(chat_id or "").strip()
    if not chat_id:
        return {"ok": False, "error": "bad_chat_id"}

    lock = redis_set_nx(_LOCK_KEY, _LOCK_TTL_S)
    if lock is False:
        return {"ok": False, "error": "busy"}
    try:
        # Admins (the owner) are exempt from the one-per-person rule and
        # the cap, and their claims are not recorded against the cap —
        # the owner needs unlimited test claims to check error cases.
        try:
            admin = bool(is_admin(chat_id))
        except Exception:
            admin = False
        claims = _load_claims()
        prior = claims.get(chat_id) if not admin else None
        if prior:
            # Re-deliver: repair the History record if the first claim's
            # best-effort write missed, DM the key again, and hand the
            # key back so the agent can re-send it in the chat too.
            vpn_key = _repair_claim(chat_id, prior)
            if vpn_key:
                _dm_key(chat_id, vpn_key,
                        prior.get("expire_date", ""))
            return {
                "ok": False,
                "error": "already_claimed",
                "expire_date": prior.get("expire_date", ""),
                "vpn_key": vpn_key,
            }
        if not admin and len(claims) >= PROMO_CAP:
            return {"ok": False, "error": "cap_reached"}

        try:
            profile = get_user_profile(chat_id) or {}
        except Exception:
            profile = {}
        user_name = (
            profile.get("full_name") or fallback_name or "Customer"
        ).strip() or "Customer"

        order_id = "PROMO-" + "".join(
            random.choices(string.ascii_uppercase + string.digits, k=6)
        )
        try:
            vpn_key, key_name, expire_date = create_outline_key(
                PROMO_SERVER,
                user_name,
                custom_gb=PROMO_GB,
                target_chat_id=chat_id,
                custom_days=PROMO_DAYS,
                is_giveaway=True,
                order_id=order_id,
            )
        except Exception:
            vpn_key = key_name = expire_date = None
        if not vpn_key:
            return {"ok": False, "error": "key_creation_failed"}

        if not admin:
            claims[chat_id] = {
                "ts": int(time.time()),
                "key_name": key_name,
                "expire_date": expire_date,
                "order_id": order_id,
            }
            redis_set(_CLAIMS_KEY, claims)

        try:
            save_user_purchase_record(
                chat_id=chat_id,
                order_id=order_id,
                plan_name="Free Promo (Facebook)",
                disp_gb=f"{PROMO_GB} GB",
                months_count=1,
                price_str="0 Ks (Promo)",
                server_num=PROMO_SERVER,
                expire_date=expire_date,
                vpn_key=vpn_key,
            )
            save_key_mapping(user_name.strip().lower(), chat_id)
        except Exception as e:
            print("Promo record Error:", e)
        try:
            push_app_notification(
                chat_id,
                "promo",
                "အခမဲ့ Promo Key ရပါပြီ 🎉",
                f"{PROMO_GB} GB · {PROMO_DAYS} Days · Server {PROMO_SERVER}"
                f" · Expire {expire_date}",
            )
        except Exception:
            pass
        _dm_key(chat_id, vpn_key, expire_date)

        return {
            "ok": True,
            "vpn_key": vpn_key,
            "key_name": key_name,
            "expire_date": expire_date,
            "gb": PROMO_GB,
            "days": PROMO_DAYS,
            "server": PROMO_SERVER,
            "claimed_count": len(claims),
        }
    finally:
        if lock is True:
            try:
                redis_delete(_LOCK_KEY)
            except Exception:
                pass
