"""Customer-facing PLANS view: HMA plans hidden, quotas sorted ascending.

The plans dict in the dynamic settings store (Supabase) keeps whatever
order the last dashboard save left it in, and a discontinued "HMA" plan
once resurfaced there, which scrambled the bot shop keyboard and showed
HMA to customers. ``_DynamicPlans`` must therefore always present the
seven real plans in 25 GB -> 500 GB order with HMA filtered out,
whatever the store holds. The raw store dict is never rewritten.
"""

from bot_app import config
from bot_app.services import settings


def _plan(name, gb, price):
    return {
        "name": name,
        "data": f"{gb} GB",
        "bytes": gb * 1000 ** 3,
        "price": price,
        "manual": False,
        "months": 1,
    }


SCRAMBLED_WITH_HMA = {
    "basic": _plan("Basic Plan", 50, 2000),
    "premium": _plan("Premium Plan", 100, 4000),
    "pro": _plan("Pro Plan", 200, 7000),
    "standard": _plan("Standard Plan", 75, 3000),
    "starter": _plan("Starter Plan", 25, 1000),
    "ultimate": _plan("Ultimate VIP Plan", 500, 10000),
    "vip": _plan("VIP Plan", 150, 5000),
    "hma": _plan("HMA Plan", 250, 8000),
}


def test_plans_view_sorted_and_hma_hidden(monkeypatch):
    monkeypatch.setattr(
        settings, "get_system_settings", lambda: {"plans": dict(SCRAMBLED_WITH_HMA)}
    )
    codes = [code for code, _ in config.PLANS.items()]
    assert codes == ["starter", "basic", "standard", "premium", "vip", "pro", "ultimate"]
    assert config.PLANS.get("hma") is None
    assert config.PLANS.get("starter")["price"] == 1000


def test_plans_view_defaults_unchanged():
    codes = [code for code, _ in config.PLANS.items()]
    assert codes == ["starter", "basic", "standard", "premium", "vip", "pro", "ultimate"]


def test_customer_plans_does_not_rewrite_input():
    raw = dict(SCRAMBLED_WITH_HMA)
    config._customer_plans(raw)
    assert list(raw) == list(SCRAMBLED_WITH_HMA)  # store order/content untouched
