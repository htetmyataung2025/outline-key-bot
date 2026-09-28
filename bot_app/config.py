"""Central settings. Env-first; safe dummy defaults for import/tests.

Production must set real secrets via environment (.env / Vercel env vars).
Hardcoded production secrets were removed on purpose (they leaked in git
history). Missing values degrade gracefully: bot features that need them
return friendly errors instead of crashing at import time.
"""

import os
from collections.abc import Sequence

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:  # pragma: no cover - production always has python-dotenv
    pass

# Dummy token keeps `import bot_app.*` working in CI without secrets.
# Real deployments MUST set TELEGRAM_TOKEN env var.
TELEGRAM_TOKEN = os.environ.get("TELEGRAM_TOKEN", "0000000000:AAADummyTokenForTestsOnly00000000000")

# Force-join channel. An explicitly empty value (``REQUIRED_CHANNEL=`` in .env)
# disables the membership check entirely — intended for local/dev bots.
# Unset keeps the production default.
REQUIRED_CHANNEL = os.environ.get("REQUIRED_CHANNEL", "@hefeature").strip() or None

# Telegram Mini App entry points. Admins open the Control Center directly
# from the menu button and sign in with their Admin ID + password; everyone
# else keeps the public landing page.
DASHBOARD_URL = os.environ.get("DASHBOARD_URL", "https://outline-key-bot.vercel.app").rstrip("/")
LANDING_URL = os.environ.get("LANDING_URL", "https://h-e.feature.hma.qzz.io").rstrip("/")

OUTLINE_API_URL_1 = os.environ.get("OUTLINE_API_URL_1", "")
OUTLINE_API_URL_2 = os.environ.get("OUTLINE_API_URL_2", "")
OUTLINE_API_URL_3 = os.environ.get("OUTLINE_API_URL_3", "")


# --- Admin access -----------------------------------------------------------
# Real-world env values arrive messy: "123, 456", '["123"]', "id:123;456",
# newlines, spaces... Parsing is therefore forgiving, and the list is *re-read
# from the environment on every access* so a value added after import (local
# .env edit, monkeypatched test, freshly deployed Vercel env var) is always
# honoured instead of a stale import-time snapshot.
_ADMIN_ENV_NAMES = (
    "ADMIN_CHAT_IDS", "ADMIN_IDS", "ADMINS",
    "ADMIN_CHAT_ID", "ADMIN_USER_IDS", "ADMIN_ID",
)

# Labels tolerated in front of an id (``id:123``, ``admin=123``,
# ``ADMIN_CHAT_IDS=123``). Anything else before ``:``/``=`` means the token is
# not an id (e.g. a ``host:port`` paste) and is dropped.
_ADMIN_ID_LABELS = {
    "id", "ids", "admin", "admins", "admin_id", "admin_ids",
    "chat", "chats", "chatid", "chat_id", "user", "users",
    "userid", "user_id", "telegram", "tg",
} | {name.lower() for name in _ADMIN_ENV_NAMES}


def _parse_admin_ids(raw):
    """Normalise a raw env value into a deduped list of digit-only ids.

    Tolerates quotes, brackets/braces, JSON-ish lists, semicolons, pipes,
    newlines, ``key=value`` / ``id:123`` labels, ``@``/``+``/``_`` padding and
    full ``ADMIN_CHAT_IDS=...`` assignments. A token must end up as *pure
    digits* of plausible Telegram length (5-15), so a stray URL, hostname or
    port can never become an accidental admin.
    """
    if not raw:
        return []
    text = raw
    for chunk in "[]{}\"'`,;|\t\n\r":
        text = text.replace(chunk, " ")
    ids = []
    for token in text.split():
        candidate = token.strip("+-@_")
        cut = max(candidate.rfind(":"), candidate.rfind("="))
        if cut >= 0:
            label = candidate[:cut].strip("+-@_").lower()
            if label not in _ADMIN_ID_LABELS:
                continue
            candidate = candidate[cut + 1:].strip("+-@_")
        if candidate.isdigit() and 5 <= len(candidate) <= 15 and candidate not in ids:
            ids.append(candidate)
    return ids


