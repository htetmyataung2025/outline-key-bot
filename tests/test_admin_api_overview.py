"""Tests for GET /api/admin/overview endpoint."""

import pytest

ADMIN_ID = 111000111


@pytest.fixture()
def two_env_servers(monkeypatch):
    """Pin exactly two .env-configured servers (OUTLINE_API_URL_3 unset).

    Resets the settings + telemetry caches so the defaults are rebuilt from
    these patched values and the probe results never leak between tests.
    """
    import bot_app.config as config
    from bot_app.services.admin_telemetry import reset_telemetry_cache
    from bot_app.services.settings import invalidate_settings_cache

    monkeypatch.setattr(config, "OUTLINE_API_URL_1", "https://sg1.example.com/api")
    monkeypatch.setattr(config, "OUTLINE_API_URL_2", "https://sg2.example.com/api")
    monkeypatch.setattr(config, "OUTLINE_API_URL_3", "")
    invalidate_settings_cache(reset_fallback=True)
    reset_telemetry_cache()
    yield
    invalidate_settings_cache(reset_fallback=True)
    reset_telemetry_cache()


def test_admin_overview_telemetry(client, make_telegram_init_data, monkeypatch, two_env_servers):
    # Mock requests.get so no live network calls to Outline servers occur
    class FakeResponse:
        def __init__(self, status_code, json_data):
            self.status_code = status_code
            self._json = json_data

        def json(self):
            return self._json

    def mock_requests_get(url, *args, **kwargs):
        if "access-keys" in url:
            return FakeResponse(200, {"accessKeys": [{"id": "1"}, {"id": "2"}]})
        if "metrics/transfer" in url:
            return FakeResponse(200, {"bytesTransferredByUserId": {"1": 1000000000, "2": 2000000000}})
        return FakeResponse(404, {})

    monkeypatch.setattr("requests.get", mock_requests_get)

    init_data = make_telegram_init_data(user_id=ADMIN_ID)
    resp = client.get(
        "/api/admin/overview",
        headers={"X-Telegram-Init-Data": init_data},
    )

    assert resp.status_code == 200
    data = resp.json
    assert "servers" in data
    assert "metrics" in data
    assert "traffic_trend" in data
    assert data["metrics"]["pending_slips"] == 0
    # Loyalty-points KPIs are always present in the metrics bundle.
    for key in ("points_circulation", "points_holders", "points_starters_redeemed",
                "points_total_claims", "points_active_claimers", "points_avg_balance",
                "points_reward_ev", "points_est_days_to_starter"):
        assert key in data["metrics"]
    # Only the servers configured via the environment appear as nodes —
    # an unset OUTLINE_API_URL_* must never surface as a phantom server.
    assert {s["id"] for s in data["servers"]} == {1, 2}


def test_reward_velocity_is_config_derived():
    """EV/claim and days-to-Starter come purely from the reward table + cost,
    so tuning the preset changes the tuning signal with no user data."""
    from bot_app.services import settings as settings_svc
    from bot_app.services.admin_telemetry import _reward_velocity
    import bot_app.config as config

    settings_svc.invalidate_settings_cache(reset_fallback=True)
    try:
        settings_svc.save_system_settings({"points": {
            **config.default_points_settings(),
            "claim_cooldown_h": 4,          # → 6 claims/day
            "starter_cost": 5000,
            "reward_table": [[10, 30, 1]],  # EV = midpoint 20
        }}, updated_by="Tester")

        ev, days = _reward_velocity()
        assert ev == 20
        # 20 * (24//4=6) = 120/day → ceil(5000/120) = 42 days.
        assert days == 42
    finally:
        settings_svc.invalidate_settings_cache(reset_fallback=True)


def test_reward_velocity_handles_empty_table():
    from bot_app.services import settings as settings_svc
    from bot_app.services.admin_telemetry import _reward_velocity
    import bot_app.config as config

    settings_svc.invalidate_settings_cache(reset_fallback=True)
    try:
        # points_settings() falls back to the constant table for a bad one, so
        # force an empty table straight through the resolver's guard.
        block = config.default_points_settings()
        block["reward_table"] = []
        settings_svc.save_system_settings({"points": block}, updated_by="Tester")
        ev, days = _reward_velocity()
        # Falls back to the constant reward table → still a positive signal.
        assert ev > 0 and days > 0
    finally:
        settings_svc.invalidate_settings_cache(reset_fallback=True)


def test_overview_aggregates_points_velocity(client, make_telegram_init_data,
                                              monkeypatch, two_env_servers):
    """Seeded points records roll up into the velocity aggregates."""
    from datetime import timedelta
    from bot_app.services import points as P
    from bot_app.timeutil import myanmar_now

    now = myanmar_now()
    recent = (now - timedelta(hours=2)).strftime("%Y-%m-%d %H:%M:%S")
    stale = (now - timedelta(hours=72)).strftime("%Y-%m-%d %H:%M:%S")
    P.save_all_points({
        "1": {**P._default_record(), "points": 800, "lifetime_claims": 10, "last_claim_at": recent},
        "2": {**P._default_record(), "points": 200, "lifetime_claims": 5, "last_claim_at": stale},
    })

    def mock_requests_get(url, *args, **kwargs):
        class R:
            status_code = 200
            def json(self_inner):
                return {"accessKeys": []} if "access-keys" in url else {"bytesTransferredByUserId": {}}
        return R()

    monkeypatch.setattr("requests.get", mock_requests_get)

    resp = client.get("/api/admin/overview",
                      headers={"X-Telegram-Init-Data": make_telegram_init_data(user_id=ADMIN_ID)})
    m = resp.json["metrics"]
    assert m["points_total_claims"] == 15
    assert m["points_active_claimers"] == 1      # only the 2h-ago record is within 48h
    assert m["points_avg_balance"] == 500        # (800 + 200) / 2 holders
