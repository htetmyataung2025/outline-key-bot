"""Monthly per-server sales stock caps (Bot Update #25).

Some VPS plans meter transfer as inbound + outbound combined, so a
"5 TB" server can only carry about half that in customer quota before
overage charges ($0.01/GB) dwarf the plan price. For those servers the
owner caps how much plan quota may be SOLD per calendar month
(Myanmar time): once the month's sold GB reaches the cap, every buy
channel (Telegram bot, native app, Mini App) refuses further sales on
that server with a friendly "stock out for this month" message, and
sales reopen automatically on the 1st of the next month.

Accounting: a Redis counter ``stock_issued:<server>:<YYYY-MM>`` holds
the GB sold this month. It is incremented ONLY after a key has been
created successfully, and only for non-admin sales (admin purchases
are exempt and uncounted, mirroring the promo-cap rule in #18.1).
Renewals count (they sell another month of quota); key replacements
do not (the same quota moves server — they never pass through the buy
flows anyway). Points redemption and promo keys are unaffected: they
mint on Server 1 / Server 2, which are uncapped.

Caps come from the system settings key ``server_stock_gb``
(e.g. ``{"3": 2500, "4": 2500}``) when present, else the defaults
below. Servers absent from the table are uncapped. When Redis is
unreachable the check fails OPEN (sales continue) — the cap is a
business guardrail, not a payment control.
"""

import re

from bot_app.storage.kv import redis_incrby_with_expiry
from bot_app.timeutil import myanmar_now

DEFAULT_SERVER_STOCK_GB = {"3": 2500, "4": 2500}

# A monthly counter touched on the month's last day must outlive the
# month itself; 70 days also keeps last month's figure readable for a
# while after rollover.
_COUNTER_TTL_SECONDS = 70 * 24 * 3600


def _caps():
    """The active {server_id: cap_gb} table (settings override wins)."""
    try:
        from bot_app.services.settings import get_system_settings

        raw = (get_system_settings() or {}).get("server_stock_gb")
        if isinstance(raw, dict) and raw:
            caps = {}
            for key, value in raw.items():
                try:
                    caps[str(key)] = int(value)
                except (TypeError, ValueError):
                    continue
            if caps:
                return caps
    except Exception:
        pass
    return dict(DEFAULT_SERVER_STOCK_GB)


def stock_cap_gb(server_num):
    """Monthly sales cap in GB for a server, or None when uncapped."""
    return _caps().get(str(server_num))


def plan_gb(plan):
    """A plan's quota in whole GB (0 when it cannot be determined)."""
    if not plan:
        return 0
    raw_bytes = plan.get("bytes")
    if raw_bytes:
        try:
            return int(raw_bytes) // 1000**3
        except (TypeError, ValueError):
            pass
    match = re.search(r"(\d+)\s*GB", str(plan.get("data") or ""), re.IGNORECASE)
    return int(match.group(1)) if match else 0


def _counter_key(server_num, now=None):
    moment = now or myanmar_now()
    return f"stock_issued:{server_num}:{moment:%Y-%m}"


def stock_used_gb(server_num):
    """GB already sold on this server in the current month.

    Reads the counter with a zero increment (atomic, cache-free).
    Returns 0 when the counter does not exist or Redis is unreachable.
    """
    value = redis_incrby_with_expiry(_counter_key(server_num), 0, _COUNTER_TTL_SECONDS)
    return int(value) if value is not None else 0


def stock_available(server_num, plan):
    """True when selling ``plan`` on ``server_num`` stays within the cap."""
    cap = stock_cap_gb(server_num)
    if cap is None:
        return True
    add = plan_gb(plan)
    if add <= 0:
        return True
    return stock_used_gb(server_num) + add <= cap


def record_stock_sale(server_num, plan):
    """Add a completed sale's GB to this month's counter (capped only)."""
    if stock_cap_gb(server_num) is None:
        return None
    add = plan_gb(plan)
    if add <= 0:
        return None
    return redis_incrby_with_expiry(_counter_key(server_num), add, _COUNTER_TTL_SECONDS)


def stock_out_message(server_num):
    """The customer-facing refusal shared by all three buy channels."""
    from bot_app.services.outline import get_server_label

    return (
        f"📦 {get_server_label(str(server_num))} အတွက် ခုလအတွက် "
        "Stock ကုန်သွားပါပြီ — တခြား Server ရွေးဝယ်နိုင်ပါတယ် ခင်ဗျာ။"
    )
