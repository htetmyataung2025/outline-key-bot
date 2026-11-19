"""Tests for the Google Sheets records backup (bot update #9).

The backup mirrors the live stores (Redis wallets/history/points/registry,
Supabase settings) into a Google Sheet owned by the admin. Zero network:
the Sheets client is a fake, and every data loader is monkeypatched.
"""

import json
import time
from types import SimpleNamespace

import pytest

from bot_app.services import sheets_backup

ADMIN_ID = 111000111
USER_ID = "555000555"
SECRET_API_URL = "https://secret.example/xyz"

FAKE_SA = json.dumps({
    "type": "service_account",
    "client_email": "backup@demo.iam.gserviceaccount.com",
    "private_key": "-----BEGIN PRIVATE KEY-----\nfake\n-----END PRIVATE KEY-----",
    "token_uri": "https://oauth2.googleapis.com/token",
})


@pytest.fixture
def configured_env(monkeypatch):
    monkeypatch.delenv("GOOGLE_SHEETS_BACKUP_SCRIPT_URL", raising=False)
    monkeypatch.delenv("GOOGLE_SHEETS_BACKUP_SCRIPT_SECRET", raising=False)
    monkeypatch.setenv("GOOGLE_SHEETS_BACKUP_ID", "sheet-123")
    monkeypatch.setenv("GOOGLE_SERVICE_ACCOUNT_JSON", FAKE_SA)


@pytest.fixture
def unconfigured_env(monkeypatch):
    monkeypatch.delenv("GOOGLE_SHEETS_BACKUP_ID", raising=False)
    monkeypatch.delenv("GOOGLE_SERVICE_ACCOUNT_JSON", raising=False)
    monkeypatch.delenv("GOOGLE_SHEETS_BACKUP_SCRIPT_URL", raising=False)
    monkeypatch.delenv("GOOGLE_SHEETS_BACKUP_SCRIPT_SECRET", raising=False)


@pytest.fixture
def script_env(monkeypatch, unconfigured_env):
    monkeypatch.setenv("GOOGLE_SHEETS_BACKUP_SCRIPT_URL",
                       "https://script.example/macros/s/AKfyc/exec")
    monkeypatch.setenv("GOOGLE_SHEETS_BACKUP_SCRIPT_SECRET", "s3cret")


class FakeClient:
    def __init__(self):
        self.ensured = None
        self.writes = {}

    def ensure_tabs(self, titles):
        self.ensured = list(titles)

    def write_tab(self, title, rows):
        self.writes[title] = rows


def _seed(monkeypatch):
    monkeypatch.setattr("bot_app.services.orders.load_all_users",
                        lambda: [ADMIN_ID, int(USER_ID)])
    monkeypatch.setattr("bot_app.services.profiles.load_all_profiles",
                        lambda: {USER_ID: {"full_name": "Aung Aung",
                                           "username": "aung"},
                                 str(ADMIN_ID): {"full_name": "Owner",
                                                 "username": "owner"}})
    monkeypatch.setattr("bot_app.services.billing.load_all_wallets",
                        lambda: {USER_ID: 3000})
    monkeypatch.setattr("bot_app.services.billing.load_expiring_credits",
                        lambda: {})
    monkeypatch.setattr("bot_app.services.points.load_all_points",
                        lambda: {USER_ID: {"points": 120}})
    monkeypatch.setattr("bot_app.services.slips.get_lifetime_topups_by_user",
                        lambda: {USER_ID: 9000})
    monkeypatch.setattr("bot_app.services.orders.get_purchase_history",
                        lambda **kw: {"items": [{
                            "order_id": "#O1", "time_str": "19/11/2026 10:00",
                            "chat_id": USER_ID, "full_name": "Aung Aung",
                            "username": "aung", "plan_name": "Basic Plan",
                            "months": 1, "disp_gb": "50 GB", "price": 2000,
                            "server_name": "Server 1 (SG-1)",
                            "expire_date": "19.12.2026", "kind": "paid",
                            "vpn_key": "ss://abc",
                        }]})
    monkeypatch.setattr("bot_app.services.slips.get_slips_list",
                        lambda status=None: [{
                            "id": "s1", "created_at": "2026-11-19 09:00:00",
                            "chat_id": USER_ID, "username": "aung",
                            "amount": 5000, "method": "KBZ",
                            "status": "APPROVED", "extracted_tx_id": "TX1",
                            "reviewed_by": "Admin",
                            "reviewed_at": "2026-11-19 09:05:00",
                        }])
    monkeypatch.setattr("bot_app.services.registry.load_persistent_keys",
                        lambda: {"1_77": {
                            "server": "1", "key_id": "77",
                            "name": "Aung (555000555) (1) 19.12.2026",
                            "chat_id": USER_ID, "order_id": "#O1",
                            "expire_date": "19.12.2026",
                            "limit_bytes": 50 * 1000 ** 3,
                            "access_url": "ss://abc",
                        }})
    monkeypatch.setattr("bot_app.services.settings.get_system_settings",
                        lambda: {
                            "plans": {"basic": {"name": "Basic Plan",
                                                "data": "50 GB", "price": 2000,
                                                "months": 1, "manual": False}},
                            "servers": [{"id": 1, "name": "Server 1 (SG-1)",
                                         "api_url": SECRET_API_URL}],
                        })