def _load_admin_ids():
    """Union of every accepted admin env var (misspelled name still works)."""
    ids = []
    for name in _ADMIN_ENV_NAMES:
        for value in _parse_admin_ids(os.environ.get(name, "")):
            if value not in ids:
                ids.append(value)
    return ids


def admin_chat_ids():
    """Fresh, normalised admin chat id list (call-time read)."""
    return _load_admin_ids()


def admin_env_sources():
    """Env var names that actually contributed admin ids (for diagnostics)."""
    return [n for n in _ADMIN_ENV_NAMES if _parse_admin_ids(os.environ.get(n, ""))]


def admin_ids_masked():
    """Secret-safe admin id rendering for logs/UI (last 4 digits only)."""
    ids = _load_admin_ids()
    return ", ".join(f"…{i[-4:]}" for i in ids) if ids else "(none)"


def is_admin(chat_id) -> bool:
    """True when ``chat_id`` is a configured admin (int or str accepted)."""
    if chat_id is None:
        return False
    return str(chat_id).strip("+-@_").strip() in _load_admin_ids()


class _AdminIdList(Sequence):
    """Live list-like view over the admin env vars.

    Every call site in the codebase treats ``ADMIN_CHAT_IDS`` like a plain
    list (``[str(aid) for aid in ADMIN_CHAT_IDS]``, ``for aid in
    ADMIN_CHAT_IDS``, ``len(...)``, ``[0]``) — this object keeps all of them
    working while always reflecting the *current* environment.
    """

    def _ids(self):
        return _load_admin_ids()

    def __iter__(self):
        return iter(self._ids())

    def __len__(self):
        return len(self._ids())

    def __getitem__(self, index):
        return self._ids()[index]

    def __contains__(self, item):
        return is_admin(item)

    def __eq__(self, other):
        if isinstance(other, (list, tuple, set)):
            return self._ids() == [str(x) for x in other]
        return NotImplemented

    def __repr__(self):
        return f"AdminIdList({self._ids()!r})"


ADMIN_CHAT_IDS = _AdminIdList()


OCR_API_KEY = os.environ.get("OCR_API_KEY", "")


def env_payment_phones():
    """Payment phones parsed straight from the env baseline (no settings read).

    Safe to call from anywhere — unlike ``MY_PAYMENT_PHONES`` it never re-enters
    ``get_system_settings()``, so it can be used while defaults are being built.
    """
    return [p.strip() for p in os.environ.get("MY_PAYMENT_PHONES", "").split(",") if p.strip()]


class _DynamicPaymentPhones(Sequence):
    """Dynamic view of payment phones from Supabase settings with env fallback."""

    def _phones(self):
        try:
            from bot_app.services.settings import get_system_settings
            phones = get_system_settings().get("payment_phones", [])
            if phones and isinstance(phones, list):
                return [str(p).strip() for p in phones if str(p).strip()]
        except Exception:
            pass
        return env_payment_phones()

    def __iter__(self):
        return iter(self._phones())

    def __len__(self):
        return len(self._phones())

    def __getitem__(self, index):
        return self._phones()[index]

    def __contains__(self, item):
        return str(item).strip() in self._phones()

    def __repr__(self):
        return repr(self._phones())


MY_PAYMENT_PHONES = _DynamicPaymentPhones()


def outline_api_urls():
    """Configured Outline servers (dynamic settings prioritized, fallback to env slots)."""
    try:
        from bot_app.services.settings import get_system_settings
        settings = get_system_settings()
        servers = settings.get("servers", [])
        urls = [s.get("api_url", "").rstrip("/") for s in servers if s.get("api_url")]
        if urls:
            return urls
    except Exception:
        pass
    return [u.rstrip("/") for u in (OUTLINE_API_URL_1, OUTLINE_API_URL_2, OUTLINE_API_URL_3) if u]


