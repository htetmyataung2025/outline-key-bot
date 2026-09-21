"""Flask routes (webhook, cron, health) - delegates to services/handlers."""

import telebot
from flask import jsonify, request

from bot_app.extensions import bot
from bot_app.extensions import flask_app as app
from bot_app.services.notifier import run_expiry_cron
from bot_app.timeutil import format_myanmar_now


@app.route("/health", methods=["GET"])
def health():
    return jsonify({"status": "ok", "time": format_myanmar_now()}), 200


@app.route("/cron-check", methods=["GET", "POST"])
def cron_check():
    result = run_expiry_cron()
    return jsonify({"status": "cron completed", **result}), 200


@app.route("/webhook", methods=["POST"])
def webhook():
    return _process_update()


@app.route("/", methods=["GET", "POST"])
def root():
    # POST on "/" kept working for backward compatibility with webhook URLs
    # that point at the bare domain (Telegram POSTs the update to "/").
    if request.method == "POST":
        return _process_update()
    return "Bot is running perfectly!", 200


def _process_update():
    try:
        json_string = request.get_data().decode("utf-8")
        update = telebot.types.Update.de_json(json_string)
        if update:
            bot.process_new_updates([update])
    except Exception as e:
        print("Webhook Processing Error:", e)
    return jsonify({"status": "ok"}), 200


@app.route("/<path:path>", methods=["GET"])
def not_found(path):
    # Unknown paths (scanners probing /.env etc.) must not return 200.
    return jsonify({"status": "not found"}), 404
