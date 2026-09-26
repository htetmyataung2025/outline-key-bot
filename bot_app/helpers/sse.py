"""One-time short-lived tickets for the admin SSE push channel.

The dashboard subscribes to live data changes via ``EventSource``, which —
unlike ``fetch`` — cannot attach custom headers. Rather than putting the
long-lived admin secret or Telegram initData into the URL (it would leak
into access logs), the client first exchanges its normal authenticated
session for a random single-use ticket valid for a few seconds, and opens
the stream with that.
"""

import secrets
import threading
import time

TICKET_TTL_SECONDS = 10

_tickets: dict[str, dict] = {}
_lock = threading.Lock()


def issue_ticket(admin_user: dict) -> str:
    """Create a one-time ticket bound to an already-authenticated admin."""
    ticket = secrets.token_urlsafe(24)
    issued = time.time()
    with _lock:
        # Opportunistic cleanup so abandoned tickets cannot accumulate.
        for t in [k for k, v in _tickets.items() if issued - v["issued"] > TICKET_TTL_SECONDS]:
            _tickets.pop(t, None)
        _tickets[ticket] = {"issued": issued, "admin": admin_user}
    return ticket


def consume_ticket(ticket: str) -> dict | None:
    """Validate and burn a ticket. Returns the bound admin profile or None.

    No re-validation of the admin profile happens here: tickets are only
    ever issued to sessions that already passed ``require_admin_api``, and
    the profile they carry (Telegram user or the desktop sentinel) is
    stored server-side — the URL only ever holds the random token.
    """
    if not ticket:
        return None
    with _lock:
        entry = _tickets.pop(ticket, None)
    if not entry:
        return None
    if time.time() - entry["issued"] > TICKET_TTL_SECONDS:
        return None
    return entry.get("admin") or None
