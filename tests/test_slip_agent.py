"""Slip auto-review agent endpoints (Bot Update #19).

The agent mirrors the Support Chat presence model: it may list
pending slips and fetch slip photos with the agent secret, but the
review endpoint refuses while the owner is present. Reviews go
through the same ``review_slip`` choke point as the Telegram button,
recorded as reviewed_by="Claude Agent".
"""

import pytest

from bot_app.services import support_chat as sc
from bot_app.services.billing import get_user_balance
from bot_app.services.slips import get_slip_by_id, record_slip

UID = 555000333
SECRET = {"X-Support-Agent-Secret": "test-secret"}
PENDING = "/api/app/agent/slips/pending"
REVIEW = "/api/app/agent/slips/review"
PHOTO = "/api/app/agent/slips/photo"


@pytest.fixture()
def absent(monkeypatch):
    monkeypatch.setattr(sc, "owner_present", lambda: False)


def test_slip_agent_endpoints_need_secret(client, isolated_state, mock_bot):
    assert client.get(PENDING).status_code == 401
    assert client.get(PHOTO, query_string={"file_id": "x"}).status_code == 401
    assert client.post(REVIEW, json={"slip_id": "S1",
                                     "action": "APPROVE"}).status_code == 401


def test_pending_lists_slips_with_duplicate_flag(client, isolated_state,
                                                 mock_bot, absent,
                                                 monkeypatch):
    monkeypatch.setenv("SUPPORT_AGENT_SECRET", "test-secret")
    record_slip("S1", UID, 5000, file_id="f1", extracted_tx_id="111222")
    record_slip("S2", UID, 5000, file_id="f2", extracted_tx_id="111222")
    record_slip("S3", UID, 3000, file_id="f3", extracted_tx_id="999888")
    resp = client.get(PENDING, headers=SECRET)
    assert resp.status_code == 200
    body = resp.get_json()
    assert body["owner_present"] is False
    slips = {s["id"]: s for s in body["slips"]}
    assert set(slips) == {"S1", "S2", "S3"}
    assert slips["S1"]["tx_duplicate"] is True
    assert slips["S2"]["tx_duplicate"] is True
    assert slips["S3"]["tx_duplicate"] is False
    assert slips["S3"]["amount"] == 3000


def test_review_refused_while_owner_present(client, isolated_state,
                                            mock_bot, monkeypatch):
    monkeypatch.setenv("SUPPORT_AGENT_SECRET", "test-secret")
    monkeypatch.setattr(sc, "owner_present", lambda: True)
    record_slip("S1", UID, 5000, extracted_tx_id="111222")
    resp = client.post(REVIEW, headers=SECRET,
                       json={"slip_id": "S1", "action": "APPROVE"})
    assert resp.status_code == 409
    assert get_slip_by_id("S1")["status"] == "PENDING"


def test_review_approve_credits_wallet(client, isolated_state, mock_bot,
                                       absent, monkeypatch):
    monkeypatch.setenv("SUPPORT_AGENT_SECRET", "test-secret")
    record_slip("S1", UID, 5000, extracted_tx_id="111222")
    before = get_user_balance(UID)
    resp = client.post(REVIEW, headers=SECRET,
                       json={"slip_id": "S1", "action": "APPROVE",
                             "reason": "checks passed"})
    assert resp.status_code == 200
    assert resp.get_json()["success"] is True
    slip = get_slip_by_id("S1")
    assert slip["status"] == "APPROVED"
    assert slip["reviewed_by"] == "Claude Agent"
    assert get_user_balance(UID) == before + 5000
    # A second review of the same slip is refused by the choke point.
    resp = client.post(REVIEW, headers=SECRET,
                       json={"slip_id": "S1", "action": "APPROVE"})
    assert resp.status_code == 400


def test_review_validation(client, isolated_state, mock_bot, absent,
                           monkeypatch):
    monkeypatch.setenv("SUPPORT_AGENT_SECRET", "test-secret")
    resp = client.post(REVIEW, headers=SECRET,
                       json={"slip_id": "S1", "action": "MAYBE"})
    assert resp.status_code == 400
    resp = client.post(REVIEW, headers=SECRET,
                       json={"slip_id": "NOPE", "action": "APPROVE"})
    assert resp.status_code == 404


def test_slip_photo_endpoint(client, isolated_state, mock_bot, monkeypatch):
    monkeypatch.setenv("SUPPORT_AGENT_SECRET", "test-secret")
    monkeypatch.setattr(sc, "fetch_photo_bytes",
                        lambda fid: b"\xff\xd8img" if fid == "f1" else None)
    resp = client.get(PHOTO, headers=SECRET, query_string={"file_id": "f1"})
    assert resp.status_code == 200
    assert resp.data == b"\xff\xd8img"
    resp = client.get(PHOTO, headers=SECRET, query_string={"file_id": "zz"})
    assert resp.status_code == 404
