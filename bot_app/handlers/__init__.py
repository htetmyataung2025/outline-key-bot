"""Telegram handler package. Import order = registration order:

common -> gate -> shop -> topup -> wallet -> keys -> redeem -> history
-> admin -> menu (catch-all text router MUST stay last: TeleBot runs the
first matching handler, so command/text handlers must register before it).
"""

from bot_app.handlers import common, gate, shop, topup, wallet  # noqa: F401
from bot_app.handlers import keys, redeem, history, admin, menu  # noqa: F401

__all__ = [
    "common", "gate", "shop", "topup", "wallet", "keys",
    "redeem", "history", "admin", "menu",
]

