"""Cooldown-ready reminder scan + secret-guarded ``/reminder-check`` endpoint.

Network-free: KV/Supabase disabled by conftest, so points state lands in the
isolated ``POINTS_FILE`` and every Telegram send is captured by ``mock_bot``.
"""

from datetime import datetime, timedelta

import pytest

from bot_app import config
from bot_app.services import points as P
from bot_app.services import points_reminder as PR
from bot_app.services import settings as settings_svc

_TS = "%Y-%m-%d %H:%M:%S"
NOW = datetime(2026, 9, 28, 12, 0, 0)


@pytest.fixture(autouse=True)
def clean_settings():
    settings_svc.invalidate_settings_cache(reset_fallback=True)
    yield
    settings_svc.invalidate_settings_cache(reset_fallback=True)


def _seed(records: dict):
    """Persist a ``{chat_id: partial_record}`` map into the isolated store."""
    data = {}
    for uid, patch in records.items():
        rec = P._default_record()
        rec.update(patch)
        data[str(uid)] = rec
    P.save_all_points(data)


def _claimed_ago(hours: float) -> str:
    return (NOW - timedelta(hours=hours)).strftime(_TS)


# ── run_cooldown_reminders: core behaviour ────────────────────────────────────
def test_ready_user_gets_reminder_and_flag_is_set(isolated_state, mock_bot):
    _seed({777: {"points": 1200, "last_claim_at": _claimed_ago(5), "reminder_sent": False}})

    result = PR.run_cooldown_reminders(now=NOW)

    assert result == {"reminded": 1, "scanned": 1, "disabled": False}
    sent = mock_bot.calls["send_message"]
    assert len(sent) == 1 and str(sent[0][0]) == "777"
    assert "Daily Reward" in sent[0][1] and "1,200" in sent[0][1]
    assert P.get_points(777)["reminder_sent"] is True


def test_already_reminded_user_is_skipped(isolated_state, mock_bot):
    _seed({777: {"last_claim_at": _claimed_ago(9), "reminder_sent": True}})

    result = PR.run_cooldown_reminders(now=NOW)

    assert result["reminded"] == 0
    assert mock_bot.calls["send_message"] == []


def test_user_still_on_cooldown_is_skipped(isolated_state, mock_bot):
    # Default cooldown is 4h; claimed 1h ago → not ready.
    _seed({777: {"last_claim_at": _claimed_ago(1), "reminder_sent": False}})

    result = PR.run_cooldown_reminders(now=NOW)

    assert result["reminded"] == 0
    assert mock_bot.calls["send_message"] == []
    assert P.get_points(777)["reminder_sent"] is False


def test_user_who_never_claimed_is_skipped(isolated_state, mock_bot):
    _seed({777: {"last_claim_at": None, "reminder_sent": False}})

    result = PR.run_cooldown_reminders(now=NOW)

    assert result["reminded"] == 0
    assert mock_bot.calls["send_message"] == []


def test_mixed_population_only_notifies_the_ready_ones(isolated_state, mock_bot):
    _seed({
        1: {"last_claim_at": _claimed_ago(5), "reminder_sent": False},   # ready
        2: {"last_claim_at": _claimed_ago(1), "reminder_sent": False},   # cooling
        3: {"last_claim_at": _claimed_ago(9), "reminder_sent": True},    # done
        4: {"last_claim_at": None, "reminder_sent": False},              # never
        5: {"last_claim_at": _claimed_ago(6), "reminder_sent": False},   # ready
    })

    result = PR.run_cooldown_reminders(now=NOW)

    assert result["reminded"] == 2
    notified = {str(c[0]) for c in mock_bot.calls["send_message"]}
    assert notified == {"1", "5"}


# ── Gating: master switch + reminder toggle ───────────────────────────────────
def test_master_off_is_a_noop(isolated_state, mock_bot):
    settings_svc.save_system_settings(
        {"points": {**config.default_points_settings(), "enabled": False}},
        updated_by="Tester",
    )
    _seed({777: {"last_claim_at": _claimed_ago(5), "reminder_sent": False}})

    result = PR.run_cooldown_reminders(now=NOW)

    assert result == {"reminded": 0, "scanned": 0, "disabled": True}
    assert mock_bot.calls["send_message"] == []


def test_reminder_toggle_off_is_a_noop(isolated_state, mock_bot):
    settings_svc.save_system_settings(
        {"points": {**config.default_points_settings(), "cooldown_reminder": False}},
        updated_by="Tester",
    )
    _seed({777: {"last_claim_at": _claimed_ago(5), "reminder_sent": False}})

    result = PR.run_cooldown_reminders(now=NOW)

    assert result["disabled"] is True
    assert mock_bot.calls["send_message"] == []


# ── Dedup lifecycle: a fresh claim re-arms the reminder ───────────────────────
def test_claim_resets_reminder_flag(isolated_state, mock_bot):
    _seed({777: {"points": 500, "last_claim_at": _claimed_ago(5),
                 "streak_days": 1, "last_streak_day": "2026-09-27",
                 "reminder_sent": True}})

    out = P.try_claim(777, now=NOW)

    assert out["ok"] is True
    assert P.get_points(777)["reminder_sent"] is False


def test_default_record_has_reminder_flag():
    assert P._default_record()["reminder_sent"] is False


def test_reminder_carries_inline_claim_button():
    markup = PR._claim_keyboard()
    btn = markup.keyboard[0][0]
    assert btn.callback_data == "points_claim"
    assert "Claim Now" in btn.text


# ── Endpoint auth: /reminder-check ────────────────────────────────────────────
def test_endpoint_disabled_without_secret(client, mock_bot, monkeypatch):
    monkeypatch.delenv("REMINDER_CRON_SECRET", raising=False)
    _seed({777: {"last_claim_at": _claimed_ago(5), "reminder_sent": False}})

    resp = client.get("/reminder-check?key=whatever")

    body = resp.get_json(silent=True)
    assert body is None or body.get("status") != "reminder completed"
    assert mock_bot.calls["send_message"] == []


def test_endpoint_rejects_wrong_secret(client, mock_bot, monkeypatch):
    monkeypatch.setenv("REMINDER_CRON_SECRET", "s3cret")
    _seed({777: {"last_claim_at": _claimed_ago(5), "reminder_sent": False}})

    resp = client.get("/reminder-check?key=nope")

    body = resp.get_json(silent=True)
    assert body is None or body.get("status") != "reminder completed"
    assert mock_bot.calls["send_message"] == []


def test_endpoint_runs_with_correct_query_secret(client, mock_bot, monkeypatch):
    monkeypatch.setenv("REMINDER_CRON_SECRET", "s3cret")
    _seed({777: {"last_claim_at": _claimed_ago(5), "reminder_sent": False}})

    resp = client.get("/reminder-check?key=s3cret")

    assert resp.status_code == 200
    body = resp.get_json()
    assert body["status"] == "reminder completed"
    assert body["reminded"] == 1
    assert len(mock_bot.calls["send_message"]) == 1


def test_endpoint_runs_with_bearer_header(client, mock_bot, monkeypatch):
    monkeypatch.setenv("REMINDER_CRON_SECRET", "s3cret")
    _seed({777: {"last_claim_at": _claimed_ago(5), "reminder_sent": False}})

    resp = client.get("/reminder-check", headers={"Authorization": "Bearer s3cret"})

    body = resp.get_json()
    assert body["status"] == "reminder completed"
    assert body["reminded"] == 1
