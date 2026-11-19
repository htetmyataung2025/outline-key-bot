"""Support Chat: app <-> Telegram admin <-> Muse agent (Bot Update #11b).

Storage is an in-memory stand-in for the module's redis_get/redis_set;
the Telegram bot is a stub that returns message ids so the forward map
can be exercised end to end.
"""

from types import SimpleNamespace

import pytest

import bot_app.routes_app as ra
from bot_app.services import support_chat as sc

ADMIN = 111000111
CUSTOMER = 555000111


class BotStub:
    def __init__(self):
        self.sent = []  # (chat_id, text, kwargs)
        self._next_id = 1000

    def send_message(self, chat_id, text, **kwargs):
        self._next_id += 1
        self.sent.append((chat_id, text, kwargs))
        return SimpleNamespace(message_id=self._next_id)


@pytest.fixture()
def store(monkeypatch):
    data = {}
    monkeypatch.setattr(sc, "redis_get", lambda key: data.get(key))
    monkeypatch.setattr(sc, "redis_set", lambda key, value: data.__setitem__(key, value))
    bot = BotStub()
    monkeypatch.setattr(sc, "bot", bot)
    pushes = []
    # raising=False: support_chat no longer imports the inbox push at all
    # (support replies stay out of the 30-cap inbox); the stub stays as a
    # tripwire so any future push through this module is caught here.
    monkeypatch.setattr(sc, "push_app_notification",
                        lambda cid, ntype, title, body: pushes.append((cid, ntype, title, body)),
                        raising=False)
    return SimpleNamespace(data=data, bot=bot, pushes=pushes)


def test_customer_say_appends_and_forwards(store):
    sc.customer_say(CUSTOMER, "Aung", "Key ချိတ်မရဘူး")
    thread = sc.load_thread(CUSTOMER)
    assert len(thread) == 1
    assert thread[0]["from"] == "user"
    assert thread[0]["text"] == "Key ချိတ်မရဘူး"
    # Forwarded to both admins with the presence buttons attached.
    assert {str(cid) for cid, _, _ in store.bot.sent} == {"111000111", "222000222"}
    assert all("reply_markup" in kw for _, _, kw in store.bot.sent)
    # The forward map can route a reply from either admin back.
    assert set(store.data[sc._FWD_KEY].values()) == {str(CUSTOMER)}


def test_admin_reply_routes_back_and_marks_presence(store):
    sc.customer_say(CUSTOMER, "Aung", "help")
    fwd_key = next(k for k in store.data[sc._FWD_KEY] if k.startswith(f"{ADMIN}:"))
    msg_id = int(fwd_key.split(":")[1])

    assert sc.admin_reply(ADMIN, msg_id, "Restart ချကြည့်ပါ") is True

    thread = sc.load_thread(CUSTOMER)
    assert [m["from"] for m in thread] == ["user", "admin"]
    assert thread[-1]["text"] == "Restart ချကြည့်ပါ"
    # Support replies stay OUT of the app inbox (30-item cap — owner
    # decision 2026-11-20); the owner still counts as present.
    assert store.pushes == []
    assert sc.owner_present() is True


def test_admin_reply_to_unknown_message_is_ignored(store):
    assert sc.admin_reply(ADMIN, 424242, "hello?") is False
    assert sc.load_thread(CUSTOMER) == []


def test_presence_expires_after_one_hour(store):
    sc.set_owner_present(True)
    assert sc.owner_present() is True
    store.data[sc._PRESENCE_KEY] = {"ts": sc._now() - 7200}
    assert sc.owner_present() is False
    sc.set_owner_present(False)
    assert sc.owner_present() is False


def test_agent_reply_blocked_while_owner_present(store):
    sc.customer_say(CUSTOMER, "Aung", "စျေးနှုန်း သိချင်တယ်")
    sc.set_owner_present(True)
    status, msg = sc.agent_reply(CUSTOMER, "Starter 1,000 Ks ပါ")
    assert status == "owner_present"
    assert msg is None
    assert [m["from"] for m in sc.load_thread(CUSTOMER)] == ["user"]

    sc.set_owner_present(False)
    status, msg = sc.agent_reply(CUSTOMER, "Starter 1,000 Ks ပါ")
    assert status == "ok"
    assert [m["from"] for m in sc.load_thread(CUSTOMER)] == ["user", "Muse"]
    # Agent answers also stay out of the app inbox (30-item cap).
    assert store.pushes == []
    # Admins receive an oversight copy of every agent answer.
    assert any("Claude Support ဖြေပြီး" in text for _, text, _ in store.bot.sent)


def test_pending_threads_and_escalation(store):
    sc.customer_say(CUSTOMER, "Aung", "ပိုက်ဆံ ပြန်အမ်းပေးပါ")
    pending = sc.pending_threads()
    assert len(pending) == 1
    assert pending[0]["chat_id"] == str(CUSTOMER)
    assert pending[0]["escalated"] is False

    sc.escalate(CUSTOMER, "Refund တောင်းဆို — owner ဆုံးဖြတ်ရန်")
    pending = sc.pending_threads()
    assert pending[0]["escalated"] is True
    assert any("Escalation" in text for _, text, _ in store.bot.sent)

    # Once answered (by anyone) the thread leaves the pending list.
    sc.agent_reply(CUSTOMER, "ခဏ စောင့်ပေးပါ ခင်ဗျာ")
    assert sc.pending_threads() == []


# --- endpoints ---------------------------------------------------------------

def test_app_support_endpoints_need_token(client, store):
    assert client.get("/api/app/support/messages").status_code == 401
    assert client.post("/api/app/support/send", json={"text": "hi"}).status_code == 401


def test_app_support_send_and_read(client, store, mock_bot):
    token = ra._make_app_token(CUSTOMER)
    resp = client.post("/api/app/support/send",
                       headers={"Authorization": f"Bearer {token}"},
                       json={"text": "Key ချိတ်မရဘူး"})
    assert resp.status_code == 200
    resp = client.get("/api/app/support/messages",
                      headers={"Authorization": f"Bearer {token}"})
    assert resp.status_code == 200
    msgs = resp.get_json()["messages"]
    assert len(msgs) == 1 and msgs[0]["text"] == "Key ချိတ်မရဘူး"


def test_agent_endpoints_need_secret(client, store, monkeypatch):
    monkeypatch.setenv("SUPPORT_AGENT_SECRET", "test-secret")
    assert client.get("/api/app/support/agent/pending").status_code == 401
    bad = {"X-Support-Agent-Secret": "wrong"}
    assert client.get("/api/app/support/agent/pending", headers=bad).status_code == 401

    good = {"X-Support-Agent-Secret": "test-secret"}
    sc.customer_say(CUSTOMER, "Aung", "help")
    resp = client.get("/api/app/support/agent/pending", headers=good)
    assert resp.status_code == 200
    body = resp.get_json()
    assert body["owner_present"] is False
    assert len(body["threads"]) == 1

    resp = client.post("/api/app/support/agent/reply", headers=good,
                       json={"chat_id": CUSTOMER, "text": "ဖြေပေးလိုက်ပြီ"})
    assert resp.status_code == 200
    assert sc.pending_threads() == []

    resp = client.post("/api/app/support/agent/presence", headers=good,
                       json={"present": True})
    assert resp.status_code == 200
    assert resp.get_json()["owner_present"] is True
    # While the owner is present the agent reply endpoint refuses.
    resp = client.post("/api/app/support/agent/reply", headers=good,
                       json={"chat_id": CUSTOMER, "text": "ထပ်ဖြေမယ်"})
    assert resp.status_code == 409
