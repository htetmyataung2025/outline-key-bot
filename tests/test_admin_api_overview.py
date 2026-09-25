"""Tests for GET /api/admin/overview endpoint."""

import pytest

ADMIN_ID = 111000111


def test_admin_overview_telemetry(client, make_telegram_init_data, monkeypatch):
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
    assert len(data["servers"]) == 3
