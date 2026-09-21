"""Transient per-user/per-admin state flags (Redis-only, no files)."""

from bot_app.storage.kv import redis_get, redis_set


def set_admin_deduct_state(admin_id, state_dict=None):
    states = redis_get("admin_deduct_state") or {}
    if state_dict:
        states[str(admin_id)] = state_dict
    else:
        if str(admin_id) in states:
            del states[str(admin_id)]
    redis_set("admin_deduct_state", states)

def get_admin_deduct_state(admin_id):
    states = redis_get("admin_deduct_state") or {}
    return states.get(str(admin_id))

def set_topup_state(chat_id, amount):
    states = redis_get("user_topup_state") or {}
    if amount is not None:
        states[str(chat_id)] = amount
    else:
        if str(chat_id) in states:
            del states[str(chat_id)]
    redis_set("user_topup_state", states)

def get_topup_state(chat_id):
    states = redis_get("user_topup_state") or {}
    return states.get(str(chat_id))

def set_custom_topup_state(chat_id, is_waiting=True):
    states = redis_get("user_custom_topup") or {}
    states[str(chat_id)] = is_waiting
    redis_set("user_custom_topup", states)

def get_custom_topup_state(chat_id):
    states = redis_get("user_custom_topup") or {}
    return states.get(str(chat_id), False)

def set_renew_choice_state(chat_id, data_dict=None):
    states = redis_get("user_renew_choice") or {}
    if data_dict:
        states[str(chat_id)] = data_dict
    else:
        if str(chat_id) in states:
            del states[str(chat_id)]
    redis_set("user_renew_choice", states)

def get_renew_choice_state(chat_id):
    states = redis_get("user_renew_choice") or {}
    return states.get(str(chat_id))

# 💾 Persistent Key Storage System

def set_broadcast_state(chat_id, is_waiting=True):
    states = redis_get("admin_broadcast_state") or {}
    states[str(chat_id)] = is_waiting
    redis_set("admin_broadcast_state", states)

def get_broadcast_state(chat_id):
    states = redis_get("admin_broadcast_state") or {}
    return states.get(str(chat_id), False)

def set_manual_dispatch_state(admin_id, order_info_dict=None):
    states = redis_get("admin_manual_dispatch_state") or {}
    if order_info_dict:
        states[str(admin_id)] = order_info_dict
    else:
        if str(admin_id) in states:
            del states[str(admin_id)]
    redis_set("admin_manual_dispatch_state", states)

def get_manual_dispatch_state(admin_id):
    states = redis_get("admin_manual_dispatch_state") or {}
    return states.get(str(admin_id))

def set_search_state(chat_id, is_searching=True):
    states = redis_get("admin_search_state") or {}
    states[str(chat_id)] = is_searching
    redis_set("admin_search_state", states)

def get_search_state(chat_id):
    states = redis_get("admin_search_state") or {}
    return states.get(str(chat_id), False)

def set_redeem_state(chat_id, is_waiting=True):
    states = redis_get("user_redeem_state") or {}
    states[str(chat_id)] = is_waiting
    redis_set("user_redeem_state", states)

def get_redeem_state(chat_id):
    states = redis_get("user_redeem_state") or {}
    return states.get(str(chat_id), False)

def set_replacement_state(chat_id, is_waiting=True):
    states = redis_get("user_replacement_state") or {}
    states[str(chat_id)] = is_waiting
    redis_set("user_replacement_state", states)

def get_replacement_state(chat_id):
    states = redis_get("user_replacement_state") or {}
    return states.get(str(chat_id), False)

def clear_all_states(chat_id):
    set_search_state(chat_id, False)
    set_redeem_state(chat_id, False)
    set_replacement_state(chat_id, False)
    set_broadcast_state(chat_id, False)
    set_manual_dispatch_state(chat_id, None)
    set_topup_state(chat_id, None)
    set_custom_topup_state(chat_id, False)
    set_admin_deduct_state(chat_id, None)
    set_renew_choice_state(chat_id, None)
