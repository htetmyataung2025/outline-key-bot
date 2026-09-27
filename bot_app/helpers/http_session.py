"""Shared HTTP connection pooling.

Every Upstash/Supabase REST call used to open a fresh TLS connection
(~0.3-0.4 s of handshake per call on Myanmar networks). Sessions are
thread-local because ``requests.Session`` is not documented as
thread-safe and the dashboard handlers run reads in parallel workers.
"""

import threading

import requests

_tls = threading.local()


def get_session() -> requests.Session:
    """Return this thread's reusable ``requests.Session`` (created on demand)."""
    session = getattr(_tls, "session", None)
    if session is None:
        session = requests.Session()
        try:
            adapter = requests.adapters.HTTPAdapter(pool_connections=2, pool_maxsize=8)
            session.mount("https://", adapter)
            session.mount("http://", adapter)
        except Exception:
            pass
        _tls.session = session
    return session
