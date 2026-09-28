"""Settings-defaults build must never re-enter the dynamic config views.

Regression: ``_get_default_settings`` used ``list(MY_PAYMENT_PHONES)`` and
``dict(PLANS)``, whose ``_phones()``/``_data()`` call ``get_system_settings()``
again before the cache is populated. The mutual recursion was swallowed by
``except Exception: pass`` and each unwind level did a KV round-trip, so one
cold ``get_system_settings()`` took minutes and froze the /start handler.
"""

from bot_app import config
from bot_app.services import settings


def test_cold_get_system_settings_does_not_recurse(monkeypatch):
    settings.invalidate_settings_cache(reset_fallback=True)
    try:
        counts = {"phones": 0, "plans": 0, "kv": 0}

        orig_phones = config._DynamicPaymentPhones._phones

        def counting_phones(self):
            counts["phones"] += 1
            assert counts["phones"] < 10, "payment-phone view re-entered the settings build"
            return orig_phones(self)

        orig_data = config._DynamicPlans._data

        def counting_plans(self):
            counts["plans"] += 1
            assert counts["plans"] < 10, "plans view re-entered the settings build"
            return orig_data(self)

        orig_kv = settings.redis_get

        def counting_kv(key):
            counts["kv"] += 1
            assert counts["kv"] < 10, "KV read repeated per recursion level"
            return orig_kv(key)

        monkeypatch.setattr(config._DynamicPaymentPhones, "_phones", counting_phones)
        monkeypatch.setattr(config._DynamicPlans, "_data", counting_plans)
        monkeypatch.setattr(settings, "redis_get", counting_kv)

        result = settings.get_system_settings()

        assert "payment_phones" in result and "plans" in result and "points" in result
        # Defaults are built from env/constants only — zero dynamic-view reads.
        assert counts["phones"] == 0
        assert counts["plans"] == 0
        # One cold build = at most one KV read.
        assert counts["kv"] <= 1
    finally:
        settings.invalidate_settings_cache(reset_fallback=True)


def test_env_payment_phones_is_pure(monkeypatch):
    monkeypatch.setenv("MY_PAYMENT_PHONES", " 09-111 , 09-222,")
    assert config.env_payment_phones() == ["09-111", "09-222"]


def test_default_plans_is_pure():
    plans = config.default_plans()
    assert isinstance(plans, dict) and "starter" in plans
    # Mutating the returned dict must not affect the baseline.
    plans.pop("starter")
    assert "starter" in config.default_plans()
