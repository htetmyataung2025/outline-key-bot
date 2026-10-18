"""Loyalty points: 4-hour claim + top-up rewards, redeemable for a Starter Plan.

Storage mirrors wallets/slips: Upstash KV first, ``/tmp`` JSON fallback. All
amounts are integers and all timestamps use ``myanmar_now()``. The pure helpers
(cooldown math, weighted RNG, cap, streak) are kept separate from the
storage-backed flows so they can be unit-tested offline.

See ``memory/05_POINTS_SYSTEM_PLAN.md`` for the locked economics.
"""

import json
import os
import random
from datetime import date, datetime, timedelta

from bot_app.config import points_settings
from bot_app.storage.kv import redis_delete, redis_get, redis_set, redis_set_nx
from bot_app.storage.paths import POINTS_FILE
from bot_app.timeutil import myanmar_now

_TS_FMT = "%Y-%m-%d %H:%M:%S"
_DAY_FMT = "%Y-%m-%d"
_LOCK_TTL_S = 10


def _default_record() -> dict:
    return {
        "points": 0,
        "last_claim_at": None,
        "streak_days": 0,
        "last_streak_day": None,
        "has_topped_up": False,
        "redeemed_count": 0,
        "lifetime_earned": 0,
        "lifetime_claims": 0,
        "reminder_sent": False,
        "week_earned": 0,
        "week_start": None,
    }


# ── Storage ─────────────────────────────────────────────────────────────────
def load_all_points() -> dict:
    data = redis_get("points_data")
    local_data = {}
    if os.path.exists(POINTS_FILE):
        try:
            with open(POINTS_FILE, "r") as f:
                local_data = json.load(f)
        except Exception:
            pass

    if data is not None and isinstance(data, dict):
        if local_data:
            merged = False
            for k, v in local_data.items():
                if k not in data or (v.get("points", 0) > data[k].get("points", 0)):
                    data[k] = {**data.get(k, {}), **v}
                    merged = True
            if merged:
                save_all_points(data)
        return data

    if local_data:
        save_all_points(local_data)
        return local_data

    return {}


def save_all_points(data: dict) -> None:
    redis_set("points_data", data)
    try:
        with open(POINTS_FILE, "w") as f:
            json.dump(data, f)
    except Exception:
        pass


def get_points(chat_id) -> dict:
    """Points record for ``chat_id`` with all keys present (safe defaults)."""
    rec = _default_record()
    stored = load_all_points().get(str(chat_id))
    if isinstance(stored, dict):
        rec.update(stored)
    return rec


def _audit(chat_id, action: str, details: dict) -> None:
    # Lazy import: slips.py imports billing/extensions and will import this
    # module in Phase 2 — a top-level import here would create a cycle.
    try:
        from bot_app.services.slips import record_audit_log

        record_audit_log(chat_id, action, "points", str(chat_id), details)
    except Exception:
        pass


