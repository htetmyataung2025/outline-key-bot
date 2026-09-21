"""Central settings. Env vars win; hardcoded fallbacks keep the current
Vercel deployment working until secrets are rotated into env vars."""

import os

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:  # pragma: no cover - production always has python-dotenv
    pass

# Token & API Configuration (Env var ဦးစားပေး, မရှိရင် fallback)
TELEGRAM_TOKEN = os.environ.get("TELEGRAM_TOKEN", "8779558815:AAEaXF6rRqCVM-PFhbOlwgubSknk5xTiKvU")

# 📢 Force Join Channel Configuration
REQUIRED_CHANNEL = os.environ.get("REQUIRED_CHANNEL", "@hefeature")

# 🌐 API Server ၁၊ ၂ နှင့် ၃ လင့်ခ်များ
OUTLINE_API_URL_1 = os.environ.get("OUTLINE_API_URL_1", "https://64.120.94.164:49429/YkDBSn3KwUaICBvzDQtvxQ")
OUTLINE_API_URL_2 = os.environ.get("OUTLINE_API_URL_2", "https://104.207.92.135:8443/o8a5SK1XlVXdrgXUX5Z24Q")
OUTLINE_API_URL_3 = os.environ.get("OUTLINE_API_URL_3", "https://vip.h-e-feature.store:33300/E_LfjCh3-9u_jEFyQnZUfA")

# 🔑 Admin Telegram Chat IDs (comma-separated env ကိုလည်း လက်ခံတယ်)
def _load_admin_ids():
    raw = os.environ.get("ADMIN_CHAT_IDS")
    if raw:
        return [x.strip() for x in raw.split(",") if x.strip()]
    return ["8778394176", "6297145771"]

ADMIN_CHAT_IDS = _load_admin_ids()

# 🔍 OCR Space API Key Configuration
OCR_API_KEY = os.environ.get("OCR_API_KEY", "K87641025188957")
MY_PAYMENT_PHONES = [p.strip() for p in os.environ.get("MY_PAYMENT_PHONES", "09699970092,9699970092,699970092").split(",") if p.strip()]

if not TELEGRAM_TOKEN or ":" not in TELEGRAM_TOKEN:
    raise ValueError("TELEGRAM_TOKEN မမှန်ပါ။ .env / Environment Variable မှာ TELEGRAM_TOKEN ထည့်ပေးပါ။")

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
