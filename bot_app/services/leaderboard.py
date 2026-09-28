"""Points leaderboard ranking — pure, offline-testable, zero Telegram API.

Two boards: ``total`` (lifetime_earned — never resets, survives redemption) and
``7d`` (points earned in the current weekly period; see ``points.week_score`` /
``points.current_week_start`` for the auto-reset + admin ``/lb_reset`` semantics).

Names come from the ``user_profiles`` store (captured at the gate), never from a
live ``bot.get_chat`` — a board of N rows must cost zero Telegram calls. Unknown
users are shown as a masked id so raw chat_ids are never exposed.
"""

from bot_app.services.points import _leaderboard_epoch, week_score

import re

_NAME_MAX = 20


def _clean(text: str) -> str:
    """Collapse newlines/tabs/runs of spaces so a multi-line profile name can
    never break the single-line board layout."""
    return re.sub(r"\s+", " ", text or "").strip()


def _leader_name(uid, profile: dict | None) -> str:
    """Display label: display name → ``@username`` → masked id (``User ••1234``).

    The human display name is preferred so the board reads as a roster of names;
    long names are capped so every row stays tidy. ``@username`` handles are left
    intact (bounded + meaningful/clickable); the masked id never leaks a raw
    chat_id.
    """
    profile = profile or {}
    full = _clean(profile.get("full_name") or "")
    if full:
        return full if len(full) <= _NAME_MAX else full[:_NAME_MAX - 1] + "…"
    username = (profile.get("username") or "").strip()
    if username:
        return "@" + username
    return f"User ••{str(uid)[-4:]}"


def _score_for(rec: dict, mode: str, now, epoch) -> int:
    if mode == "total":
        return int(rec.get("lifetime_earned", 0) or 0)
    return week_score(rec, now, epoch)


def build_leaderboard(all_points: dict, profiles: dict, mode: str, me_id,
                      now=None, top_n: int = 10) -> dict:
    """Rank users for ``mode`` (``"7d"`` | ``"total"``).

    Returns ``{"mode", "rows", "me", "total_players"}`` where ``rows`` is the
    top ``top_n`` (each ``{rank, uid, name, score, is_me}``) and ``me`` is the
    caller's own entry (``{rank, name, score}``) — present whenever the caller
    is NOT already inside ``rows`` (so the view can append their standing), and
    ``rank`` is ``None`` when the caller has no score this period.
    """
    mode = "total" if mode == "total" else "7d"
    epoch = _leaderboard_epoch()
    me = str(me_id)

    scored = []
    for uid, rec in all_points.items():
        if not isinstance(rec, dict):
            continue
        score = _score_for(rec, mode, now, epoch)
        if score > 0:
            scored.append((str(uid), score))

    # Highest first; stable tie-break on uid so ranks are deterministic.
    scored.sort(key=lambda t: (-t[1], t[0]))

    rows = []
    me_in_top = False
    me_rank = None
    me_score = 0
    for idx, (uid, score) in enumerate(scored):
        rank = idx + 1
        if uid == me:
            me_rank, me_score, me_in_top = rank, score, rank <= top_n
        if rank <= top_n:
            rows.append({
                "rank": rank, "uid": uid, "score": score,
                "name": _leader_name(uid, profiles.get(uid)),
                "is_me": uid == me,
            })

    me_entry = None
    if not me_in_top:
        me_entry = {
            "rank": me_rank,   # None when the caller has 0 this period
            "score": me_score,
            "name": _leader_name(me, profiles.get(me)),
        }

    return {"mode": mode, "rows": rows, "me": me_entry, "total_players": len(scored)}