def test_cell_escapes_formulas():
    assert sheets_backup._cell("=SUM(A1:A2)").startswith("'")
    assert sheets_backup._cell("@mention").startswith("'")
    assert sheets_backup._cell("+cmd").startswith("'")
    assert sheets_backup._cell("-5") == "-5"
    assert sheets_backup._cell(-5) == -5
    assert sheets_backup._cell(2000) == 2000
    assert sheets_backup._cell(None) == ""
    assert sheets_backup._cell("plain") == "plain"


def test_users_rows_merge_all_sources(monkeypatch):
    _seed(monkeypatch)
    rows = sheets_backup._users_rows()
    header, *body = rows
    assert header[0] == "Chat ID"
    by_id = {row[0]: row for row in body}
    user = by_id[USER_ID]
    assert user[1] == "Aung Aung"
    assert user[3] == 3000          # wallet
    assert user[5] == 3000          # total (no bonus)
    assert user[6] == 120           # points
    assert user[7] == 9000          # lifetime top-ups
    assert user[8] == ""            # not admin
    assert by_id[str(ADMIN_ID)][8] == "Yes"


def test_run_backup_writes_all_tabs(isolated_state, configured_env, monkeypatch):
    _seed(monkeypatch)
    client = FakeClient()
    result = sheets_backup.run_backup(client=client)

    assert result["ok"] is True
    assert result["counts"] == {
        "Users": 2, "Purchases": 1, "Topups": 1,
        "Keys": 1, "Plans": 1, "Servers": 1,
    }
    assert client.ensured == sheets_backup.ALL_TABS
    assert set(client.writes) == set(sheets_backup.ALL_TABS)

    # The Outline management secret must never reach the sheet.
    all_cells = [c for rows in client.writes.values() for r in rows for c in r]
    assert SECRET_API_URL not in all_cells
    assert "secret.example" not in " ".join(str(c) for c in all_cells)
    servers_rows = client.writes["Servers"]
    assert servers_rows[1][2] == "Yes"  # configured flag only, no URL

    # Keys tab carries the access URL — that is the point of the backup.
    assert client.writes["Keys"][1][7] == "ss://abc"
    # Backup Info tab reports the run.
    info_text = " ".join(str(c) for r in client.writes["Backup Info"] for c in r)
    assert "Last backup" in info_text


def test_run_backup_not_configured(unconfigured_env):
    assert sheets_backup.is_configured() is False
    assert sheets_backup.run_backup() == {"ok": False, "reason": "not_configured"}
    assert sheets_backup.maybe_run_daily_backup() == {
        "ok": False, "reason": "not_configured"}


