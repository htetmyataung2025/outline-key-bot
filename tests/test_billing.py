"""Wallet / bonus-credit accounting (file-backed, network-free)."""

import index

UID = 999000111


def test_topup_and_spend_main_balance(isolated_state):
    assert index.update_user_balance(UID, 5000)[0] == 5000
    main, bonus, total = index.get_user_balance_breakdown(UID)
    assert (main, bonus, total) == (5000, 0, 5000)

    assert index.update_user_balance(UID, -2000)[0] == 3000
    assert index.get_user_balance(UID) == 3000


def test_bonus_is_spent_before_main(isolated_state):
    index.update_user_balance(UID, 3000)  # main
    index.add_expiring_bonus_to_wallet(UID, 3000, 7)  # bonus
    assert index.get_user_balance(UID) == 6000

    index.update_user_balance(UID, -1000)
    main, bonus, total = index.get_user_balance_breakdown(UID)
    assert total == 5000
    assert bonus == 2000  # bonus absorbed the spend
    assert main == 3000  # main untouched


def test_expired_bonus_is_cleaned_up(isolated_state):
    index.add_expiring_bonus_to_wallet(UID, 3000, 7)
    data = index.load_expiring_credits()
    data[str(UID)][0]["expire_at"] = "2000-01-01 00:00:00"
    data[str(UID)][0]["remaining"] = 3000
    index.save_expiring_credits(data)

    main, bonus, total = index.get_user_balance_breakdown(UID)
    assert bonus == 0
    assert index.load_expiring_credits().get(str(UID), []) == []


def test_admin_has_unlimited_balance(isolated_state):
    admin_id = index.ADMIN_CHAT_IDS[0]
    assert index.get_user_balance(admin_id) == 999999999


def test_admin_deduct_main_only(isolated_state):
    index.update_user_balance(UID, 5000)
    deducted, m_bal, b_bal, final = index.admin_deduct_specific_funds(UID, 2000, "main")
    assert deducted == 2000
    assert (m_bal, final) == (3000, 3000)


def test_admin_deduct_never_goes_negative(isolated_state):
    index.update_user_balance(UID, 500)
    deducted, m_bal, b_bal, final = index.admin_deduct_specific_funds(UID, 9999, "all")
    assert final == 0 and m_bal == 0
