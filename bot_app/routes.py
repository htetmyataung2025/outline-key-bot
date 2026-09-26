"""Flask routes: Telegram webhook + health + expiry cron.

⚠️ IMPORTANT (Vercel behaviour)
The project rewrites every request to ``/api/index.py`` and the WSGI app
receives PATH_INFO = the *rewrite destination*, NOT the client's path.
That is why the old monolith used one universal catch-all route, and why
``/health``, ``/webhook`` style routes never match on Vercel.

So this module is intentionally **path-agnostic**:

- any **POST** → Telegram update (webhook works on ``/``, ``/webhook``,
  ``/index.py``, ``/api/index.py`` — whatever the webhook URL is)
- **GET + Vercel Cron user-agent** → run the nightly expiry cron
- any other **GET** → 200 health text (uptime monitors); dotted probe paths
  (``/.env`` etc.) return 404 when the real path is visible (local/dev)
"""

import hashlib
import hmac
import os
import platform

import telebot
from flask import jsonify, request

from bot_app.config import (
    MY_PAYMENT_PHONES, OCR_API_KEY, REQUIRED_CHANNEL, TELEGRAM_TOKEN,
    admin_chat_ids, admin_env_sources, admin_ids_masked, is_telegram_configured,
    outline_api_urls,
)
from bot_app.extensions import bot
from bot_app.extensions import flask_app as app
from bot_app.services.notifier import run_expiry_cron

CRON_USER_AGENT = "vercel-cron"


def diag_key():
    """Access key for /diag: sha256(TELEGRAM_TOKEN)[:16] — token = the secret."""
    return hashlib.sha256((TELEGRAM_TOKEN or "").encode()).hexdigest()[:16]



def _process_update():
    """Parse and dispatch one Telegram update (always ACK 200)."""
    try:
        json_string = request.get_data().decode("utf-8")
        update = telebot.types.Update.de_json(json_string)
        if update:
            bot.process_new_updates([update])
    except Exception as e:
        print("Webhook Processing Error:", e)
    return jsonify({"status": "ok"}), 200


def _is_cron_request():
    ua = request.headers.get("User-Agent", "")
    return ua.startswith(CRON_USER_AGENT) or request.headers.get("x-vercel-cron") == "1"


def _is_diag_request():
    key = request.args.get("key", "")
    return bool(key) and hmac.compare_digest(key, diag_key())


def _diag_payload():
    """Secret-safe config snapshot (no ids/tokens in full, booleans + counts)."""
    urls = outline_api_urls()
    connectivity = {}
    import requests as _requests

    for i, url in enumerate(urls, 1):
        label = f"s{i}"
        get_ok = post_ok = False
        try:
            gr = _requests.get(f"{url}/access-keys", verify=False, timeout=6)
            get_ok = 200 <= gr.status_code < 400
        except Exception:
            get_ok = False
        try:
            pr = _requests.post(f"{url}/access-keys", verify=False, timeout=8)
            post_ok = 200 <= pr.status_code < 400
            # remove the test key so the diag doesn't leave stray keys on the server
            if post_ok:
                try:
                    kid = pr.json().get("id")
                    if kid:
                        _requests.delete(f"{url}/access-keys/{kid}", verify=False, timeout=8)
                except Exception:
                    pass
        except Exception:
            post_ok = False
        connectivity[label] = {
            "url": url if url else None,
            "get": get_ok,
            "post": post_ok,
        }

    return {
        "status": "ok",
        "platform": "vercel" if os.environ.get("VERCEL") else "local",
        "git_sha": os.environ.get("VERCEL_GIT_COMMIT_SHA", "")[:7],
        "python": platform.python_version(),
        "telegram_configured": is_telegram_configured(),
        "admins": len(admin_chat_ids()),
        "admin_ids_masked": admin_ids_masked(),
        "admin_env_sources": admin_env_sources(),
        "outline_servers": len(urls),
        "outline_connectivity": connectivity,
        "kv": bool(os.environ.get("KV_REST_API_URL")),
        "ocr": bool(OCR_API_KEY),
        "payment_phones": len(MY_PAYMENT_PHONES),
        "required_channel": REQUIRED_CHANNEL,
    }


from bot_app.routes_admin import admin_bp

# Register Admin REST API Blueprint
app.register_blueprint(admin_bp)


class VercelPathFixMiddleware:
    """Restores real request path from Vercel rewrite headers if rewritten to /api/index.py."""

    def __init__(self, wsgi_app):
        self.wsgi_app = wsgi_app

    def __call__(self, environ, start_response):
        matched = environ.get("HTTP_X_MATCHED_PATH") or environ.get("HTTP_X_FORWARDED_URI")
        if matched and environ.get("PATH_INFO") in ("/api/index.py", "/index.py"):
            environ["PATH_INFO"] = matched
        return self.wsgi_app(environ, start_response)


app.wsgi_app = VercelPathFixMiddleware(app.wsgi_app)


@app.route("/", defaults={"path": ""}, methods=["GET", "POST"])
@app.route("/<path:path>", methods=["GET", "POST"])
def entry(path=""):
    # If an admin API request was routed here (unmatched admin sub-path), return 404 JSON
    if request.path.startswith("/api/admin") or path.startswith("api/admin"):
        return jsonify({"error": "Admin endpoint not found"}), 404

    if request.method == "POST":
        return _process_update()

    # Protected self-check: GET /diag?key=<sha256(TELEGRAM_TOKEN)[:16]>
    if _is_diag_request():
        return jsonify(_diag_payload()), 200

    if _is_cron_request():
        result = run_expiry_cron()
        return jsonify({"status": "cron completed", **result}), 200

    # Hide secret-ish probe paths when the real path reaches us (dev/local).
    if path and path.rsplit("/", 1)[-1].startswith("."):
        return jsonify({"status": "not found"}), 404

    return "Bot is running perfectly!", 200



