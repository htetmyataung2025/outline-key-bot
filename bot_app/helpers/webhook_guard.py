"""Guard rails for local runs (avoid killing production delivery)."""


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
