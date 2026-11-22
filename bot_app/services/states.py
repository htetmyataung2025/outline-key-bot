"""Transient per-user/per-admin state flags.

Redis (Upstash) is the source of truth in production. When Redis is not
configured — local polling dev, CI/tests, or a deployment missing the KV
env vars — every helper falls back to a ``/tmp`` JSON file so state still
survives between the separate Telegram updates that make up one flow
(e.g. picking a top-up amount, then uploading the slip photo). Without
this fallback the amount selection was lost and the slip defaulted to the
minimum 1,000 Ks.
"""

import json
import os

from bot_app.storage.kv import redis_get, redis_set
from bot_app.storage.paths import (
    BROADCAST_STATE_FILE,
    CUSTOM_TOPUP_STATE_FILE,
    DEDUCT_STATE_FILE,
    MANUAL_DISPATCH_STATE_FILE,
    SLIP_GATE_STATE_FILE,
    REDEEM_STATE_FILE,
    RENEW_CHOICE_STATE_FILE,
    REPLACEMENT_STATE_FILE,
    SEARCH_STATE_FILE,
    TOPUP_STATE_FILE,
)


def _load_states(redis_key, file_path):
    data = redis_get(redis_key)
    if data is not None:
        return data
    try:
        if os.path.exists(file_path):
            with open(file_path, "r") as f:
                return json.load(f)
    except Exception:
        pass
    return {}


def _save_states(redis_key, file_path, states):
    redis_set(redis_key, states)
    try:
        with open(file_path, "w") as f:
            json.dump(states, f)
    except Exception:
        pass


def set_admin_deduct_state(admin_id, state_dict=None):
    states = _load_states("admin_deduct_state", DEDUCT_STATE_FILE)
    cid = str(admin_id)
    if not state_dict and cid not in states:
        return
    if state_dict:
        states[cid] = state_dict
    else:
        states.pop(cid, None)
    _save_states("admin_deduct_state", DEDUCT_STATE_FILE, states)

def get_admin_deduct_state(admin_id):
    states = _load_states("admin_deduct_state", DEDUCT_STATE_FILE)
    return states.get(str(admin_id))

# Slip-reject reason dialog state. Defined here as a module-level *_FILE
# constant (not in storage/paths.py) so the test suite's isolated_state
# sweep patches it like every other state file.
ADMIN_REJECT_STATE_FILE = os.path.join(os.path.dirname(DEDUCT_STATE_FILE), "admin_reject_state.json")

def set_admin_reject_state(admin_id, state_dict=None):
    states = _load_states("admin_reject_state", ADMIN_REJECT_STATE_FILE)
    cid = str(admin_id)
    if not state_dict and cid not in states:
        return
    if state_dict:
        states[cid] = state_dict
    else:
        states.pop(cid, None)
    _save_states("admin_reject_state", ADMIN_REJECT_STATE_FILE, states)

def get_admin_reject_state(admin_id):
    states = _load_states("admin_reject_state", ADMIN_REJECT_STATE_FILE)
    return states.get(str(admin_id))

def set_topup_state(chat_id, amount):
    states = _load_states("user_topup_state", TOPUP_STATE_FILE)
    cid = str(chat_id)
    if amount is None and cid not in states:
        return
    if amount is not None:
        states[cid] = amount
    else:
        states.pop(cid, None)
    _save_states("user_topup_state", TOPUP_STATE_FILE, states)

def get_topup_state(chat_id):
    states = _load_states("user_topup_state", TOPUP_STATE_FILE)
    return states.get(str(chat_id))

def set_custom_topup_state(chat_id, is_waiting=True):
    states = _load_states("user_custom_topup", CUSTOM_TOPUP_STATE_FILE)
    cid = str(chat_id)
    old = states.get(cid, False)
    if bool(old) == bool(is_waiting):
        return
    if is_waiting:
        states[cid] = True
    else:
        states.pop(cid, None)
    _save_states("user_custom_topup", CUSTOM_TOPUP_STATE_FILE, states)

def get_custom_topup_state(chat_id):
    states = _load_states("user_custom_topup", CUSTOM_TOPUP_STATE_FILE)
    return states.get(str(chat_id), False)

