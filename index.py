"""Outline Key Bot — entry point.

The implementation lives in the ``bot_app`` package (handlers, services,
storage, routes). This module is now a thin compatibility shim:

- ``api/index.py`` (Vercel serverless) imports the Flask app via ``bot_app``.
- Local / VPS runs use ``python index.py`` below (polling or webhook mode).
- Common names are re-exported for backward compatibility with older
  scripts/tests that did ``import index``.
"""

import os

from bot_app import app, bot  # noqa: F401  (import registers handlers + routes)

# --- Backward-compatible re-exports (source of truth: bot_app.*) ---
from bot_app.config import (  # noqa: F401
    ADMIN_CHAT_IDS,
    MY_PAYMENT_PHONES,
    OCR_API_KEY,
    OUTLINE_API_URL_1,
    OUTLINE_API_URL_2,
    OUTLINE_API_URL_3,
    PLANS,
    REQUIRED_CHANNEL,
    TELEGRAM_TOKEN,
    admin_chat_ids,
    admin_env_sources,
    admin_ids_masked,
    is_admin,
)
from bot_app.helpers.callback_guard import (  # noqa: F401
    PROCESSED_CALLBACKS,
    is_callback_processed,
)
from bot_app.utils import (  # noqa: F401
    bytes_to_gb,
    clean_ss_url,
    extract_chat_id_from_key_name,
    generate_random_redeem_code,
    is_user_subscribed,
)
from bot_app.services.billing import (  # noqa: F401
    add_expiring_bonus_to_wallet,
    admin_deduct_specific_funds,
    get_user_balance,
    get_user_balance_breakdown,
    load_expiring_credits,
    update_user_balance,
)
from bot_app.services.ocr import (  # noqa: F401
    clean_ocr_text_thoroughly,
    extract_transaction_last6,
    generate_order_id_from_slip,
    parse_slip_ocr,
)
from bot_app.helpers.payment_text import get_payment_instruction_text  # noqa: F401

__all__ = [
    "app", "bot",
    "ADMIN_CHAT_IDS", "MY_PAYMENT_PHONES", "OCR_API_KEY",
    "OUTLINE_API_URL_1", "OUTLINE_API_URL_2", "OUTLINE_API_URL_3",
    "PLANS", "REQUIRED_CHANNEL", "TELEGRAM_TOKEN",
    "admin_chat_ids", "admin_env_sources", "admin_ids_masked", "is_admin",
    "PROCESSED_CALLBACKS", "is_callback_processed",
    "bytes_to_gb", "clean_ss_url", "extract_chat_id_from_key_name",
    "generate_random_redeem_code", "is_user_subscribed",
    "add_expiring_bonus_to_wallet", "admin_deduct_specific_funds",
    "get_user_balance", "get_user_balance_breakdown",
    "load_expiring_credits", "update_user_balance",
    "clean_ocr_text_thoroughly", "extract_transaction_last6",
    "generate_order_id_from_slip", "parse_slip_ocr",
    "get_payment_instruction_text",
    "main",
]


def main() -> None:
    """Local / VPS runner: polling (default) or Flask webhook server."""
    import argparse

    from bot_app.helpers.webhook_guard import polling_conflict

    parser = argparse.ArgumentParser(description="Outline Key Bot runner")
    parser.add_argument("--mode", choices=["polling", "webhook", "hybrid"],
                        default=os.environ.get("BOT_MODE", "webhook"),
                        help="polling: Telegram long-polling, "
                             "webhook: Flask API server, "
                             "hybrid: Flask API server + bot polling thread")
    parser.add_argument("--port", type=int, default=int(os.environ.get("PORT", "5000")))
    parser.add_argument("--webhook-url", default=os.environ.get("WEBHOOK_URL", ""),
                        help="webhook mode မှာ Telegram ကို setWebhook လုပ်မည့် public URL "
                             "(ဥပမာ https://yourdomain.com/webhook)")
    parser.add_argument("--remove-webhook", action="store_true",
                        help="polling မှာ လက်ရှိ webhook ကို ဖျက်ရန် အတိအလင်း ခွင့်ပြုချက် "
                             "(production bot ရဲ့ webhook ဖြစ်နိုင်လို့ default က ငြင်းထားတယ်)")
    args = parser.parse_args()

    if args.mode == "polling":
        allowed, active_url = polling_conflict(bot, allow_remove=args.remove_webhook)
        if not allowed:
            print("⚠️  ဒီ bot မှာ webhook အလုပ်လုပ်နေပါတယ်:")
            print(f"    {active_url}")
            print("    polling run လုပ်ရင် အဲဒီ webhook ကို ဖျက်ရပါမယ် — production bot")
            print("    ဖြစ်နေရင် production delivery လုံးဝ ရပ်သွားပါမယ်။")
            print()
            print("    သေချာပြီဆိုရင်:  python index.py --mode polling --remove-webhook")
            print("    production ကို မထိခိုက်စေချင်ရင် စမ်းသပ် bot (test token) သုံးပါ။")
            return

        print("🤖 Polling mode ဖြင့် Bot စတင်နေသည်... (Ctrl+C ဖြင့် ရပ်ရန်)")
        if active_url:
            print(f"   (webhook ဖျက်လိုက်ပါပြီ: {active_url})")
        try:
            bot.remove_webhook()
        except Exception as e:
            print(f"remove_webhook သတိပေးချက်: {e}")
        bot.infinity_polling(skip_pending=True, timeout=30)
    elif args.mode == "hybrid":
        import threading
        print("🤖 Background Bot Polling စတင်နေသည်...")
        try:
            bot.remove_webhook()
        except Exception:
            pass
        t = threading.Thread(target=lambda: bot.infinity_polling(skip_pending=True, timeout=30), daemon=True)
        t.start()
        print(f"🌐 Flask API server running on http://127.0.0.1:{args.port} (Dashboard backend)")
        app.run(host="0.0.0.0", port=args.port, debug=False)
    else:
        if args.webhook_url:
            try:
                bot.remove_webhook()
                bot.set_webhook(url=args.webhook_url.rstrip("/"))
                print(f"✅ Webhook set: {args.webhook_url.rstrip('/')}")
            except Exception as e:
                print(f"⚠️ setWebhook မအောင်မြင်ပါ: {e}")
        print(f"🌐 Webhook Flask server on port {args.port} ...")
        app.run(host="0.0.0.0", port=args.port, debug=False)




if __name__ == "__main__":
    main()