def test_daily_backup_throttle(configured_env, monkeypatch):
    _seed(monkeypatch)
    fake = FakeClient()
    monkeypatch.setattr(sheets_backup, "_build_client", lambda: fake)

    monkeypatch.setattr(sheets_backup, "redis_get",
                        lambda key: {"ts": time.time()})
    assert sheets_backup.maybe_run_daily_backup() == {"ok": True, "skipped": True}
    assert fake.writes == {}

    monkeypatch.setattr(sheets_backup, "redis_get",
                        lambda key: {"ts": time.time() - 21 * 3600})
    result = sheets_backup.maybe_run_daily_backup()
    assert result["ok"] is True
    assert set(fake.writes) == set(sheets_backup.ALL_TABS)


class _FakeHttpResp:
    def __init__(self, payload):
        self._payload = payload

    def raise_for_status(self):
        pass

    def json(self):
        return self._payload


def test_script_transport_run_backup(isolated_state, script_env, monkeypatch):
    """With the Apps Script env set, one POST delivers every tab."""
    _seed(monkeypatch)
    posted = {}

    def fake_post(url, json=None, timeout=None):
        posted["url"] = url
        posted["json"] = json
        return _FakeHttpResp({"ok": True})

    monkeypatch.setattr(sheets_backup.requests, "post", fake_post)

    assert sheets_backup.backup_status()["transport"] == "apps_script"
    result = sheets_backup.run_backup()
    assert result["ok"] is True
    assert posted["url"].endswith("/exec")
    assert posted["json"]["secret"] == "s3cret"
    titles = [t["title"] for t in posted["json"]["tabs"]]
    # Data tabs are built first; Backup Info is written last (it reports
    # the other tabs' row counts).
    assert titles == sheets_backup.ALL_TABS[1:] + sheets_backup.ALL_TABS[:1]
    users_tab = next(t for t in posted["json"]["tabs"] if t["title"] == "Users")
    assert users_tab["rows"][1][0] in (str(ADMIN_ID), USER_ID)


def test_script_transport_error_surfaces(script_env, monkeypatch):
    _seed(monkeypatch)
    monkeypatch.setattr(
        sheets_backup.requests, "post",
        lambda url, json=None, timeout=None: _FakeHttpResp(
            {"ok": False, "error": "bad_secret"}))
    result = sheets_backup.run_backup()
    assert result["ok"] is False
    assert "bad_secret" in result["reason"]


def test_backup_status_endpoint(client, make_telegram_init_data, unconfigured_env):
    headers = {"X-Telegram-Init-Data": make_telegram_init_data(user_id=ADMIN_ID)}
    resp = client.get("/api/admin/backup/status", headers=headers)
    assert resp.status_code == 200
    assert resp.json["configured"] is False
    assert resp.json["transport"] is None
    assert resp.json["last"] is None


def test_run_backup_endpoint(client, make_telegram_init_data, monkeypatch):
    headers = {"X-Telegram-Init-Data": make_telegram_init_data(user_id=ADMIN_ID)}
    monkeypatch.setattr(
        sheets_backup, "run_backup",
        lambda: {"ok": True, "counts": {"Users": 2},
                 "spreadsheet_id": "sheet-123"})
    resp = client.post("/api/admin/backup/sheets", headers=headers)
    assert resp.status_code == 200
    assert resp.json["success"] is True
    assert resp.json["counts"] == {"Users": 2}

    stranger = {"X-Telegram-Init-Data": make_telegram_init_data(user_id=999888777)}
    resp = client.post("/api/admin/backup/sheets", headers=stranger)
    assert resp.status_code == 403


def test_backup_command_admin_only(mock_bot, unconfigured_env):
    from bot_app.handlers import admin as admin_handlers

    # Non-admin: silently ignored.
    admin_handlers.handle_backup(SimpleNamespace(chat=SimpleNamespace(id=424242)))
    assert mock_bot.calls["send_message"] == []

    # Admin without configuration: gets the setup reminder.
    admin_handlers.handle_backup(
        SimpleNamespace(chat=SimpleNamespace(id=ADMIN_ID)))
    assert len(mock_bot.calls["send_message"]) == 1
    text = mock_bot.calls["send_message"][0][1]
    assert "GOOGLE_SHEETS_BACKUP_SCRIPT_URL" in text
