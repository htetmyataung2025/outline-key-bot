"""Outline Key Bot application package.

Importing this package registers every Telegram handler and Flask route.
"""

from bot_app.extensions import bot, flask_app
from bot_app.extensions import flask_app as app

from bot_app.handlers import (
    admin,
    common,
    gate,
    history,
    keys,
    leaderboard,
    menu,
    points,
    redeem,
    shop,
    topup,
    wallet,
)
from bot_app import routes

# Export for `from bot_app import app` or direct `app = app`
__all__ = [
    "app", "bot", "flask_app", "routes",
    "admin", "common", "gate", "history", "keys",
    "leaderboard", "menu", "points", "redeem", "shop", "topup", "wallet",
]
