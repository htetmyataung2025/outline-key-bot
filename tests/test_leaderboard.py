"""Points Leaderboard: weekly-period math, ranking, bot view/toggle, /lb_reset.

Network-free: KV/Supabase disabled by conftest; ``mock_bot`` captures sends and
``isolated_state`` sandboxes files. A key regression guard here is that
rendering a board makes ZERO ``bot.get_chat`` calls (names come from profiles).
"""

from datetime import datetime, timedelta
from types import SimpleNamespace

import pytest

from bot_app import config
from bot_app.services import points as P
from bot_app.services import profiles as PR
from bot_app.services import settings as settings_svc
from bot_app.services.leaderboard import build_leaderboard, _leader_name

MON = datetime(2026, 9, 28, 10, 0, 0)   # a Monday
ADMIN = 111000111
NON_ADMIN = 999000999


@pytest.fixture(autouse=True)
def clean_settings():
    settings_svc.invalidate_settings_cache(reset_fallback=True)
    yield
    settings_svc.invalidate_settings_cache(reset_fallback=True)


def _rec(**over):
    r = P._default_record()
    r.update(over)
    return r


# ── Period math ───────────────────────────────────────────────────────────────
def test_week_start_defaults_to_iso_monday():
    assert P.current_week_start(MON) == "2026-09-28"
    assert P.current_week_start(datetime(2026, 10, 1, 5, 0, 0)) == "2026-09-28"  # same week
    assert P.current_week_start(datetime(2026, 10, 5, 5, 0, 0)) == "2026-10-05"  # next Monday


def test_week_start_honours_epoch_anchor():
    # 7-day blocks counted from a Thursday epoch, not ISO Monday.
    assert P.current_week_start(MON, "2026-09-24") == "2026-09-24"
    assert P.current_week_start(datetime(2026, 10, 2, 0, 0, 0), "2026-09-24") == "2026-10-01"


def test_week_score_zero_once_period_rolls_over():
    rec = _rec(week_earned=80, week_start="2026-09-28")
    assert P.week_score(rec, MON, "2026-09-28") == 80
    assert P.week_score(rec, datetime(2026, 10, 6), "2026-10-05") == 0


def test_bump_week_accumulates_then_resets():
    rec = _rec()
    P._bump_week(rec, 30, MON)
    P._bump_week(rec, 20, MON)
    assert rec["week_earned"] == 50 and rec["week_start"] == "2026-09-28"
    P._bump_week(rec, 15, datetime(2026, 10, 6))   # new period → reset
    assert rec["week_earned"] == 15 and rec["week_start"] == "2026-10-05"


def test_bump_week_ignores_non_positive():
    rec = _rec(week_earned=10, week_start="2026-09-28")
    P._bump_week(rec, 0, MON)
    P._bump_week(rec, -5, MON)
    assert rec["week_earned"] == 10


# ── Earning hooks bump the weekly counter ─────────────────────────────────────
def test_credit_points_bumps_week(isolated_state):
    P.credit_points(101, 200, "topup")
    rec = P.get_points(101)
    assert rec["week_earned"] == 200 and rec["week_start"] == P.current_week_start()


def test_try_claim_bumps_week(isolated_state):
    out = P.try_claim(102, now=MON)
    assert out["ok"]
    rec = P.get_points(102)
    assert rec["week_earned"] == out["granted"] and rec["week_start"] == "2026-09-28"


def test_admin_grant_bumps_week_but_deduct_does_not(isolated_state):
    P.admin_adjust_points(103, 500, admin_id="A")
    assert P.get_points(103)["week_earned"] == 500
    P.admin_adjust_points(103, -100, admin_id="A")
    assert P.get_points(103)["week_earned"] == 500   # deduct never adds


# ── Settings: leaderboard_epoch default + resolver + validation ───────────────
def test_epoch_defaults_none_and_resolves():
    assert config.default_points_settings()["leaderboard_epoch"] is None
    assert config.points_settings()["leaderboard_epoch"] is None
    settings_svc.save_system_settings(
        {"points": {**config.default_points_settings(), "leaderboard_epoch": "2026-09-24"}},
        updated_by="T")
    assert config.points_settings()["leaderboard_epoch"] == "2026-09-24"


@pytest.mark.parametrize("value,ok", [
    ("2026-09-24", True), ("", True), (None, True), ("not-a-date", False), ("2026/09/24", False),
])
def test_epoch_validation(value, ok):
    from bot_app.routes_admin import _validate_points_settings
    block = {**config.default_points_settings(), "leaderboard_epoch": value}
    accepted, err, norm = _validate_points_settings(block)
    assert accepted is ok
    if ok:
        assert norm["leaderboard_epoch"] == (value or None)


# ── Ranking ───────────────────────────────────────────────────────────────────
def test_leaderboard_total_ranks_by_lifetime():
    allp = {
        "1": _rec(lifetime_earned=500), "2": _rec(lifetime_earned=900),
        "3": _rec(lifetime_earned=0),
    }
    profs = {"1": {"username": "aa"}, "2": {"full_name": "Min Min"}}
    b = build_leaderboard(allp, profs, "total", "1", MON)
    assert [(r["rank"], r["name"], r["score"], r["is_me"]) for r in b["rows"]] == [
        (1, "Min Min", 900, False), (2, "@aa", 500, True)]
    assert b["me"] is None            # caller already in the top rows
    assert b["total_players"] == 2    # zero-score user excluded


