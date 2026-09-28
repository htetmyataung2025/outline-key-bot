"""§9: Settings-configurable Points economy.

Covers the dynamic-settings plumbing added on top of the locked economics:
- ``points`` block is part of the default settings bundle (all fields present).
- ``config.points_settings()`` resolves dynamic values at call time and falls
  back per-field to the hardcoded ``POINTS_*`` constants when a stored value is
  missing or malformed.
- ``POST /settings`` strictly validates the ``points`` block (ranges +
  reward-table rules) before it reaches storage.
- The master switch (``enabled=false``) gates every action while preserving
  stored balances: the reward button is hidden and the top-up hook is skipped.

Network-free: KV/Supabase disabled in conftest, so ``save_system_settings``
persists into the in-memory fallback and ``points_settings`` reads it back.
"""

import pytest

from bot_app import config
from bot_app.services import settings as settings_svc


def _full_points_block(**overrides):
    """A valid points block (defaults) with optional field overrides."""
    block = config.default_points_settings()
    block.update(overrides)
    return block


@pytest.fixture(autouse=True)
def clean_settings():
    settings_svc.invalidate_settings_cache(reset_fallback=True)
    yield
    settings_svc.invalidate_settings_cache(reset_fallback=True)


def _save_points(block):
    settings_svc.invalidate_settings_cache(reset_fallback=True)
    settings_svc.save_system_settings({"points": block}, updated_by="Tester")


# ── Defaults ─────────────────────────────────────────────────────────────────
def test_default_settings_include_full_points_block():
    defaults = settings_svc._get_default_settings()
    assert "points" in defaults
    block = defaults["points"]
    for key in (
        "enabled", "claim_cooldown_h", "balance_cap", "topup_rate", "topup_cap",
        "starter_cost", "streak_target_days", "streak_reward", "on_admin_topup",
        "reward_table",
    ):
        assert key in block, f"missing {key}"
    assert block["enabled"] is True
    assert block["balance_cap"] == config.POINTS_BALANCE_CAP
    assert block["reward_table"]  # non-empty


# ── points_settings() resolution + fallback ──────────────────────────────────
def test_points_settings_returns_defaults_when_store_empty():
    cfg = config.points_settings()
    assert cfg["claim_cooldown_h"] == config.POINTS_CLAIM_COOLDOWN_H
    assert cfg["balance_cap"] == config.POINTS_BALANCE_CAP
    assert cfg["starter_cost"] == config.POINTS_STARTER_COST
    assert cfg["streak_reward"] == tuple(config.POINTS_STREAK_REWARD)
    assert cfg["reward_table"] == [tuple(r) for r in config.POINTS_REWARD_TABLE]
    assert config.points_enabled() is True


def test_points_settings_reflects_dynamic_edits():
    _save_points(_full_points_block(
        claim_cooldown_h=8, balance_cap=30000, starter_cost=6000,
        topup_rate=200, topup_cap=500, streak_target_days=10,
        streak_reward=[300, 400], reward_table=[[10, 20, 5], [21, 40, 2]],
    ))
    cfg = config.points_settings()
    assert cfg["claim_cooldown_h"] == 8
    assert cfg["balance_cap"] == 30000
    assert cfg["starter_cost"] == 6000
    assert cfg["topup_rate"] == 200
    assert cfg["topup_cap"] == 500
    assert cfg["streak_target_days"] == 10
    assert cfg["streak_reward"] == (300, 400)
    assert cfg["reward_table"] == [(10, 20, 5), (21, 40, 2)]


def test_points_settings_falls_back_on_malformed_values():
    # topup_rate below the minimum and a broken reward table must NOT poison the
    # economy — each field independently falls back to its constant.
    _save_points(_full_points_block(
        topup_rate=0, reward_table=[["oops", 1]],
    ))
    cfg = config.points_settings()
    assert cfg["topup_rate"] == config.POINTS_TOPUP_RATE
    assert cfg["reward_table"] == [tuple(r) for r in config.POINTS_REWARD_TABLE]


