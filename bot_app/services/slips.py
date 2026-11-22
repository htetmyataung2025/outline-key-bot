"""Slips storage and payment verification queue service."""

import json
import os
from bot_app.timeutil import myanmar_now

from bot_app.extensions import bot
from bot_app.services.billing import update_user_balance
from bot_app.storage.kv import redis_get, redis_set
from bot_app.storage.paths import AUDIT_LOGS_FILE, SLIPS_FILE


def load_all_slips() -> dict:
    data = redis_get("admin_slips_data")
    if data is not None and isinstance(data, dict):
        return data
    if os.path.exists(SLIPS_FILE):
        try:
            with open(SLIPS_FILE, "r") as f:
                return json.load(f)
        except Exception:
            pass
    return {}


def save_all_slips(slips: dict):
    redis_set("admin_slips_data", slips)
    try:
        with open(SLIPS_FILE, "w") as f:
            json.dump(slips, f, indent=2)
    except Exception:
        pass


def record_slip(
    slip_id: str,
    chat_id: int | str,
    amount: int,
    username: str = "",
    image_url: str = "",
    file_id: str = "",
    extracted_tx_id: str = "",
    admin_messages: list | None = None,
    admin_caption: str = "",
    method: str = "KBZ",
    ocr_amount: int | None = None,
    selected_amount: int | None = None,
    unverified_photo: bool = False,
) -> dict:
    slips = load_all_slips()
    now = myanmar_now()
    slip_record = {
        "id": str(slip_id),
        "chat_id": str(chat_id),
        "amount": int(amount),
        "username": username or "Unknown",
        "image_url": image_url,
        "file_id": file_id,
        "extracted_tx_id": extracted_tx_id,
        # Bot Update #20: the amount OCR read off the slip photo and the
        # amount the customer originally selected, kept for audit whenever
        # intake auto-filled the recorded amount from the slip itself.
        "ocr_amount": ocr_amount,
        "selected_amount": selected_amount,
        # Bot Update #21: True when the customer overrode the slip-photo
        # gate ("this IS a real slip") — OCR could not verify the photo,
        # so a human must check it before approving.
        "unverified_photo": bool(unverified_photo),
        "method": str(method or "KBZ").upper(),
        "status": "PENDING",  # PENDING, APPROVED, REJECTED
        "reviewed_by": None,
        "reviewed_at": None,
        "review_reason": None,
        "created_at": now.strftime("%Y-%m-%d %H:%M:%S"),
        # Telegram notifications sent to admin chats for this slip
        # ([{"chat_id": ..., "message_id": ...}]) plus the original caption,
        # so a dashboard-side review can edit those messages too.
        "admin_messages": admin_messages or [],
        "admin_caption": admin_caption,
    }
    slips[str(slip_id)] = slip_record
    save_all_slips(slips)
    return slip_record


def get_lifetime_topups_by_user() -> dict:
    """Map ``chat_id`` -> total APPROVED top-up amount (lifetime real money paid in).

    Sums the ``amount`` of every slip whose status is ``APPROVED``; PENDING and
    REJECTED slips do not count. This is the customer's lifetime "Total Spent"
    figure — real bank/wallet top-ups only, not admin manual credits or promo
    redeem codes, which are separate wallet adjustments.
    """
    totals: dict[str, int] = {}
    for slip in load_all_slips().values():
        if slip.get("status") == "APPROVED":
            uid = str(slip.get("chat_id"))
            totals[uid] = totals.get(uid, 0) + int(slip.get("amount", 0) or 0)
    return totals


def get_slips_list(status: str | None = None) -> list:
    slips = load_all_slips()
    result = list(slips.values())
    if status:
        target_status = status.upper()
        result = [s for s in result if s.get("status") == target_status]
    # Sort newest first
    result.sort(key=lambda s: s.get("created_at", ""), reverse=True)
    return result


def get_slip_by_id(slip_id: str) -> dict | None:
    slips = load_all_slips()
    return slips.get(str(slip_id))