def set_renew_choice_state(chat_id, data_dict=None):
    states = _load_states("user_renew_choice", RENEW_CHOICE_STATE_FILE)
    cid = str(chat_id)
    if not data_dict and cid not in states:
        return
    if data_dict:
        states[cid] = data_dict
    else:
        states.pop(cid, None)
    _save_states("user_renew_choice", RENEW_CHOICE_STATE_FILE, states)

def get_renew_choice_state(chat_id):
    states = _load_states("user_renew_choice", RENEW_CHOICE_STATE_FILE)
    return states.get(str(chat_id))

# 💾 Persistent Key Storage System

def set_broadcast_state(chat_id, is_waiting=True):
    states = _load_states("admin_broadcast_state", BROADCAST_STATE_FILE)
    cid = str(chat_id)
    old = states.get(cid, False)
    if bool(old) == bool(is_waiting):
        return
    if is_waiting:
        states[cid] = True
    else:
        states.pop(cid, None)
    _save_states("admin_broadcast_state", BROADCAST_STATE_FILE, states)

def get_broadcast_state(chat_id):
    states = _load_states("admin_broadcast_state", BROADCAST_STATE_FILE)
    return states.get(str(chat_id), False)

def set_manual_dispatch_state(admin_id, order_info_dict=None):
    states = _load_states("admin_manual_dispatch_state", MANUAL_DISPATCH_STATE_FILE)
    cid = str(admin_id)
    if not order_info_dict and cid not in states:
        return
    if order_info_dict:
        states[cid] = order_info_dict
    else:
        states.pop(cid, None)
    _save_states("admin_manual_dispatch_state", MANUAL_DISPATCH_STATE_FILE, states)

def get_manual_dispatch_state(admin_id):
    states = _load_states("admin_manual_dispatch_state", MANUAL_DISPATCH_STATE_FILE)
    return states.get(str(admin_id))

def set_slip_gate_state(chat_id, gate_dict=None):
    """Bot Update #21: park a bounced slip photo (file_id + intake facts)
    so the customer's "this IS a real slip" button can forward it to the
    admin queue without re-uploading."""
    states = _load_states("slip_gate_state", SLIP_GATE_STATE_FILE)
    cid = str(chat_id)
    if not gate_dict and cid not in states:
        return
    if gate_dict:
        states[cid] = gate_dict
    else:
        states.pop(cid, None)
    _save_states("slip_gate_state", SLIP_GATE_STATE_FILE, states)

def get_slip_gate_state(chat_id):
    states = _load_states("slip_gate_state", SLIP_GATE_STATE_FILE)
    return states.get(str(chat_id))

def set_search_state(chat_id, is_searching=True):
    states = _load_states("admin_search_state", SEARCH_STATE_FILE)
    cid = str(chat_id)
    old = states.get(cid, False)
    if bool(old) == bool(is_searching):
        return
    if is_searching:
        states[cid] = True
    else:
        states.pop(cid, None)
    _save_states("admin_search_state", SEARCH_STATE_FILE, states)

def get_search_state(chat_id):
    states = _load_states("admin_search_state", SEARCH_STATE_FILE)
    return states.get(str(chat_id), False)

def set_redeem_state(chat_id, is_waiting=True):
    states = _load_states("user_redeem_state", REDEEM_STATE_FILE)
    cid = str(chat_id)
    old = states.get(cid, False)
    if bool(old) == bool(is_waiting):
        return
    if is_waiting:
        states[cid] = True
    else:
        states.pop(cid, None)
    _save_states("user_redeem_state", REDEEM_STATE_FILE, states)

def get_redeem_state(chat_id):
    states = _load_states("user_redeem_state", REDEEM_STATE_FILE)
    return states.get(str(chat_id), False)

def set_replacement_state(chat_id, is_waiting=True):
    states = _load_states("user_replacement_state", REPLACEMENT_STATE_FILE)
    cid = str(chat_id)
    old = states.get(cid, False)
    if bool(old) == bool(is_waiting):
        return
    if is_waiting:
        states[cid] = True
    else:
        states.pop(cid, None)
    _save_states("user_replacement_state", REPLACEMENT_STATE_FILE, states)

def get_replacement_state(chat_id):
    states = _load_states("user_replacement_state", REPLACEMENT_STATE_FILE)
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
