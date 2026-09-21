"""Central settings. Env-first; safe dummy defaults for import/tests.

Production must set real secrets via environment (.env / Vercel env vars).
Hardcoded production secrets were removed on purpose (they leaked in git
history). Missing values degrade gracefully: bot features that need them
return friendly errors instead of crashing at import time.
"""

import os

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:  # pragma: no cover - production always has python-dotenv
    pass

# Dummy token keeps `import bot_app.*` working in CI without secrets.
# Real deployments MUST set TELEGRAM_TOKEN env var.
TELEGRAM_TOKEN = os.environ.get("TELEGRAM_TOKEN", "0000000000:AAADummyTokenForTestsOnly00000000000")

REQUIRED_CHANNEL = os.environ.get("REQUIRED_CHANNEL", "@hefeature")

OUTLINE_API_URL_1 = os.environ.get("OUTLINE_API_URL_1", "")
OUTLINE_API_URL_2 = os.environ.get("OUTLINE_API_URL_2", "")
OUTLINE_API_URL_3 = os.environ.get("OUTLINE_API_URL_3", "")


def _load_admin_ids():
    raw = os.environ.get("ADMIN_CHAT_IDS", "")
    if raw:
        return [x.strip() for x in raw.split(",") if x.strip()]
    return []


ADMIN_CHAT_IDS = _load_admin_ids()

OCR_API_KEY = os.environ.get("OCR_API_KEY", "")
MY_PAYMENT_PHONES = [p.strip() for p in os.environ.get("MY_PAYMENT_PHONES", "").split(",") if p.strip()]


def outline_api_urls():
    """Configured Outline servers only (skip unconfigured slots)."""
    return [u.rstrip("/") for u in (OUTLINE_API_URL_1, OUTLINE_API_URL_2, OUTLINE_API_URL_3) if u]


def is_telegram_configured():
    return bool(os.environ.get("TELEGRAM_TOKEN") and ":" in TELEGRAM_TOKEN and "Dummy" not in TELEGRAM_TOKEN)

# 🌟 Plan Configuration
PLANS = {
    "starter": {"name": "Starter Plan", "data": "25 GB", "bytes": 25 * 1000**3, "price": 1000, "manual": False, "months": 1},
    "basic": {"name": "Basic Plan", "data": "50 GB", "bytes": 50 * 1000**3, "price": 2000, "manual": False, "months": 1},
    "standard": {"name": "Standard Plan", "data": "75 GB", "bytes": 75 * 1000**3, "price": 3000, "manual": False, "months": 1},
    "premium": {"name": "Premium Plan", "data": "100 GB", "bytes": 100 * 1000**3, "price": 4000, "manual": False, "months": 1},
    "vip": {"name": "VIP Plan", "data": "150 GB", "bytes": 150 * 1000**3, "price": 5000, "manual": False, "months": 1},
    "pro": {"name": "Pro Plan", "data": "200 GB", "bytes": 200 * 1000**3, "price": 7000, "manual": False, "months": 1},
    "ultimate": {"name": "Ultimate VIP Plan", "data": "500 GB", "bytes": 500 * 1000**3, "price": 10000, "manual": False, "months": 1},
    "custom_1m": {"name": "၁ လ စိတ်ကြိုက်သုံး (5 Device)", "data": "Unlimited Data", "bytes": 0, "price": 20000, "manual": True, "months": 1},
    "custom_3m": {"name": "၃ လ စိတ်ကြိုက်သုံး (5 Device)", "data": "Unlimited Data", "bytes": 0, "price": 60000, "manual": True, "months": 3},
}
