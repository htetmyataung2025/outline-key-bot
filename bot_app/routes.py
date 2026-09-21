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

import telebot
from flask import jsonify, request

from bot_app.extensions import bot
from bot_app.extensions import flask_app as app
from bot_app.services.notifier import run_expiry_cron

CRON_USER_AGENT = "vercel-cron"


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


@app.route("/", defaults={"path": ""}, methods=["GET", "POST"])
@app.route("/<path:path>", methods=["GET", "POST"])
def entry(path=""):
    if request.method == "POST":
        return _process_update()

    if _is_cron_request():
        result = run_expiry_cron()
        return jsonify({"status": "cron completed", **result}), 200

    # Hide secret-ish probe paths when the real path reaches us (dev/local).
    if path and path.rsplit("/", 1)[-1].startswith("."):
        return jsonify({"status": "not found"}), 404

    return "Bot is running perfectly!", 200