def test_leaderboard_7d_uses_week_score():
    ws = P.current_week_start(MON)
    allp = {
        "1": _rec(lifetime_earned=9999, week_earned=10, week_start=ws),
        "2": _rec(lifetime_earned=1, week_earned=80, week_start=ws),
        "3": _rec(week_earned=500, week_start="2000-01-03"),   # stale → 0
    }
    b = build_leaderboard(allp, {}, "7d", "2", MON)
    assert [(r["rank"], r["score"]) for r in b["rows"]] == [(1, 80), (2, 10)]


def test_leaderboard_self_outside_top_is_appended():
    allp = {str(i): _rec(lifetime_earned=1000 - i) for i in range(1, 13)}  # 12 players
    b = build_leaderboard(allp, {}, "total", "12", MON)
    assert len(b["rows"]) == 10                 # capped at top 10
    assert b["me"]["rank"] == 12                # caller ranked below the cut
    assert all(not r["is_me"] for r in b["rows"])


def test_leaderboard_self_with_zero_has_no_rank():
    allp = {"1": _rec(lifetime_earned=50), "99": _rec(lifetime_earned=0)}
    b = build_leaderboard(allp, {}, "total", "99", MON)
    assert b["me"]["rank"] is None and b["me"]["score"] == 0


def test_leader_name_fallback_chain():
    assert _leader_name("111", {"username": "bob"}) == "@bob"
    assert _leader_name("111", {"full_name": "Aung Aung"}) == "Aung Aung"
    assert _leader_name("987654", None) == "User ••7654"
    assert _leader_name("987654", {"username": "", "full_name": ""}) == "User ••7654"


# ── Bot view + toggle + gating ────────────────────────────────────────────────
def _call(data, chat_id=ADMIN, message_id=770):
    return SimpleNamespace(
        id="cb", data=data,
        message=SimpleNamespace(chat=SimpleNamespace(id=chat_id), message_id=message_id),
    )


def test_view_renders_medals_and_highlights_self(isolated_state, mock_bot):
    from bot_app.handlers import leaderboard as LB
    ws = P.current_week_start()
    P.save_all_points({
        str(ADMIN): _rec(lifetime_earned=10, week_earned=10, week_start=ws),
        "500": _rec(lifetime_earned=999, week_earned=999, week_start=ws),
    })
    PR.save_user_profile(ADMIN, username="me")
    text, markup = LB.build_leaderboard_view(ADMIN, "7d")
    assert "🏆" in text and "🥇" in text and "▶" in text   # self row highlighted
    assert mock_bot.calls["get_chat"] == []                 # zero Telegram lookups
    datas = [b.callback_data for row in markup.keyboard for b in row]
    assert "lb_7d" in datas and "lb_total" in datas


def test_toggle_edits_in_place_no_duplicate(isolated_state, mock_bot):
    from bot_app.handlers import leaderboard as LB
    P.save_all_points({str(ADMIN): _rec(lifetime_earned=100)})
    LB.handle_leaderboard_toggle(_call("lb_total"))
    assert len(mock_bot.calls["edit_message_text"]) == 1
    assert mock_bot.calls["send_message"] == []             # edited, not re-sent


def test_toggle_not_modified_does_not_duplicate(isolated_state, mock_bot, monkeypatch):
    from bot_app.handlers import leaderboard as LB
    from telebot.apihelper import ApiTelegramException
    P.save_all_points({str(ADMIN): _rec(lifetime_earned=100)})

    def _raise(*a, **k):
        raise ApiTelegramException("editMessageText", "r",
                                   {"error_code": 400, "description": "Bad Request: message is not modified"})
    monkeypatch.setattr(LB.bot, "edit_message_text", _raise)
    LB.handle_leaderboard_toggle(_call("lb_7d"))
    assert mock_bot.calls["send_message"] == []


def test_lb_reset_admin_sets_epoch(isolated_state, mock_bot):
    from bot_app.handlers import leaderboard as LB
    LB.handle_lb_reset(SimpleNamespace(chat=SimpleNamespace(id=ADMIN),
                                       from_user=SimpleNamespace(id=ADMIN)))
    today = __import__("bot_app.timeutil", fromlist=["myanmar_now"]).myanmar_now().strftime("%Y-%m-%d")
    assert config.points_settings()["leaderboard_epoch"] == today
    assert len(mock_bot.calls["send_message"]) == 1


def test_lb_reset_ignores_non_admin(isolated_state, mock_bot):
    from bot_app.handlers import leaderboard as LB
    LB.handle_lb_reset(SimpleNamespace(chat=SimpleNamespace(id=NON_ADMIN),
                                       from_user=SimpleNamespace(id=NON_ADMIN)))
    assert config.points_settings()["leaderboard_epoch"] is None
    assert mock_bot.calls["send_message"] == []


def test_menu_button_visible_only_when_enabled():
    from bot_app.keyboards import get_main_menu_keyboard

    def _labels():
        kb = get_main_menu_keyboard(chat_id=NON_ADMIN)
        return [b["text"] for row in kb.keyboard for b in row]

    settings_svc.save_system_settings(
        {"points": {**config.default_points_settings(), "enabled": True}}, updated_by="T")
    assert "🏆 Leaderboard" in _labels()

    settings_svc.save_system_settings(
        {"points": {**config.default_points_settings(), "enabled": False}}, updated_by="T")
    assert "🏆 Leaderboard" not in _labels()


