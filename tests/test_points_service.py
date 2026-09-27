"""Loyalty points service: cooldown, weighted RNG, cap, streak, redeem gate.

All file-backed and network-free (Upstash disabled in conftest → the claim
lock degrades to best-effort, which is exactly what a single-process test wants).
"""

import random
from datetime import datetime, timedelta

from bot_app.config import (
    POINTS_BALANCE_CAP,
    POINTS_STARTER_COST,
    POINTS_STREAK_REWARD,
    POINTS_STREAK_TARGET_DAYS,
)
from bot_app.services import points as P

UID = 555000777
P_STARTER = POINTS_STARTER_COST


def _day(s):
    return datetime.strptime(s, "%Y-%m-%d").date()


# ── topup_points_for formula ─────────────────────────────────────────────────
def test_topup_points_formula():
    assert P.topup_points_for(1000) == 10
    assert P.topup_points_for(5000) == 50
    assert P.topup_points_for(10000) == 100
    assert P.topup_points_for(20000) == 200
    assert P.topup_points_for(50000) == 500
    assert P.topup_points_for(100000) == 1000
    assert P.topup_points_for(500000) == 1000   # capped at 1,000
    assert P.topup_points_for(2000) == 20
    assert P.topup_points_for(3000) == 30
    assert P.topup_points_for(50) == 0          # below 1 point


# ── cooldown ──────────────────────────────────────────────────────────────────
def test_cooldown_fresh_record_is_ready():
    assert P.claim_cooldown_remaining(P._default_record()) == 0


def test_cooldown_blocks_then_clears():
    now = datetime(2026, 9, 27, 12, 0, 0)
    rec = {**P._default_record(), "last_claim_at": now.strftime(P._TS_FMT)}
    assert P.claim_cooldown_remaining(rec, now + timedelta(hours=1)) > 0   # ~3h left
    assert P.claim_cooldown_remaining(rec, now + timedelta(hours=4)) == 0  # ready


# ── weighted reward bounds ────────────────────────────────────────────────────
def test_roll_reward_within_bounds():
    rng = random.Random(1234)
    for _ in range(2000):
        assert 10 <= P.roll_claim_reward(1, rng=rng) <= 200


def test_streak_day_reward_is_high_band():
    rng = random.Random(7)
    low, high = POINTS_STREAK_REWARD
    for _ in range(500):
        assert low <= P.roll_claim_reward(POINTS_STREAK_TARGET_DAYS, rng=rng) <= high


# ── streak transitions ────────────────────────────────────────────────────────
def test_streak_transitions():
    assert P._next_streak(P._default_record(), _day("2026-09-27")) == 1
    base = {**P._default_record(), "streak_days": 3, "last_streak_day": "2026-09-27"}
    assert P._next_streak(base, _day("2026-09-27")) == 3   # same day → unchanged
    assert P._next_streak(base, _day("2026-09-28")) == 4   # consecutive → +1
    assert P._next_streak(base, _day("2026-09-30")) == 1   # gap → reset


def test_is_streak_reward_day():
    assert not P.is_streak_reward_day(0)
    assert not P.is_streak_reward_day(6)
    assert P.is_streak_reward_day(7)
    assert P.is_streak_reward_day(14)


def test_effective_streak_alive_and_broken():
    now = datetime(2026, 9, 27, 12, 0, 0)
    # claimed today → full streak shown
    rec = {**P._default_record(), "streak_days": 9, "last_streak_day": "2026-09-27"}
    assert P.effective_streak(rec, now) == 9
    # claimed yesterday → still alive
    rec_y = {**P._default_record(), "streak_days": 9, "last_streak_day": "2026-09-26"}
    assert P.effective_streak(rec_y, now) == 9
    # missed a day (older than yesterday) → broken → 0
    rec_b = {**P._default_record(), "streak_days": 9, "last_streak_day": "2026-09-25"}
    assert P.effective_streak(rec_b, now) == 0
    # never claimed → 0
    assert P.effective_streak(P._default_record(), now) == 0


def test_streak_grows_without_limit_and_resets_on_gap():
    d = _day
    # daily claims keep growing past the 7-day target (8, 9, 10…)
    rec = {**P._default_record(), "streak_days": 9, "last_streak_day": "2026-09-27"}
    assert P._next_streak(rec, d("2026-09-28")) == 10
    # a skipped day resets to 1 on the next claim
    assert P._next_streak(rec, d("2026-09-30")) == 1



