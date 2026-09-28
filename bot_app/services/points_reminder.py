"""Cooldown-ready reminder scan.

Sends a one-off Telegram nudge to each user whose 4-hour claim cooldown has
just elapsed, so they come back and claim (engagement). Triggered by an
EXTERNAL free pinger (e.g. cron-job.org) hitting the secret-guarded
``/reminder-check`` endpoint every ~15 minutes — Vercel Hobby crons are capped
at once per day, so they cannot drive a 4-hour cycle themselves.

Dedup is per cooldown cycle via the ``reminder_sent`` flag on each points
record: set here after a successful send, and reset to ``False`` by
``try_claim`` when the next claim opens a fresh window. A user who never
returns therefore receives at most one reminder per claim.
"""

from datetime import datetime

from bot_app.config import points_enabled, points_settings
from bot_app.extensions import bot
from bot_app.services.points import (
    claim_cooldown_remaining,
    effective_streak,
    load_all_points,
    save_all_points,
)
from bot_app.timeutil import myanmar_now

# Cap sends per run so one invocation stays well under the 60s function wall
# and Telegram's ~30 msg/s ceiling; any remainder is picked up next pass.
_SEND_CAP = 100


def _reminder_text(rec: dict, now: datetime) -> str:
    bal = int(rec.get("points", 0) or 0)
    streak = effective_streak(rec, now)
    return (
        "🎁 <b>Daily Reward အသင့်ဖြစ်ပါပြီ!</b>\n\n"
        f"လက်ကျန် Points: <b>{bal:,}</b>\n"
        f"လက်ရှိ Streak: <b>{streak}</b> ရက်\n\n"
        "အခုပဲ Claim လုပ်ပြီး Points ဆက်စုလိုက်ပါ 👉 /start"
    )


def _is_ready(rec: dict, now: datetime) -> bool:
    """A record is due a reminder when it has claimed before, has not already
    been reminded this cycle, and its cooldown has fully elapsed."""
    if not isinstance(rec, dict):
        return False
    if not rec.get("last_claim_at"):
        return False
    if rec.get("reminder_sent"):
        return False
    return claim_cooldown_remaining(rec, now) <= 0


def run_cooldown_reminders(now: datetime | None = None) -> dict:
    """Scan all points records; DM users whose cooldown just became ready.

    Returns ``{"reminded": int, "scanned": int, "disabled": bool}``. Honours
    the master switch and the ``cooldown_reminder`` setting (both OFF → no-op).
    """
    if not points_enabled() or not points_settings().get("cooldown_reminder", True):
        return {"reminded": 0, "scanned": 0, "disabled": True}

    now = now or myanmar_now()
    data = load_all_points()
    reminded_uids = []

    for uid, rec in data.items():
        if not _is_ready(rec, now):
            continue
        try:
            bot.send_message(uid, _reminder_text(rec, now), parse_mode="HTML")
        except Exception:
            # A blocked/deleted chat must not abort the whole sweep; leave the
            # flag unset so a future run can retry.
            continue
        reminded_uids.append(uid)
        if len(reminded_uids) >= _SEND_CAP:
            break

    # Persist the ``reminder_sent`` flags against a FRESH read so a claim that
    # landed mid-sweep (which reset the flag and re-opened the cooldown) is not
    # clobbered and not wrongly marked as reminded.
    if reminded_uids:
        fresh = load_all_points()
        changed = False
        for uid in reminded_uids:
            r = fresh.get(uid)
            if _is_ready(r, now):
                r["reminder_sent"] = True
                changed = True
        if changed:
            save_all_points(fresh)

    return {"reminded": len(reminded_uids), "scanned": len(data), "disabled": False}
