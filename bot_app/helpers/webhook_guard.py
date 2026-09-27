"""Guard rails for local runs (avoid killing production delivery)."""

import os

WEBHOOK_SUFFIX = "/webhook"


def expected_webhook_url() -> str:
    """Production webhook URL ('' when not deployed / not configured).

    Reads the environment on every call (a Vercel env var added after import
    is honoured immediately). Precedence: WEBHOOK_URL override > the Vercel
    production domain. ``/webhook`` is always enforced — the webhook must
    never point at the site root, where static output rejects POST (405).
    """
    override = (os.environ.get("WEBHOOK_URL") or "").strip().rstrip("/")
    domain = (os.environ.get("VERCEL_PROJECT_PRODUCTION_URL") or "").strip().rstrip("/")
    base = (override or domain).split("://", 1)[-1]
    if not base:
        return ""
    if not base.endswith(WEBHOOK_SUFFIX):
        base += WEBHOOK_SUFFIX
    return f"https://{base}"


def ensure_webhook(bot, expected_url=None):
    """Self-heal production delivery: re-register the webhook if it drifted.

    The bot went deaf twice because the webhook pointed at the site root
    (static ``index.html`` rejects POST → 405, updates queue up). This
    compares the live registration against ``expected`` and resets it on
    mismatch.

    Returns ``{"checked", "url", "previous", "fixed", "error"}``.
    ``checked=False`` means no expected URL is configured (local dev) —
    the bot is never touched.
    """
    expected = (expected_url or expected_webhook_url()).strip()
    if not expected:
        return {"checked": False, "url": "", "previous": "", "fixed": False, "error": None}
    try:
        info = bot.get_webhook_info()
        previous = (getattr(info, "url", "") or "").strip()
        if previous.rstrip("/") == expected.rstrip("/"):
            return {"checked": True, "url": expected, "previous": previous,
                    "fixed": False, "error": None}
        bot.set_webhook(url=expected)
        return {"checked": True, "url": expected, "previous": previous,
                "fixed": True, "error": None}
    except Exception as exc:  # delivery health must never crash the cron
        return {"checked": True, "url": expected, "previous": "", "fixed": False,
                "error": str(exc)}


def active_webhook_url(bot) -> str:
    """Return the currently registered webhook URL ('' when none). Best effort."""
    try:
        info = bot.get_webhook_info()
    except Exception as e:  # network / token problem: don't block the user
        print("webhook info check failed:", e)
        return ""
    return (getattr(info, "url", "") or "").strip()


def polling_conflict(bot, allow_remove: bool = False):
    """Polling needs the webhook removed; that kills production delivery.

    Returns ``(allowed, active_url)``:
    - no active webhook            -> (True, "")
    - active but ``allow_remove``  -> (True, url)
    - active and not allowed       -> (False, url)  # refuse & explain
    """
    url = active_webhook_url(bot)
    if not url:
        return True, ""
    return (True, url) if allow_remove else (False, url)
