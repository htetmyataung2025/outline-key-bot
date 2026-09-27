"""Phase 2: approving a payment slip grants loyalty points (single choke point).

Covers both review paths implicitly — the Telegram approve button and the
dashboard ``POST /slips/<id>/review`` both funnel through ``review_slip``.
Network-free: ``mock_bot`` stubs Telegram, ``isolated_state`` sandboxes files.
"""

from bot_app.services.points import get_points, topup_points_for
from bot_app.services.slips import record_slip, review_slip

UID = 610000123


def test_approve_grants_topup_points_and_flips_gate(isolated_state, mock_bot):
    record_slip("#PT0001", UID, 10000)
    res = review_slip("#PT0001", "APPROVE", reviewed_by=111000111)
    assert res["success"] is True

    rec = get_points(UID)
    assert rec["points"] == topup_points_for(10000) == 100
    assert rec["has_topped_up"] is True   # redeem gate opened by a real payment


def test_reject_grants_no_points(isolated_state, mock_bot):
    record_slip("#PT0002", UID, 10000)
    review_slip("#PT0002", "REJECT", reviewed_by=111000111, reason="blurry")

    rec = get_points(UID)
    assert rec["points"] == 0
    assert rec["has_topped_up"] is False


def test_small_topup_flips_gate_even_with_zero_points(isolated_state, mock_bot):
    # 50 Ks → floor(50/100) = 0 points, but it is still a real payment, so the
    # anti-Sybil gate must open.
    record_slip("#PT0003", UID, 50)
    review_slip("#PT0003", "APPROVE", reviewed_by=111000111)

    rec = get_points(UID)
    assert rec["points"] == 0
    assert rec["has_topped_up"] is True