def pending_slips_for_agent() -> list:
    """PENDING slips enriched for the auto-review agent (Bot Update #19).

    ``tx_duplicate`` is computed across ALL recorded slips (any status):
    a transaction reference that appears on more than one slip means a
    re-used slip — the most common top-up fraud — even when the first
    copy was rejected. Oldest first, so the agent works the queue in
    arrival order.
    """
    slips = load_all_slips()
    tx_counts: dict = {}
    for s in slips.values():
        tx = (s.get("extracted_tx_id") or "").strip()
        if tx:
            tx_counts[tx] = tx_counts.get(tx, 0) + 1
    out = []
    for s in reversed(get_slips_list("PENDING")):
        tx = (s.get("extracted_tx_id") or "").strip()
        out.append({
            "id": s.get("id"),
            "chat_id": s.get("chat_id"),
            "username": s.get("username"),
            "amount": s.get("amount"),
            "method": s.get("method"),
            "file_id": s.get("file_id"),
            "image_url": s.get("image_url"),
            "extracted_tx_id": tx,
            "ocr_amount": s.get("ocr_amount"),
            "selected_amount": s.get("selected_amount"),
            "unverified_photo": bool(s.get("unverified_photo")),
            "tx_duplicate": bool(tx) and tx_counts.get(tx, 0) > 1,
            "created_at": s.get("created_at"),
        })
    return out


def load_audit_logs() -> list:
    logs = redis_get("admin_audit_logs")
    if logs is not None and isinstance(logs, list):
        return logs
    if os.path.exists(AUDIT_LOGS_FILE):
        try:
            with open(AUDIT_LOGS_FILE, "r") as f:
                return json.load(f)
        except Exception:
            pass
    return []


def record_audit_log(admin_id: str | int, action: str, target_type: str, target_id: str, details: dict | None = None):
    try:
        logs = redis_get("admin_audit_logs") or []
        if not logs and os.path.exists(AUDIT_LOGS_FILE):
            with open(AUDIT_LOGS_FILE, "r") as f:
                logs = json.load(f)
        now = myanmar_now()
        log_entry = {
            "admin_id": str(admin_id),
            "action": action,
            "target_type": target_type,
            "target_id": str(target_id),
            "details": details or {},
            "timestamp": now.strftime("%Y-%m-%d %H:%M:%S"),
        }
        logs.append(log_entry)
        redis_set("admin_audit_logs", logs)
        with open(AUDIT_LOGS_FILE, "w") as f:
            json.dump(logs, f, indent=2)
    except Exception:
        pass


def _sync_admin_messages(slip: dict, badge: str):
    """Append a verdict badge to the admin Telegram notifications and drop
    the Approve button, so a dashboard-side review is reflected in Telegram.

    Best-effort: messages may have been deleted or the bot removed from the
    chat, and slips recorded before this feature carry no message ids.
    """
    caption = slip.get("admin_caption") or ""
    for entry in slip.get("admin_messages") or []:
        try:
            bot.edit_message_caption(
                chat_id=entry["chat_id"],
                message_id=entry["message_id"],
                caption=f"{caption}\n\n{badge}" if caption else badge,
                parse_mode="HTML",
                reply_markup=None,
            )
        except Exception:
            try:
                bot.edit_message_text(
                    chat_id=entry["chat_id"],
                    message_id=entry["message_id"],
                    text=f"{caption}\n\n{badge}" if caption else badge,
                    parse_mode="HTML",
                    reply_markup=None,
                )
            except Exception:
                pass


