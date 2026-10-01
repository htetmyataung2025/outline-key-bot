"""Regression tests: one-tap key import (/go deep links + delivery keyboards).

Background: customers had to copy the ss:// key and paste it into their VPN
app. Telegram URL buttons reject custom schemes (ss://), so the bot hands out
HMAC-signed https links to /go/<token>, which fires the app scheme. These
tests pin the signing, the registry lookup, the landing page, and the
delivery keyboards.
"""

from bot_app.config import DASHBOARD_URL
from bot_app.extensions import flask_app
from bot_app.helpers import deeplink
from bot_app.services.registry import save_persistent_key

SS_URL = "ss://YWJjLXNlY3JldA@h.e.feature.hma.qzz.io:443/?outline=1#Test User (123) 01.11.2026"


def _seed_key():
    save_persistent_key(
        server_num="1",
        key_id="777",
        name="Test User (123) 01.11.2026",
        access_url=SS_URL,
    )


# ---------------------------------------------------------------------------
# token signing
# ---------------------------------------------------------------------------

def test_go_token_roundtrip(isolated_state):
    _seed_key()
    token = deeplink.make_go_token("1", "777")
    assert deeplink.verify_go_token(token) == ("1", "777")


def test_go_token_rejects_tamper_and_garbage(isolated_state):
    token = deeplink.make_go_token("1", "777")
    # flip a char inside the token
    bad = ("A" if token[0] != "A" else "B") + token[1:]
    assert deeplink.verify_go_token(bad) is None
    assert deeplink.verify_go_token(token[:-2]) is None
    assert deeplink.verify_go_token("not-a-token") is None
    assert deeplink.verify_go_token("") is None


# ---------------------------------------------------------------------------
# registry lookup by access URL
# ---------------------------------------------------------------------------

def test_find_key_ref_matches_despite_name_fragment(isolated_state):
    _seed_key()
    renamed = SS_URL.split("#")[0] + "#Some Other Label"
    assert deeplink.find_key_ref_by_url(SS_URL) == ("1", "777")
    assert deeplink.find_key_ref_by_url(renamed) == ("1", "777")


def test_find_key_ref_unknown_url_returns_none(isolated_state):
    assert deeplink.find_key_ref_by_url("ss://unknown@host:443/?outline=1#x") is None
    assert deeplink.find_key_ref_by_url("") is None


# ---------------------------------------------------------------------------
# delivery keyboards
# ---------------------------------------------------------------------------

def test_import_keyboard_has_two_valid_url_buttons(isolated_state):
    _seed_key()
    markup = deeplink.get_key_import_keyboard(SS_URL)
    assert markup is not None
    buttons = [b for row in markup.keyboard for b in row]
    urls = [b.url for b in buttons]
    assert len(urls) == 2
    for u in urls:
        assert u.startswith(f"{DASHBOARD_URL}/go/")
        assert len(u) <= 256  # Telegram URL button limit
    assert any("app=outline" in u for u in urls)
    assert any("app=incy" in u for u in urls)
    # the ss:// secret itself must never appear in the button URL
    assert all("YWJj" not in u for u in urls)


def test_delivery_markup_falls_back_for_unregistered_key(isolated_state):
    markup = deeplink.get_key_delivery_markup("ss://unknown@host:443/?outline=1#x")
    datas = [b.callback_data or b.url for row in markup.keyboard for b in row]
    assert datas == ["back_to_main"]


def test_delivery_markup_appends_back_row(isolated_state):
    _seed_key()
    markup = deeplink.get_key_delivery_markup(SS_URL)
    texts = [b.text for row in markup.keyboard for b in row]
    assert any("Outline" in t for t in texts)
    assert any("Menu" in t for t in texts)


# ---------------------------------------------------------------------------
# /go/<token> landing page
# ---------------------------------------------------------------------------

def test_go_page_renders_ss_and_incy_links(isolated_state):
    _seed_key()
    token = deeplink.make_go_token("1", "777")
    client = flask_app.test_client()

    resp = client.get(f"/go/{token}?app=outline")
    assert resp.status_code == 200
    body = resp.get_data(as_text=True)
    assert SS_URL in body                     # js payload + href
    assert f"incy://add/{SS_URL}" in body     # INCY one-tap link
    assert "Copy" in body                     # V2Box fallback

    resp2 = client.get(f"/go/{token}?app=incy")
    assert resp2.status_code == 200


def test_go_page_rejects_bad_token_and_missing_key(isolated_state):
    _seed_key()
    client = flask_app.test_client()
    assert client.get("/go/garbage").status_code == 404
    assert client.get(f"/go/{deeplink.make_go_token('1', '999999')}").status_code == 404


def test_go_page_survives_local_path_routing(isolated_state):
    """Local/dev hits /go/<token> directly (no Vercel rewrite headers); Flask
    must route it over the catch-all entry rule."""
    _seed_key()
    client = flask_app.test_client()
    resp = client.get(f"/go/{deeplink.make_go_token('1', '777')}")
    assert resp.status_code == 200