# ── cap / overflow ──────────────────────────────────────────────────────────────
def test_credit_applies_cap_and_discards(isolated_state):
    granted, discarded, bal = P.credit_points(UID, POINTS_BALANCE_CAP - 100, "topup")
    assert (granted, discarded, bal) == (POINTS_BALANCE_CAP - 100, 0, POINTS_BALANCE_CAP - 100)
    granted, discarded, bal = P.credit_points(UID, 500, "claim")  # only 100 room left
    assert granted == 100 and discarded == 400 and bal == POINTS_BALANCE_CAP


def test_topup_source_flips_gate(isolated_state):
    P.credit_points(UID, 300, "topup")
    assert P.get_points(UID)["has_topped_up"] is True
    P.credit_points(UID + 1, 300, "claim")   # non-topup credit must not flip it
    assert P.get_points(UID + 1)["has_topped_up"] is False


# ── try_claim integration ─────────────────────────────────────────────────────
def test_try_claim_awards_then_blocks(isolated_state):
    now = datetime(2026, 9, 27, 9, 0, 0)
    rng = random.Random(42)
    res = P.try_claim(UID, now=now, rng=rng)
    assert res["ok"] is True
    assert 10 <= res["awarded"] <= 200
    assert res["streak_days"] == 1
    rec = P.get_points(UID)
    assert rec["lifetime_claims"] == 1
    assert rec["points"] == res["new_balance"]

    again = P.try_claim(UID, now=now, rng=rng)   # immediate re-claim → cooldown
    assert again["ok"] is False and again["error"] == "cooldown" and again["next_in_s"] > 0

    later = P.try_claim(UID, now=now + timedelta(hours=4), rng=rng)   # cooldown cleared
    assert later["ok"] is True
    assert P.get_points(UID)["lifetime_claims"] == 2


def test_try_claim_builds_streak_and_guarantees_target_day(isolated_state):
    rng = random.Random(99)
    start = datetime(2026, 9, 1, 8, 0, 0)
    last = None
    for i in range(POINTS_STREAK_TARGET_DAYS):
        last = P.try_claim(UID, now=start + timedelta(days=i), rng=rng)
        assert last["ok"] is True
    assert last["streak_days"] == POINTS_STREAK_TARGET_DAYS
    assert last["is_streak_bonus"] is True
    low, high = POINTS_STREAK_REWARD
    assert low <= last["awarded"] <= high


# ── redeem gate (one Starter per user for life) ───────────────────────────────
def test_redeem_requires_topup(isolated_state):
    P.credit_points(UID, POINTS_STARTER_COST, "claim")   # enough points, never topped up
    res = P.redeem_starter(UID)
    assert res["ok"] is False and res["error"] == "needs_topup"


def test_redeem_insufficient_points(isolated_state):
    P.credit_points(UID, 100, "topup")
    res = P.redeem_starter(UID)
    assert res["ok"] is False and res["error"] == "insufficient_points"


def test_redeem_success_is_repeatable(isolated_state):
    # Starter is the ONLY product but it is repeatable while balance ≥ cost.
    P.credit_points(UID, 2 * P_STARTER + 200, "topup")
    first = P.redeem_starter(UID)
    assert first["ok"] is True and first["new_balance"] == P_STARTER + 200
    assert P.get_points(UID)["redeemed_count"] == 1

    second = P.redeem_starter(UID)   # enough left → redeem again
    assert second["ok"] is True and second["new_balance"] == 200
    assert P.get_points(UID)["redeemed_count"] == 2

    third = P.redeem_starter(UID)    # now too poor
    assert third["ok"] is False and third["error"] == "insufficient_points"


def test_refund_restores_points_and_count(isolated_state):
    P.credit_points(UID, P_STARTER, "topup")
    P.redeem_starter(UID)
    assert P.get_points(UID)["points"] == 0
    assert P.get_points(UID)["redeemed_count"] == 1
    P.refund_starter(UID)
    rec = P.get_points(UID)
    assert rec["points"] == P_STARTER and rec["redeemed_count"] == 0