def is_telegram_configured():
    return bool(os.environ.get("TELEGRAM_TOKEN") and ":" in TELEGRAM_TOKEN and "Dummy" not in TELEGRAM_TOKEN)


# --- Startup diagnostic -----------------------------------------------------
# One secret-safe line in the runtime logs (Vercel → Logs) telling the owner
# exactly what the running build parsed.
if is_telegram_configured():
    print(
        "[config] admins={n} ids={ids} env={env} outline_servers={srv} kv={kv}".format(
            n=len(admin_chat_ids()),
            ids=admin_ids_masked(),
            env=",".join(admin_env_sources()) or "none",
            srv=len(outline_api_urls()),
            kv="on" if os.environ.get("KV_REST_API_URL") else "off",
        )
    )


# 🌟 Default Plan Configuration (Baseline fallback)
_DEFAULT_PLANS = {
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


class _DynamicPlans(dict):
    """Dynamic dictionary view of VPN plans from Supabase settings."""

    def _data(self) -> dict:
        try:
            from bot_app.services.settings import get_system_settings
            dyn = get_system_settings().get("plans")
            if dyn and isinstance(dyn, dict):
                return dyn
        except Exception:
            pass
        return _DEFAULT_PLANS

    def get(self, key, default=None):
        return self._data().get(key, default)

    def items(self):
        return self._data().items()

    def keys(self):
        return self._data().keys()

    def values(self):
        return self._data().values()

    def __getitem__(self, key):
        return self._data()[key]

    def __contains__(self, key):
        return key in self._data()

    def __len__(self):
        return len(self._data())

    def __iter__(self):
        return iter(self._data())

    def __repr__(self):
        return repr(self._data())


PLANS = _DynamicPlans()


def default_plans() -> dict:
    """Baseline plans straight from the constants (no settings read).

    Same re-entrancy rationale as ``env_payment_phones``: use this when
    building settings defaults, never ``PLANS`` itself.
    """
    return dict(_DEFAULT_PLANS)


# 🎁 Loyalty Points / Daily Reward System (see memory/05_POINTS_SYSTEM_PLAN.md)
# Economics are LOCKED; reward-table weights are tunable after live observation.
POINTS_BALANCE_CAP = 20000          # hard cap; earnings above this are discarded
POINTS_CLAIM_COOLDOWN_H = 4         # rolling cooldown between claims (~6/day max)
POINTS_TOPUP_RATE = 100             # 1 point per this many Ks topped up
POINTS_TOPUP_CAP = 1000             # max points from a single top-up (at 100k Ks)
POINTS_STARTER_COST = 5000          # points to redeem one Starter Plan
POINTS_STREAK_TARGET_DAYS = 7       # every Nth consecutive claim-day = guaranteed band
POINTS_STREAK_REWARD = (150, 200)   # guaranteed reward range on a streak-target day
POINTS_ON_ADMIN_TOPUP = False       # LOCKED: manual admin credits grant no points

# Claim reward distribution: (low, high, weight). Weighted low so 100+ is rare.
POINTS_REWARD_TABLE = [
    (10, 19, 35),
    (20, 30, 35),
    (31, 50, 18),
    (51, 99, 8),
    (100, 150, 3),
    (151, 200, 1),
]


def default_points_settings() -> dict:
    """Baseline Points economy as a plain JSON-friendly dict.

    This is the seed written into the dynamic settings store; every field is
    also the ultimate hardcoded fallback used by ``points_settings()`` when a
    key is missing or unreadable.
    """
    return {
        "enabled": True,
        "claim_cooldown_h": POINTS_CLAIM_COOLDOWN_H,
        "balance_cap": POINTS_BALANCE_CAP,
        "topup_rate": POINTS_TOPUP_RATE,
        "topup_cap": POINTS_TOPUP_CAP,
        "starter_cost": POINTS_STARTER_COST,
        "streak_target_days": POINTS_STREAK_TARGET_DAYS,
        "streak_reward": [POINTS_STREAK_REWARD[0], POINTS_STREAK_REWARD[1]],
        "on_admin_topup": POINTS_ON_ADMIN_TOPUP,
        "cooldown_reminder": True,
        "leaderboard_epoch": None,
        "reward_table": [[lo, hi, w] for lo, hi, w in POINTS_REWARD_TABLE],
    }


def points_settings() -> dict:
    """Call-time Points economy config: dynamic settings → env/const fallback.

    Read fresh on every call (never at import time) so the owner's dashboard
    edits apply without a redeploy — same pattern as ``PLANS`` /
    ``MY_PAYMENT_PHONES``. Each field independently falls back to the hardcoded
    ``POINTS_*`` constant if the stored value is missing or malformed, so a
    partial/legacy ``points`` dict can never break the economy.
    """
    dyn = {}
    try:
        from bot_app.services.settings import get_system_settings
        stored = get_system_settings().get("points")
        if isinstance(stored, dict):
            dyn = stored
    except Exception:
        pass

    def _int(key, fallback, minimum=None):
        try:
            val = int(dyn[key])
        except (KeyError, TypeError, ValueError):
            return fallback
        if minimum is not None and val < minimum:
            return fallback
        return val

    def _band(fallback):
        v = dyn.get("streak_reward")
        if isinstance(v, (list, tuple)) and len(v) == 2:
            try:
                lo, hi = int(v[0]), int(v[1])
                if 1 <= lo <= hi:
                    return (lo, hi)
            except (TypeError, ValueError):
                pass
        return tuple(fallback)

    def _table(fallback):
        v = dyn.get("reward_table")
        if isinstance(v, list) and v:
            rows = []
            try:
                for row in v:
                    lo, hi, w = row
                    lo, hi, w = int(lo), int(hi), int(w)
                    if not (1 <= lo <= hi and w > 0):
                        raise ValueError
                    rows.append((lo, hi, w))
                return rows
            except (TypeError, ValueError):
                pass
        return [tuple(r) for r in fallback]

    return {
        "enabled": bool(dyn.get("enabled", True)),
        "claim_cooldown_h": _int("claim_cooldown_h", POINTS_CLAIM_COOLDOWN_H, minimum=1),
        "balance_cap": _int("balance_cap", POINTS_BALANCE_CAP, minimum=1),
        "topup_rate": _int("topup_rate", POINTS_TOPUP_RATE, minimum=1),
        "topup_cap": _int("topup_cap", POINTS_TOPUP_CAP, minimum=0),
        "starter_cost": _int("starter_cost", POINTS_STARTER_COST, minimum=1),
        "streak_target_days": _int("streak_target_days", POINTS_STREAK_TARGET_DAYS, minimum=1),
        "streak_reward": _band(POINTS_STREAK_REWARD),
        "on_admin_topup": bool(dyn.get("on_admin_topup", POINTS_ON_ADMIN_TOPUP)),
        "cooldown_reminder": bool(dyn.get("cooldown_reminder", True)),
        "leaderboard_epoch": (dyn.get("leaderboard_epoch").strip()
                              if isinstance(dyn.get("leaderboard_epoch"), str)
                              and dyn.get("leaderboard_epoch").strip() else None),
        "reward_table": _table(POINTS_REWARD_TABLE),
    }


def points_enabled() -> bool:
    """Master switch for the whole Points system (call-time read)."""
    return points_settings()["enabled"]


def reminder_cron_secret() -> str:
    """Shared secret guarding the external cooldown-reminder pinger endpoint.

    Read at call time (never import) so a value added on Vercel/`.env` after
    import — or monkeypatched in tests — is always honoured. Empty string means
    the reminder endpoint is disabled (no external trigger is authorised).
    """
    return os.environ.get("REMINDER_CRON_SECRET", "").strip()


