from scripts.migrate_wallets_and_points import (
    merge_admin_slips,
    merge_all_users,
    merge_global_claimed_redeemers,
    merge_points,
    merge_sales_history,
    merge_user_profiles,
    merge_user_purchases,
    merge_wallets,
)


def test_merge_wallets():
    old_w = {
        "user_old_only": 5000,
        "user_zero": 0,
        "user_both": 2000,
    }
    new_w = {
        "user_both": 1000,
        "user_new_only": 3000,
    }
    merged, audit = merge_wallets(old_w, new_w)

    assert merged["user_old_only"] == 5000
    assert merged["user_new_only"] == 3000
    # user_both gets summed (old + new)
    assert merged["user_both"] == 3000
    assert audit["user_both"] == {"old": 2000, "new": 1000, "final": 3000}


def test_merge_points():
    old_p = {
        "user_1": {
            "points": 5000,
            "lifetime_earned": 5000,
            "lifetime_claims": 50,
            "streak_days": 20,
            "last_claim_at": "2026-10-17 12:00:00",
            "has_topped_up": True,
        }
    }
    new_p = {
        "user_1": {
            "points": 25,
            "lifetime_earned": 25,
            "lifetime_claims": 1,
            "streak_days": 1,
            "last_claim_at": "2026-10-25 12:00:00",
            "has_topped_up": False,
        },
        "user_2": {
            "points": 100,
            "lifetime_earned": 100,
            "lifetime_claims": 2,
            "streak_days": 2,
            "last_claim_at": "2026-10-26 12:00:00",
            "has_topped_up": False,
        },
    }
    merged, audit = merge_points(old_p, new_p)

    # user_1 merged
    assert merged["user_1"]["points"] == 5025
    assert merged["user_1"]["lifetime_earned"] == 5025
    assert merged["user_1"]["lifetime_claims"] == 51
    assert merged["user_1"]["streak_days"] == 20
    assert merged["user_1"]["last_claim_at"] == "2026-10-25 12:00:00"
    assert merged["user_1"]["has_topped_up"] is True

    # user_2 added
    assert merged["user_2"]["points"] == 100
    assert audit["user_1"]["action"] == "summed"


def test_merge_sales_history():
    old_sales = [
        {"order_id": "ORD-1", "date": "2026-10-10", "timestamp": "12:00:00", "price": 1000},
        {"order_id": "ORD-2", "date": "2026-10-12", "timestamp": "12:00:00", "price": 2000},
    ]
    new_sales = [
        {"order_id": "ORD-2", "date": "2026-10-12", "timestamp": "12:00:00", "price": 2000, "updated": True},
        {"order_id": "ORD-3", "date": "2026-10-25", "timestamp": "12:00:00", "price": 3000},
    ]
    merged = merge_sales_history(old_sales, new_sales)
    assert len(merged) == 3
    assert merged[0]["order_id"] == "ORD-1"
    assert merged[1]["order_id"] == "ORD-2"
    assert merged[1].get("updated") is True
    assert merged[2]["order_id"] == "ORD-3"


def test_merge_admin_slips():
    old_slips = {
        "#100": {"id": "#100", "status": "APPROVED", "amount": 5000},
        "#101": {"id": "#101", "status": "PENDING", "amount": 2000},
    }
    new_slips = {
        "#101": {"id": "#101", "status": "APPROVED", "amount": 2000},
        "#102": {"id": "#102", "status": "APPROVED", "amount": 10000},
    }
    merged = merge_admin_slips(old_slips, new_slips)
    assert len(merged) == 3
    assert merged["#100"]["status"] == "APPROVED"
    assert merged["#101"]["status"] == "APPROVED"  # updated from new
    assert merged["#102"]["amount"] == 10000


def test_merge_user_purchases():
    old_up = {
        "123": [{"order_id": "ORD-1", "date": "2026-10-01"}]
    }
    new_up = {
        "123": [{"order_id": "ORD-2", "date": "2026-10-20"}],
        "456": [{"order_id": "ORD-3", "date": "2026-10-21"}],
    }
    merged = merge_user_purchases(old_up, new_up)
    assert len(merged["123"]) == 2
    assert len(merged["456"]) == 1


def test_merge_all_users_and_profiles():
    old_users = ["111", "222"]
    new_users = ["222", "333"]
    assert merge_all_users(old_users, new_users) == ["222", "333", "111"]

    old_prof = {"111": {"name": "User 1", "last_seen": "old"}}
    new_prof = {"111": {"last_seen": "new"}, "333": {"name": "User 3"}}
    merged_prof = merge_user_profiles(old_prof, new_prof)
    assert merged_prof["111"]["name"] == "User 1"
    assert merged_prof["111"]["last_seen"] == "new"
    assert merged_prof["333"]["name"] == "User 3"

    old_r = ["111", "222"]
    new_r = ["222", "333"]
    assert set(merge_global_claimed_redeemers(old_r, new_r)) == {"111", "222", "333"}
