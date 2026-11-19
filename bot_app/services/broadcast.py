"""Reliable admin broadcast engine.

The old broadcast sent to every user inside a single webhook request:
a sequential, unpaced loop with every error swallowed. Vercel kills the
function at 60 s (see ``vercel.json`` ``maxDuration``), so once the user
list grew, most customers silently never received the message and the
admin never saw the completion report.

This service turns a broadcast into a resumable Redis job instead:

- ``start_broadcast`` snapshots the recipient list once (all registered
  users minus admins) and stores the job under ``broadcast_job``.
- ``advance_broadcast`` sends the next chunk — bounded by both a send
  cap and a time budget, lightly paced, with Telegram 429
  (``retry_after``) honoured and blocked/deactivated chats counted
  separately — then persists the cursor. Whoever calls it (the admin's
  webhook request, the "continue" button, or the ~15-minute
  ``/reminder-check`` pinger) simply moves the job forward; when the
  cursor reaches the end, the admin gets the final summary once.
- Every processed recipient also gets the announcement pushed into
  their H&E VPN app inbox (``services/app_notify``), so app users see
  it as an in-app notification + phone popup even if they blocked the
  bot or rarely open Telegram.
"""

import html as _html
import re
import time
import uuid

from telebot.types import InlineKeyboardButton, InlineKeyboardMarkup

from bot_app.config import ADMIN_CHAT_IDS
from bot_app.services.app_notify import push_app_notification
from bot_app.services.orders import load_all_users
from bot_app.storage.kv import redis_get, redis_set

_JOB_KEY = "broadcast_job"
_CHUNK_CAP = 120  # sends per advance — mirrors points_reminder's cap
_BUDGET_S = 40.0  # stay well under Vercel's 60 s function wall
_PACE_S = 0.05  # light pacing between sends
_APP_TITLE = "📢 H&E VPN"
_PHOTO_FALLBACK = "📷 ပုံနှင့်အတူ ကြေညာချက်အသစ် ရောက်ပါတယ် — အသေးစိတ်ကို Bot တွင် ကြည့်ပါ။"


def _sleep(seconds: float) -> None:
    """Indirection so tests can patch out real waiting."""
    time.sleep(seconds)


# ── job storage ──────────────────────────────────────────────────────────────

def _load_job():
    try:
        job = redis_get(_JOB_KEY)
    except Exception:
        return None
    return job if isinstance(job, dict) else None


def _save_job(job) -> None:
    try:
        redis_set(_JOB_KEY, job)
    except Exception:
        pass


def get_active_job():
    """The currently running broadcast job, or None."""
    job = _load_job()
    if job and job.get("status") == "running":
        return job
    return None


def remaining(job) -> int:
    return max(0, len(job.get("recipients", [])) - int(job.get("cursor", 0)))


# ── lifecycle ────────────────────────────────────────────────────────────────

def _app_body(kind: str, text: str) -> str:
    """Plain-text version of the announcement for the app inbox."""
    plain = _html.unescape(re.sub(r"<[^>]+>", "", text or "")).strip()
    if plain:
        return plain
    return _PHOTO_FALLBACK if kind == "photo" else ""


def start_broadcast(admin_id, kind: str, text: str, photo_id=None):
    """Create a job unless one is already running.

    Returns ``(job, created)`` — when a broadcast is already in flight,
    the existing job is returned with ``created=False`` so the caller
    can show its progress instead of starting a competing send.
    """
    existing = get_active_job()
    if existing:
        return existing, False

    admins = {str(a) for a in ADMIN_CHAT_IDS}
    seen = set()
    recipients = []
    for uid in load_all_users() or []:
        s = str(uid)
        if s in admins or s in seen:
            continue
        seen.add(s)
        recipients.append(s)

    job = {
        "id": uuid.uuid4().hex[:12],
        "kind": kind,
        "text": text or "",
        "photo_id": photo_id,
        "app_body": _app_body(kind, text or ""),
        "recipients": recipients,
        "cursor": 0,
        "sent": 0,
        "failed": 0,
        "blocked": 0,
        "app_sent": 0,
        "admin_id": str(admin_id),
        "status": "running",
        "summary_sent": False,
        "created_at": int(time.time()),
    }
    _save_job(job)
    return job, True


def _classify_error(exc) -> tuple:
    """Map a Telegram send error to (kind, retry_after_s).

    kind is "flood" (429 — worth one retry after a wait), "blocked"
    (user blocked the bot / deactivated / chat gone — never retry), or
    "failed" (anything else).
    """
    code = getattr(exc, "error_code", None)
    desc = str(exc).lower()
    if code == 429 or "too many requests" in desc:
        retry_after = 2.0
        result = getattr(exc, "result_json", None) or {}
        try:
            retry_after = float(result.get("parameters", {}).get("retry_after", retry_after))
        except Exception:
            pass
        return "flood", min(retry_after, 10.0)
    if code == 403 or "blocked" in desc or "deactivated" in desc or "chat not found" in desc:
        return "blocked", 0.0
    return "failed", 0.0


