"""Temp Files & Redis Fallback Configs (local JSON state paths)."""

import os

STATE_DIR = os.environ.get("LOCAL_STATE_DIR", "").strip() or "/tmp"
os.makedirs(STATE_DIR, exist_ok=True)


def _state_path(filename: str) -> str:
    return os.path.join(STATE_DIR, filename)


STATE_FILE = _state_path("user_plans.json")
MAPPING_FILE = _state_path("key_mappings.json")
REDEEM_FILE = _state_path("redeem_codes.json")
USED_REDEEMERS_FILE = _state_path("used_redeemers.json")
SEARCH_STATE_FILE = _state_path("admin_search_state.json")
REDEEM_STATE_FILE = _state_path("user_redeem_state.json")
REPLACEMENT_STATE_FILE = _state_path("user_replacement_state.json")
SALES_FILE = _state_path("sales_history.json")
ADMIN_MSG_MAP_FILE = _state_path("admin_msg_map.json")
REPLACEMENT_MSG_MAP_FILE = _state_path("replacement_msg_map.json")
BROADCAST_STATE_FILE = _state_path("admin_broadcast_state.json")
ALL_USERS_FILE = _state_path("all_users.json")
ORDERS_FILE = _state_path("orders_data.json")
KEY_ORDERS_FILE = _state_path("key_orders.json")
USER_HISTORY_FILE = _state_path("user_purchases.json")
PERSISTENT_KEYS_FILE = _state_path("persistent_keys.json")
WALLET_FILE = _state_path("user_wallets.json")
TOPUP_STATE_FILE = _state_path("user_topup_state.json")
CUSTOM_TOPUP_STATE_FILE = _state_path("user_custom_topup.json")
EXPIRING_CREDITS_FILE = _state_path("expiring_credits.json")
DEDUCT_STATE_FILE = _state_path("admin_deduct_state.json")
RENEW_CHOICE_STATE_FILE = _state_path("user_renew_choice.json")
MANUAL_DISPATCH_STATE_FILE = _state_path("admin_manual_dispatch_state.json")
SLIPS_FILE = _state_path("payment_slips.json")
SLIP_GATE_STATE_FILE = _state_path("slip_gate_state.json")
AUDIT_LOGS_FILE = _state_path("audit_logs.json")
DATA_VERSION_FILE = _state_path("admin_data_version.json")
USER_PROFILES_FILE = _state_path("user_profiles.json")
POINTS_FILE = _state_path("points_data.json")
SETTINGS_FILE = _state_path("system_settings.json")