def review_slip(slip_id: str, action: str, reviewed_by: str | int = "Admin", reason: str = "") -> dict:
    slips = load_all_slips()
    slip = slips.get(str(slip_id))
    if not slip:
        return {"success": False, "error": "Slip not found", "code": 404}

    current_status = slip.get("status", "PENDING")
    if current_status != "PENDING":
        return {
            "success": False,
            "error": f"Slip is already {current_status}",
            "status": current_status,
            "code": 400,
        }

    action_upper = action.upper()
    now = myanmar_now()
    chat_id = slip.get("chat_id")
    amount = slip.get("amount", 0)

    if action_upper == "APPROVE":
        slip["status"] = "APPROVED"
        slip["reviewed_by"] = str(reviewed_by)
        slip["reviewed_at"] = now.strftime("%Y-%m-%d %H:%M:%S")
        slip["review_reason"] = reason or "Payment approved"
        save_all_slips(slips)

        # 0. Reflect the verdict on the admin Telegram notifications
        _sync_admin_messages(slip, f"✅ <b>APPROVED (+{amount:,} MMK)</b>")

        # 1. Update user balance
        new_balance, _ = update_user_balance(chat_id, amount)

        # 1b. Loyalty points: a real customer payment earns points and flips the
        # redeem gate (has_topped_up). Single choke point → covers both the
        # Telegram approve button and the dashboard review. Best-effort: a points
        # failure must never block the money credit or the approval itself.
        pts_granted = 0
        try:
            from bot_app.config import points_enabled
            from bot_app.services.points import credit_points, topup_points_for

            if points_enabled():
                pts_granted, _pts_discarded, _pts_balance = credit_points(
                    chat_id, topup_points_for(amount), "topup"
                )
        except Exception:
            pts_granted = 0

        points_line = (
            f"🎁 ရရှိသော Points: <b>+{pts_granted:,}</b>\n\n" if pts_granted > 0 else ""
        )

        # 2. Send Telegram notification to user
        user_noti = (
            f"🎉 <b>ငွေဖြည့်သွင်းမှု အောင်မြင်ပါသည်!</b>\n\n"
            f"🧾 Top-Up ID: <code>{slip_id}</code>\n\n"
            f"💵 ဖြည့်သွင်းငွေ: <b>+{amount:,} MMK</b>\n\n"
            f"💳 လက်ရှိ Wallet လက်ကျန်ငွေ: <b>{new_balance:,} MMK</b>\n\n"
            f"{points_line}"
            f"'🛍️ Plan များဝယ်ရန်' Menu မှတစ်ဆင့် VPN Key များကို အချိန်မရွေး စိတ်ကြိုက် ချက်ချင်း ဝယ်ယူနိုင်ပါပြီခင်ဗျာ!"
        )
        try:
            bot.send_message(chat_id, user_noti, parse_mode="HTML")
        except Exception:
            pass

        # 3. Record audit log
        record_audit_log(
            admin_id=reviewed_by,
            action="SLIP_APPROVE",
            target_type="slip",
            target_id=slip_id,
            details={"chat_id": chat_id, "amount": amount, "new_balance": new_balance,
                     "points_granted": pts_granted},
        )

        # App inbox: mirror the Telegram DM into the H&E VPN app's
        # notification list (best-effort, never blocks the credit).
        try:
            from bot_app.services.app_notify import push_app_notification
            push_app_notification(
                chat_id, "topup_approved",
                "ငွေဖြည့်သွင်းမှု အောင်မြင်ပါပြီ 🎉",
                f"+{amount:,} MMK · လက်ကျန် {new_balance:,} MMK",
            )
        except Exception:
            pass

        return {"success": True, "action": "APPROVED", "new_balance": new_balance, "slip": slip}

    elif action_upper == "REJECT":
        slip["status"] = "REJECTED"
        slip["reviewed_by"] = str(reviewed_by)
        slip["reviewed_at"] = now.strftime("%Y-%m-%d %H:%M:%S")
        slip["review_reason"] = reason or "Payment rejected"
        save_all_slips(slips)

        # Reflect the verdict on the admin Telegram notifications
        reject_badge = f"❌ <b>REJECTED</b>\n{reason}" if reason else "❌ <b>REJECTED</b>"
        _sync_admin_messages(slip, reject_badge)

        # Send Telegram notification to user
        reject_msg = (
            f"⚠️ <b>ငွေလွှဲပြေစာအား ပယ်ချပါသည်</b>\n\n"
            f"🧾 Top-Up ID: <code>{slip_id}</code>\n"
            f"အကြောင်းပြချက်: {reason or 'ပြေစာအချက်အလက် မကိုက်ညီပါ'}\n\n"
            f"အကူအညီလိုအပ်ပါက Admin ထံ တိုက်ရိုက် ဆက်သွယ်ပေးပါခင်ဗျာ။"
        )
        try:
            bot.send_message(chat_id, reject_msg, parse_mode="HTML")
        except Exception:
            pass

        record_audit_log(
            admin_id=reviewed_by,
            action="SLIP_REJECT",
            target_type="slip",
            target_id=slip_id,
            details={"chat_id": chat_id, "reason": reason},
        )

        try:
            from bot_app.services.app_notify import push_app_notification
            push_app_notification(
                chat_id, "topup_rejected",
                "ငွေလွှဲပြေစာ ပယ်ချခံရပါသည် ⚠️",
                reason or "ပြေစာအချက်အလက် မကိုက်ညီပါ",
            )
        except Exception:
            pass

        return {"success": True, "action": "REJECTED", "slip": slip}

    return {"success": False, "error": f"Invalid action: {action}", "code": 400}