def _deliver(bot, job, uid) -> None:
    """Send one recipient: app inbox first, then Telegram."""
    # App inbox first: the announcement lands in the VPN app even when
    # the Telegram send below fails (bot blocked, account deactivated).
    push_app_notification(uid, "broadcast", _APP_TITLE, job.get("app_body") or _PHOTO_FALLBACK)
    job["app_sent"] = job.get("app_sent", 0) + 1

    for attempt in range(2):
        try:
            if job["kind"] == "photo":
                bot.send_photo(uid, job["photo_id"], caption=job["text"], parse_mode="HTML")
            else:
                bot.send_message(uid, job["text"], parse_mode="HTML")
            job["sent"] = job.get("sent", 0) + 1
            return
        except Exception as exc:
            kind, wait = _classify_error(exc)
            if kind == "flood" and attempt == 0:
                _sleep(wait)
                continue
            if kind == "blocked":
                job["blocked"] = job.get("blocked", 0) + 1
            else:
                job["failed"] = job.get("failed", 0) + 1
            return


def advance_broadcast(bot, job=None, budget_s: float = _BUDGET_S, cap: int = _CHUNK_CAP):
    """Send the next chunk of the active job. Returns the job (or None).

    ``job`` may be passed by the caller that just created it (the common
    handler path); otherwise the stored job is loaded. Safe to call
    from anywhere: a no-op when no broadcast is running. On completion
    the admin summary + audit log are emitted once.
    """
    if job is None:
        job = get_active_job()
    if not job or job.get("status") != "running":
        return job

    recipients = job.get("recipients", [])
    deadline = time.monotonic() + budget_s
    processed = 0
    while (
        job["cursor"] < len(recipients)
        and processed < cap
        and time.monotonic() < deadline
    ):
        uid = recipients[job["cursor"]]
        _deliver(bot, job, uid)
        job["cursor"] += 1
        processed += 1
        if processed % 10 == 0:
            _save_job(job)
        if _PACE_S:
            _sleep(_PACE_S)

    if job["cursor"] >= len(recipients):
        job["status"] = "done"
        job["finished_at"] = int(time.time())
    _save_job(job)
    if job["status"] == "done":
        _finalize(bot, job)
    return job


def _finalize(bot, job) -> None:
    """Send the admin the completion summary + write the audit log (once)."""
    if job.get("summary_sent"):
        return
    job["summary_sent"] = True
    _save_job(job)
    total = len(job.get("recipients", []))
    try:
        bot.send_message(
            job["admin_id"],
            (
                "✅ <b>Broadcast ပို့ပြီးပါပြီ!</b>\n\n"
                f"📨 Telegram ရောက်ရှိသူ: <b>{job.get('sent', 0)} / {total}</b>\n"
                f"📱 App Noti ထည့်ပေးသူ: <b>{job.get('app_sent', 0)}</b>\n"
                f"🚫 Bot ပိတ်ထား/အကောင့်မရှိတော့သူ: <b>{job.get('blocked', 0)}</b>\n"
                f"❌ မအောင်မြင်သူ: <b>{job.get('failed', 0)}</b>"
            ),
            parse_mode="HTML",
        )
    except Exception:
        pass
    try:
        from bot_app.services.slips import record_audit_log

        record_audit_log(
            job["admin_id"],
            "BROADCAST",
            "broadcast",
            str(total),
            {
                "message_type": job.get("kind"),
                "sent": job.get("sent", 0),
                "recipients": total,
                "app_sent": job.get("app_sent", 0),
                "blocked": job.get("blocked", 0),
                "failed": job.get("failed", 0),
            },
        )
    except Exception:
        pass


# ── admin-facing progress ────────────────────────────────────────────────────

def progress_text(job) -> str:
    total = len(job.get("recipients", []))
    return (
        "📢 <b>Broadcast ပို့နေဆဲ…</b>\n\n"
        f"ပို့ပြီး: <b>{job.get('cursor', 0)} / {total}</b> (Telegram ရောက် {job.get('sent', 0)})\n"
        f"ကျန်: <b>{remaining(job)}</b> ယောက်\n\n"
        "⏳ ကျန်တာကို မိနစ်ပိုင်းအတွင်း အလိုအလျောက် ဆက်ပို့ပေးပါမယ် — "
        "မြန်ချင်ရင် အောက်က ခလုတ်ကို နှိပ်ပါ။"
    )


def continue_markup(job):
    markup = InlineKeyboardMarkup()
    markup.row(
        InlineKeyboardButton(
            f"▶️ ဆက်ပို့ရန် (ကျန် {remaining(job)} ယောက်)",
            callback_data="broadcast_continue",
        )
    )
    return markup


def send_progress(bot, job, chat_id=None) -> None:
    """Post a progress message + continue button (no-op when done)."""
    if not job or job.get("status") == "done":
        return
    try:
        bot.send_message(
            chat_id or job["admin_id"],
            progress_text(job),
            parse_mode="HTML",
            reply_markup=continue_markup(job),
        )
    except Exception:
        pass
