"""Wallet + expiring bonus credits + admin deductions."""

import json
import os
from datetime import datetime, timedelta

from app.config import ADMIN_CHAT_IDS
from app.storage.kv import redis_get, redis_set
from app.storage.paths import EXPIRING_CREDITS_FILE, USED_REDEEMERS_FILE, WALLET_FILE


# 💳 Advanced Wallet System
def load_all_wallets():
    data = redis_get("user_wallets_data")
    if data is not None:
        return data
    if os.path.exists(WALLET_FILE):
        try:
            with open(WALLET_FILE, 'r') as f:
                return json.load(f)
        except:
            pass
    return {}

def load_expiring_credits():
    data = redis_get("user_expiring_credits")
    if data is not None:
        return data
    if os.path.exists(EXPIRING_CREDITS_FILE):
        try:
            with open(EXPIRING_CREDITS_FILE, 'r') as f:
                return json.load(f)
        except:
            pass
    return {}

def save_expiring_credits(data):
    redis_set("user_expiring_credits", data)
    try:
        with open(EXPIRING_CREDITS_FILE, 'w') as f:
            json.dump(data, f)
    except:
        pass

def load_claimed_redeem_users():
    data = redis_get("global_claimed_redeemers")
    if data is not None:
        return data
    if os.path.exists(USED_REDEEMERS_FILE):
        try:
            with open(USED_REDEEMERS_FILE, 'r') as f:
                return json.load(f)
        except:
            pass
    return []

def save_claimed_redeem_user(chat_id):
    if str(chat_id) in [str(aid) for aid in ADMIN_CHAT_IDS]:
        return
    users = load_claimed_redeem_users()
    uid = str(chat_id)
    if uid not in users:
        users.append(uid)
        redis_set("global_claimed_redeemers", users)
        try:
            with open(USED_REDEEMERS_FILE, 'w') as f:
                json.dump(users, f)
        except:
            pass

def get_user_balance_breakdown(chat_id):
    uid = str(chat_id)
    wallets = load_all_wallets()
    main_bal = int(wallets.get(uid, 0))
    
    expiring_data = load_expiring_credits()
    user_grants = expiring_data.get(uid, [])
    
    now = datetime.utcnow() + timedelta(hours=6, minutes=30)
    valid_bonus = 0
    clean_grants = []
    
    for g in user_grants:
        try:
            exp_dt = datetime.strptime(g["expire_at"], "%Y-%m-%d %H:%M:%S")
            if exp_dt > now and g.get("remaining", 0) > 0:
                valid_bonus += int(g["remaining"])
                clean_grants.append(g)
        except:
            pass
            
    if len(clean_grants) != len(user_grants):
        expiring_data[uid] = clean_grants
        save_expiring_credits(expiring_data)
        
    return main_bal, valid_bonus, (main_bal + valid_bonus)

def get_user_balance(chat_id):
    if str(chat_id) in [str(aid) for aid in ADMIN_CHAT_IDS]:
        return 999999999
    _, _, total_bal = get_user_balance_breakdown(chat_id)
    return total_bal

def update_user_balance(chat_id, amount_delta):
    uid = str(chat_id)
    wallets = load_all_wallets()
    
    if amount_delta > 0:
        curr = int(wallets.get(uid, 0))
        new_bal = curr + amount_delta
        wallets[uid] = new_bal
        redis_set("user_wallets_data", wallets)
        try:
            with open(WALLET_FILE, 'w') as f:
                json.dump(wallets, f)
        except:
            pass
        return get_user_balance(chat_id), None

    needed_deduct = abs(amount_delta)
    expiring_data = load_expiring_credits()
    user_grants = expiring_data.get(uid, [])
    
    now = datetime.utcnow() + timedelta(hours=6, minutes=30)
    sorted_grants = []
    for g in user_grants:
        try:
            exp_dt = datetime.strptime(g["expire_at"], "%Y-%m-%d %H:%M:%S")
            if exp_dt > now and g.get("remaining", 0) > 0:
                sorted_grants.append(g)
        except:
            pass
            
    sorted_grants.sort(key=lambda x: x["expire_at"])
    used_bonus_days = []
    
    for g in sorted_grants:
        if needed_deduct <= 0:
            break
        rem = g.get("remaining", 0)
        if rem <= needed_deduct:
            needed_deduct -= rem
            g["remaining"] = 0
            used_bonus_days.append(g.get("days", 1))
        else:
            g["remaining"] -= needed_deduct
            needed_deduct = 0
            used_bonus_days.append(g.get("days", 1))
            
    expiring_data[uid] = [g for g in sorted_grants if g.get("remaining", 0) > 0]
    save_expiring_credits(expiring_data)
    
    if needed_deduct > 0:
        curr_main = int(wallets.get(uid, 0))
        new_main = max(0, curr_main - needed_deduct)
        wallets[uid] = new_main
        redis_set("user_wallets_data", wallets)
        try:
            with open(WALLET_FILE, 'w') as f:
                json.dump(wallets, f)
        except:
            pass
            
    min_bonus_days = min(used_bonus_days) if used_bonus_days else None
    return get_user_balance(chat_id), min_bonus_days

def add_expiring_bonus_to_wallet(chat_id, amount, validity_days):
    uid = str(chat_id)
    now = datetime.utcnow() + timedelta(hours=6, minutes=30)
    exp_dt = now + timedelta(days=validity_days)
    
    expiring_data = load_expiring_credits()
    if uid not in expiring_data:
        expiring_data[uid] = []
        
    grant = {
        "amount": int(amount),
        "remaining": int(amount),
        "days": int(validity_days),
        "expire_at": exp_dt.strftime("%Y-%m-%d %H:%M:%S"),
        "expire_disp": exp_dt.strftime("%d.%m.%Y")
    }
    expiring_data[uid].append(grant)
    save_expiring_credits(expiring_data)
    save_claimed_redeem_user(chat_id)
    return get_user_balance(chat_id), grant["expire_disp"]

def admin_deduct_specific_funds(target_chat_id, amount_to_deduct, deduct_type="all"):
    uid = str(target_chat_id)
    needed = int(amount_to_deduct)
    deducted = 0
    
    if deduct_type in ["bonus", "all"]:
        expiring_data = load_expiring_credits()
        user_grants = expiring_data.get(uid, [])
        for g in user_grants:
            if needed <= 0:
                break
            rem = g.get("remaining", 0)
            if rem <= needed:
                needed -= rem
                deducted += rem
                g["remaining"] = 0
            else:
                g["remaining"] -= needed
                deducted += needed
                needed = 0
        expiring_data[uid] = [g for g in user_grants if g.get("remaining", 0) > 0]
        save_expiring_credits(expiring_data)
        
    if deduct_type in ["main", "all"]:
        if deduct_type == "main":
            needed = int(amount_to_deduct)
        if needed > 0:
            wallets = load_all_wallets()
            curr_main = int(wallets.get(uid, 0))
            to_sub = min(curr_main, needed)
            wallets[uid] = curr_main - to_sub
            deducted += to_sub
            redis_set("user_wallets_data", wallets)
            try:
                with open(WALLET_FILE, 'w') as f:
                    json.dump(wallets, f)
            except:
                pass
                
    m_bal, b_bal, f_total = get_user_balance_breakdown(uid)
    return deducted, m_bal, b_bal, f_total