def test_topup_formula_follows_dynamic_rate_and_cap():
    from bot_app.services import points as P
    _save_points(_full_points_block(topup_rate=200, topup_cap=50))
    assert P.topup_points_for(10000) == 50   # floor(10000/200)=50, under cap
    assert P.topup_points_for(100000) == 50  # capped


def test_points_enabled_reflects_master_switch():
    _save_points(_full_points_block(enabled=False))
    assert config.points_enabled() is False


# ── POST /settings validation ────────────────────────────────────────────────
def _post_points(client, monkeypatch, block):
    monkeypatch.setenv("ADMIN_SECRET_KEY", "test-pin-123")
    return client.post(
        "/api/admin/settings",
        json={"points": block},
        headers={"Authorization": "Bearer test-pin-123", "X-Admin-ID": "111000111"},
    )


def test_post_valid_points_block_succeeds(client, monkeypatch):
    resp = _post_points(client, monkeypatch, _full_points_block(
        claim_cooldown_h=6, balance_cap=25000, starter_cost=5000,
    ))
    assert resp.status_code == 200
    saved = resp.get_json()["settings"]["points"]
    assert saved["claim_cooldown_h"] == 6
    assert saved["balance_cap"] == 25000


@pytest.mark.parametrize("bad", [
    {"claim_cooldown_h": 0},
    {"claim_cooldown_h": 25},
    {"balance_cap": 0},
    {"topup_rate": 0},
    {"topup_cap": -1},
    {"starter_cost": 0},
    {"starter_cost": 999999},                 # > balance_cap
    {"streak_target_days": 0},
    {"streak_target_days": 31},
    {"streak_reward": [200, 100]},            # low > high
    {"streak_reward": [1, 999999]},           # high > balance_cap
    {"reward_table": []},                     # empty
    {"reward_table": [[10, 20, 0]]},          # weight not > 0
    {"reward_table": [[20, 10, 5]]},          # low > high
    {"reward_table": [[10, 999999, 5]]},      # high > balance_cap
    {"reward_table": [[10, 20]]},             # wrong arity
])
def test_post_invalid_points_block_rejected(client, monkeypatch, bad):
    resp = _post_points(client, monkeypatch, _full_points_block(**bad))
    assert resp.status_code == 400
    assert "points" in resp.get_json()["error"].lower()


def test_post_points_does_not_disturb_other_settings(client, monkeypatch):
    resp = _post_points(client, monkeypatch, _full_points_block(enabled=False))
    assert resp.status_code == 200
    body = resp.get_json()["settings"]
    assert body["points"]["enabled"] is False
    assert "servers" in body and "plans" in body


# ── Master-OFF gating ─────────────────────────────────────────────────────────
def test_master_off_hides_reward_button():
    from bot_app.keyboards import get_main_menu_keyboard

    _save_points(_full_points_block(enabled=True))
    assert "Daily Reward" in get_main_menu_keyboard().to_json()

    _save_points(_full_points_block(enabled=False))
    assert "Daily Reward" not in get_main_menu_keyboard().to_json()


def test_master_off_skips_topup_points_hook(isolated_state, mock_bot):
    from bot_app.services.points import get_points
    from bot_app.services.slips import record_slip, review_slip

    _save_points(_full_points_block(enabled=False))

    uid = 610000999
    record_slip("#PTOFF1", uid, 10000)
    res = review_slip("#PTOFF1", "APPROVE", reviewed_by=111000111)
    assert res["success"] is True

    rec = get_points(uid)
    assert rec["points"] == 0            # no points granted while system is OFF
    assert rec["has_topped_up"] is False  # gate stays closed too


def test_master_on_reward_view_reflects_dynamic_values(isolated_state, mock_bot):
    from bot_app.handlers.points import build_reward_view

    _save_points(_full_points_block(balance_cap=30000, starter_cost=6000))
    text, _markup = build_reward_view(610000998)
    assert "30,000" in text        # dynamic cap surfaced
    assert "6,000 Points" in text  # dynamic starter cost surfaced