# ── Pure helpers (offline-testable) ──────────────────────────────────────────
def topup_points_for(amount_ks) -> int:
    """Points granted for a wallet top-up: 1% of the amount, capped."""
    cfg = points_settings()
    rate = max(1, int(cfg["topup_rate"]))
    return min(int(cfg["topup_cap"]), int(amount_ks) // rate)


def claim_cooldown_remaining(rec: dict, now: datetime | None = None) -> int:
    """Seconds until the next claim is allowed (0 = ready now)."""
    now = now or myanmar_now()
    last = rec.get("last_claim_at")
    if not last:
        return 0
    try:
        last_dt = datetime.strptime(last, _TS_FMT)
    except (ValueError, TypeError):
        return 0
    cooldown_h = int(points_settings()["claim_cooldown_h"])
    remaining = cooldown_h * 3600 - (now - last_dt).total_seconds()
    return int(remaining) if remaining > 0 else 0


def format_cooldown_remaining(seconds: int) -> str:
    """Format remaining cooldown seconds as a friendly Burmese string."""
    seconds = max(0, int(seconds))
    h, m = seconds // 3600, (seconds % 3600) // 60
    if h > 0:
        return f"{h} နာရီ {m} မိနစ်"
    if m > 0:
        return f"{m} မိနစ်"
    return f"{seconds} စက္ကန့်"


def is_streak_reward_day(streak_days: int) -> bool:
    """True on every Nth consecutive claim-day (7, 14, 21…) — guaranteed band."""
    target = int(points_settings()["streak_target_days"])
    return streak_days > 0 and target > 0 and streak_days % target == 0


def effective_streak(rec: dict, now: datetime | None = None) -> int:
    """Live streak for display.

    Returns the stored streak while it is still alive — the last claim was
    today or yesterday — otherwise 0. A missed day breaks the streak, and the
    next claim restarts it at 1. The streak grows without limit (8, 9, 30, 45…)
    as long as the user claims at least once each calendar day.
    """
    now = now or myanmar_now()
    last_day = rec.get("last_streak_day")
    if not last_day:
        return 0
    try:
        last_date = datetime.strptime(last_day, _DAY_FMT).date()
    except (ValueError, TypeError):
        return 0
    if (now.date() - last_date).days <= 1:
        return int(rec.get("streak_days") or 0)
    return 0


def _next_streak(rec: dict, today: date) -> int:
    """Streak count after a claim made on ``today`` (Myanmar calendar day)."""
    current = int(rec.get("streak_days") or 0)
    last_day = rec.get("last_streak_day")
    if not last_day:
        return 1
    try:
        last_date = datetime.strptime(last_day, _DAY_FMT).date()
    except (ValueError, TypeError):
        return 1
    delta = (today - last_date).days
    if delta <= 0:                      # same day → unchanged
        return current if current > 0 else 1
    if delta == 1:                      # consecutive day → grow
        return current + 1
    return 1                            # gap → reset


def roll_claim_reward(streak_days: int, rng: random.Random | None = None) -> int:
    """Weighted random claim reward.

    On a streak-target day the reward is drawn from the guaranteed high band
    instead of the weighted table.
    """
    rng = rng or random
    cfg = points_settings()
    target = int(cfg["streak_target_days"])
    if streak_days > 0 and target > 0 and streak_days % target == 0:
        low, high = cfg["streak_reward"]
        return rng.randint(int(low), int(high))
    table = cfg["reward_table"]
    ranges = [(lo, hi) for lo, hi, _ in table]
    weights = [w for _, _, w in table]
    lo, hi = rng.choices(ranges, weights=weights, k=1)[0]
    return rng.randint(int(lo), int(hi))


def _apply_cap(current: int, amount: int) -> tuple[int, int, int]:
    """Add ``amount`` under the balance cap.

    Returns ``(new_balance, granted, discarded)``.
    """
    cap = int(points_settings()["balance_cap"])
    room = cap - int(current)
    if room <= 0:
        return int(current), 0, int(amount)
    granted = min(int(amount), room)
    return int(current) + granted, granted, int(amount) - granted


# ── Weekly leaderboard period (pure, offline-testable) ────────────────────────
_AUTO = object()


def _iso_monday(d: date) -> date:
    return d - timedelta(days=d.weekday())


def current_week_start(now: datetime | None = None, epoch: str | None = None) -> str:
    """Start date (``YYYY-MM-DD``) of the CURRENT 7-day leaderboard period.

    Without an ``epoch`` the period is the ISO week (auto-resets every Monday).
    With an ``epoch`` date set (e.g. by an admin ``/lb_reset``), 7-day blocks are
    counted from that date, re-anchoring the weekly cycle to the reset day. No
    cron is needed: the boundary advances purely from the calendar.
    """
    now = now or myanmar_now()
    d = now.date()
    base = None
    if epoch:
        try:
            base = datetime.strptime(epoch, _DAY_FMT).date()
        except (ValueError, TypeError):
            base = None
    if base is None:
        base = _iso_monday(d)
    if d < base:
        return base.strftime(_DAY_FMT)
    weeks = (d - base).days // 7
    return (base + timedelta(days=7 * weeks)).strftime(_DAY_FMT)


def _leaderboard_epoch() -> str | None:
    return points_settings().get("leaderboard_epoch") or None


def week_score(rec: dict, now: datetime | None = None, epoch=_AUTO) -> int:
    """Points ``rec`` earned in the current period (0 once it has reset — i.e.
    the stored counter belongs to an older period)."""
    if epoch is _AUTO:
        epoch = _leaderboard_epoch()
    if rec.get("week_start") == current_week_start(now, epoch):
        return int(rec.get("week_earned", 0) or 0)
    return 0


def _bump_week(rec: dict, granted: int, now: datetime | None = None) -> None:
    """Add a positive earning to the current-period counter, resetting it first
    when the stored counter belongs to an older period. Mutates ``rec``."""
    granted = int(granted)
    if granted <= 0:
        return
    cur = current_week_start(now, _leaderboard_epoch())
    if rec.get("week_start") != cur:
        rec["week_earned"] = granted
        rec["week_start"] = cur
    else:
        rec["week_earned"] = int(rec.get("week_earned", 0) or 0) + granted


# ── Storage-backed flows ──────────────────────────────────────────────────────
def credit_points(chat_id, amount, source: str = "topup") -> tuple[int, int, int]:
    """Add points under the cap. Returns ``(granted, discarded, new_balance)``.

    A ``source="topup"`` credit also flips ``has_topped_up`` (the redeem gate).
    """
    amount = int(amount)
    uid = str(chat_id)
    data = load_all_points()
    rec = _default_record()
    if isinstance(data.get(uid), dict):
        rec.update(data[uid])

    new_bal, granted, discarded = _apply_cap(rec["points"], amount)
    rec["points"] = new_bal
    rec["lifetime_earned"] = int(rec["lifetime_earned"]) + granted
    if source == "topup":
        rec["has_topped_up"] = True
    _bump_week(rec, granted)
    data[uid] = rec
    save_all_points(data)

    action = "POINTS_TOPUP" if source == "topup" else "POINTS_GRANT"
    _audit(uid, action, {"amount": amount, "granted": granted,
                         "discarded": discarded, "new_balance": new_bal, "source": source})
    return granted, discarded, new_bal


def try_claim(chat_id, now: datetime | None = None,
              rng: random.Random | None = None) -> dict:
    """Atomic 4-hour claim. On success grants a weighted reward and advances
    the streak. Guarded by a short per-user Upstash lock against double-taps.

    Returns a dict with ``ok`` plus, on success, ``awarded``/``granted``/
    ``discarded``/``new_balance``/``streak_days``/``is_streak_bonus``/
    ``next_in_s``; on failure ``error`` is ``"cooldown"`` or ``"claim_in_progress"``.
    """
    now = now or myanmar_now()
    uid = str(chat_id)
    lock_key = f"points_lock:{uid}"
    lock = redis_set_nx(lock_key, _LOCK_TTL_S)
    if lock is False:
        return {"ok": False, "error": "claim_in_progress"}
    try:
        data = load_all_points()
        rec = _default_record()
        if isinstance(data.get(uid), dict):
            rec.update(data[uid])

        remaining = claim_cooldown_remaining(rec, now)
        if remaining > 0:
            return {"ok": False, "error": "cooldown", "next_in_s": remaining,
                    "points": rec["points"], "streak_days": rec["streak_days"]}

        today = now.date()
        new_streak = _next_streak(rec, today)
        awarded = roll_claim_reward(new_streak, rng=rng)
        new_bal, granted, discarded = _apply_cap(rec["points"], awarded)

        rec["points"] = new_bal
        rec["lifetime_earned"] = int(rec["lifetime_earned"]) + granted
        rec["lifetime_claims"] = int(rec["lifetime_claims"]) + 1
        rec["last_claim_at"] = now.strftime(_TS_FMT)
        rec["streak_days"] = new_streak
        rec["last_streak_day"] = today.strftime(_DAY_FMT)
        # Re-arm the cooldown-ready reminder: a fresh claim starts a new
        # 4-hour window, so the next scan should be allowed to notify again.
        rec["reminder_sent"] = False
        _bump_week(rec, granted, now)
        data[uid] = rec
        save_all_points(data)

        is_bonus = is_streak_reward_day(new_streak)
        _audit(uid, "POINTS_CLAIM", {"awarded": awarded, "granted": granted,
                                     "discarded": discarded, "new_balance": new_bal,
                                     "streak_days": new_streak, "streak_bonus": is_bonus})
        return {"ok": True, "awarded": awarded, "granted": granted,
                "discarded": discarded, "new_balance": new_bal,
                "streak_days": new_streak, "is_streak_bonus": is_bonus,
                "next_in_s": int(points_settings()["claim_cooldown_h"]) * 3600}
    finally:
        if lock is True:
            redis_delete(lock_key)


def can_redeem(rec: dict, cost: int | None = None) -> tuple[bool, str | None]:
    """Redemption gate. Returns ``(ok, reason)`` where reason is one of
    ``needs_topup`` / ``insufficient_points``.

    Starter is the ONLY redemption product, but it is **repeatable**: any user
    who has topped up at least once may redeem it as often as their balance
    (≤ 20,000 cap) allows.
    """
    cost = int(points_settings()["starter_cost"]) if cost is None else cost
    if not rec.get("has_topped_up"):
        return False, "needs_topup"
    if int(rec.get("points", 0)) < cost:
        return False, "insufficient_points"
    return True, None


def redeem_starter(chat_id) -> dict:
    """Deduct the Starter cost for a (repeatable) redemption.

    Does NOT provision the VPN key — the handler does that after a successful
    deduction, and calls ``refund_starter`` if provisioning fails.
    """
    uid = str(chat_id)
    data = load_all_points()
    rec = _default_record()
    if isinstance(data.get(uid), dict):
        rec.update(data[uid])

    ok, reason = can_redeem(rec)
    if not ok:
        return {"ok": False, "error": reason, "points": rec["points"]}

    cost = int(points_settings()["starter_cost"])
    rec["points"] = int(rec["points"]) - cost
    rec["redeemed_count"] = int(rec.get("redeemed_count", 0)) + 1
    data[uid] = rec
    save_all_points(data)

    _audit(uid, "POINTS_REDEEM", {"cost": cost,
                                  "new_balance": rec["points"], "product": "starter",
                                  "redeemed_count": rec["redeemed_count"]})
    return {"ok": True, "new_balance": rec["points"], "product": "starter",
            "redeemed_count": rec["redeemed_count"]}


def refund_starter(chat_id) -> dict:
    """Re-credit a failed Starter redemption (points back, undo the count)."""
    uid = str(chat_id)
    data = load_all_points()
    rec = _default_record()
    if isinstance(data.get(uid), dict):
        rec.update(data[uid])

    new_bal, _granted, _discarded = _apply_cap(rec["points"], int(points_settings()["starter_cost"]))
    rec["points"] = new_bal
    rec["redeemed_count"] = max(0, int(rec.get("redeemed_count", 0)) - 1)
    data[uid] = rec
    save_all_points(data)

    _audit(uid, "POINTS_REDEEM_REFUND", {"amount": int(points_settings()["starter_cost"]),
                                         "new_balance": new_bal})
    return {"ok": True, "new_balance": new_bal}


def admin_adjust_points(chat_id, delta, admin_id="Admin", reason: str = "") -> dict:
    """Admin manual points adjustment.

    ``delta > 0`` grants (capped at 20,000, overflow discarded); ``delta < 0``
    deducts (floored at 0). Audited as ``POINTS_ADMIN_GRANT``/``POINTS_ADMIN_DEDUCT``
    with the acting admin as actor and the customer as target. Returns
    ``{ok, applied, discarded, new_balance}`` where ``applied`` is the signed
    change actually made to the balance.
    """
    uid = str(chat_id)
    delta = int(delta)
    data = load_all_points()
    rec = _default_record()
    if isinstance(data.get(uid), dict):
        rec.update(data[uid])

    current = int(rec["points"])
    discarded = 0
    if delta >= 0:
        new_bal, applied, discarded = _apply_cap(current, delta)
        rec["lifetime_earned"] = int(rec["lifetime_earned"]) + applied
        _bump_week(rec, applied)
    else:
        new_bal = max(0, current + delta)
        applied = new_bal - current   # negative or zero
    rec["points"] = new_bal
    data[uid] = rec
    save_all_points(data)

    action = "POINTS_ADMIN_GRANT" if delta >= 0 else "POINTS_ADMIN_DEDUCT"
    try:
        from bot_app.services.slips import record_audit_log

        record_audit_log(admin_id, action, "points", uid,
                         {"delta": delta, "applied": applied, "discarded": discarded,
                          "new_balance": new_bal, "reason": reason})
    except Exception:
        pass
    return {"ok": True, "applied": applied, "discarded": discarded, "new_balance": new_bal}
