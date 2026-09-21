"""In-memory callback dedup (per-process; Vercel-safe best-effort)."""

PROCESSED_CALLBACKS: set = set()
_MAX_ENTRIES = 1000


def is_callback_processed(call_id: str) -> bool:
    """Return True if this callback was already handled (double-tap guard)."""
    if call_id in PROCESSED_CALLBACKS:
        return True
    PROCESSED_CALLBACKS.add(call_id)
    if len(PROCESSED_CALLBACKS) > _MAX_ENTRIES:
        PROCESSED_CALLBACKS.clear()
    return False


def _reset_for_tests() -> None:
    PROCESSED_CALLBACKS.clear()
