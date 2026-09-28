"""Reply + inline keyboard factories."""

from telebot.types import (
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    KeyboardButton,
    ReplyKeyboardMarkup,
)

from bot_app.config import REQUIRED_CHANNEL, is_admin, points_enabled


def get_force_join_keyboard():
    markup = InlineKeyboardMarkup()
    channel_url = f"https://t.me/{REQUIRED_CHANNEL.replace('@', '')}"
    markup.add(InlineKeyboardButton("📢 Channel သို့ Join ရန်", url=channel_url))
    markup.add(InlineKeyboardButton("✅ Join ပြီးပါပြီ (Verify)", callback_data="verify_subscription"))
    return markup


# 📱 ပင်မ Menu Keyboard
def get_main_menu_keyboard(chat_id=None):
    markup = ReplyKeyboardMarkup(resize_keyboard=True, row_width=2)
    btn_buy = KeyboardButton("🛍️ Plan များဝယ်ရန်")
    btn_topup = KeyboardButton("💰 ငွေဖြည့်ရန်")
    btn_wallet = KeyboardButton("💳 လက်ကျန်ငွေ")
    btn_check = KeyboardButton("🧰 Data ပမာဏစစ်ရန်")
    btn_history = KeyboardButton("📇 ဝယ်ယူမှုမှတ်တမ်း")
    btn_replace = KeyboardButton("♻️ Key လဲရန်")
    btn_reward = KeyboardButton("🎁 Daily Reward")
    btn_leaderboard = KeyboardButton("🏆 Leaderboard")
    btn_admin = KeyboardButton("👨‍💻 Admin ဆက်သွယ်ရန်")
    btn_refresh = KeyboardButton("🤖 Bot Refresh")

    markup.add(btn_buy, btn_topup)
    markup.add(btn_wallet, btn_history)
    markup.add(btn_check, btn_replace)
    # The Daily Reward / Points system can be turned off from Settings without a
    # redeploy; when off, hide its entry point entirely.
    try:
        reward_on = points_enabled()
    except Exception:
        reward_on = True
    if reward_on:
        markup.add(btn_reward, btn_leaderboard)
    markup.add(btn_admin, btn_refresh)

    if chat_id and is_admin(chat_id):
        # Control Center opens from the chat menu button (bottom-left pill,
        # set in handlers/gate.py). A web_app row here duplicated it and
        # made the mobile keyboard tall enough to swallow the message input.
        btn_total_usage = KeyboardButton("📊 Total Data Usage")
        btn_monthly_income = KeyboardButton("💰 လစဉ် ဝင်ငွေ")
        btn_gen_code = KeyboardButton("🎟️ Gen RD Code")
        btn_search_user = KeyboardButton("🔍 Cus ရှာရန်")
        btn_deduct = KeyboardButton("💸 ငွေနှုတ်ရန်")
        btn_broadcast = KeyboardButton("📢 Broadcast စာပို့ရန်")
        markup.add(btn_total_usage, btn_gen_code)
        markup.add(btn_monthly_income, btn_search_user)
        markup.add(btn_deduct, btn_broadcast)

    return markup


def get_back_inline_keyboard():
    markup = InlineKeyboardMarkup()
    markup.add(InlineKeyboardButton("🔙 မူလ Menu သို့ ပြန်သွားရန်", callback_data="back_to_main"))
    return markup


def get_plan_keyboard():
    markup = InlineKeyboardMarkup()
    markup.row(InlineKeyboardButton("🌟 Starter (25 GB) - 1,000 Ks", callback_data="selectplan_starter"))
    markup.row(InlineKeyboardButton("💎 Basic (50 GB) - 2,000 Ks", callback_data="selectplan_basic"))
    markup.row(InlineKeyboardButton("⚡ Standard (75 GB) - 3,000 Ks", callback_data="selectplan_standard"))
    markup.row(InlineKeyboardButton("🔥 Premium (100 GB) - 4,000 Ks", callback_data="selectplan_premium"))
    markup.row(InlineKeyboardButton("👑 VIP (150 GB) - 5,000 Ks", callback_data="selectplan_vip"))
    markup.row(InlineKeyboardButton("🚀 Pro (200 GB) - 7,000 Ks", callback_data="selectplan_pro"))
    markup.row(InlineKeyboardButton("🌌 Ultimate VIP (500 GB) - 10,000 Ks", callback_data="selectplan_ultimate"))
    markup.row(InlineKeyboardButton("🔙 မူလ Menu သို့ ပြန်သွားရန်", callback_data="back_to_main"))
    return markup


def get_topup_amounts_keyboard():
    markup = InlineKeyboardMarkup()
    markup.row(
        InlineKeyboardButton("💵 1,000 Ks", callback_data="topup_amt_1000"),
        InlineKeyboardButton("💵 2,000 Ks", callback_data="topup_amt_2000")
    )
    markup.row(
        InlineKeyboardButton("💵 3,000 Ks", callback_data="topup_amt_3000"),
        InlineKeyboardButton("💵 5,000 Ks", callback_data="topup_amt_5000")
    )
    markup.row(
        InlineKeyboardButton("💵 10,000 Ks", callback_data="topup_amt_10000"),
        InlineKeyboardButton("💵 20,000 Ks", callback_data="topup_amt_20000")
    )
    markup.row(
        InlineKeyboardButton("✍️ စိတ်ကြိုက်ပမာဏ ရိုက်ထည့်မည်", callback_data="topup_amt_custom")
    )
    markup.row(InlineKeyboardButton("🔙 မူလ Menu သို့ ပြန်သွားရန်", callback_data="back_to_main"))
    return markup


def get_admin_rd_amounts_keyboard():
    markup = InlineKeyboardMarkup()
    markup.row(
        InlineKeyboardButton("💵 1,000 Ks", callback_data="adm_rdamt_1000"),
        InlineKeyboardButton("💵 3,000 Ks", callback_data="adm_rdamt_3000")
    )
    markup.row(
        InlineKeyboardButton("💵 5,000 Ks", callback_data="adm_rdamt_5000"),
        InlineKeyboardButton("💵 10,000 Ks", callback_data="adm_rdamt_10000")
    )
    markup.row(InlineKeyboardButton("🔙 မူလ Menu သို့ ပြန်သွားရန်", callback_data="back_to_main"))
    return markup


def get_admin_rd_mode_keyboard(amt):
    markup = InlineKeyboardMarkup()
    markup.row(
        InlineKeyboardButton(f"👤 တစ်ဦးတည်းသုံး ({int(amt):,} Ks)", callback_data=f"adm_rdmode_{amt}_single")
    )
    markup.row(
        InlineKeyboardButton("👥 လူအများခွဲသုံး (၁၀၀၀ ~ ၃၀၀၀ Ks စီ)", callback_data=f"adm_rdmode_{amt}_shared")
    )
    markup.row(InlineKeyboardButton("🔙 ငွေပမာဏ ပြန်ရွေးရန်", callback_data="back_to_gen_rd"))
    return markup


def get_admin_rd_days_keyboard(amt, mode):
    markup = InlineKeyboardMarkup()
    markup.row(
        InlineKeyboardButton("📅 1 ရက် သက်တမ်း", callback_data=f"adm_rddur_{amt}_{mode}_1"),
        InlineKeyboardButton("📅 3 ရက် သက်တမ်း", callback_data=f"adm_rddur_{amt}_{mode}_3")
    )
    markup.row(
        InlineKeyboardButton("📅 5 ရက် သက်တမ်း", callback_data=f"adm_rddur_{amt}_{mode}_5"),
        InlineKeyboardButton("📅 7 ရက် သက်တမ်း", callback_data=f"adm_rddur_{amt}_{mode}_7")
    )
    markup.row(InlineKeyboardButton("🔙 နောက်သို့ ပြန်သွားရန်", callback_data="back_to_gen_rd"))
    return markup


def get_admin_rd_count_keyboard(amt, mode, days):
    markup = InlineKeyboardMarkup()
    markup.row(
        InlineKeyboardButton("1 ခု", callback_data=f"adm_rdcnt_{amt}_{mode}_{days}_1"),
        InlineKeyboardButton("3 ခု", callback_data=f"adm_rdcnt_{amt}_{mode}_{days}_3")
    )
    markup.row(
        InlineKeyboardButton("5 ခု", callback_data=f"adm_rdcnt_{amt}_{mode}_{days}_5"),
        InlineKeyboardButton("10 ခု", callback_data=f"adm_rdcnt_{amt}_{mode}_{days}_10")
    )
    markup.row(InlineKeyboardButton("🔙 ရက်ပေါင်း ပြန်ရွေးရန်", callback_data=f"adm_rdmode_{amt}_{mode}"))
    return markup


def get_admin_deduct_type_keyboard():
    markup = InlineKeyboardMarkup()
    markup.row(
        InlineKeyboardButton("🎁 Redeem Bonus ငွေနှုတ်မည်", callback_data="adm_deduct_type_bonus")
    )
    markup.row(
        InlineKeyboardButton("💵 လက်ကျန်ငွေ ပမာဏနှုတ်မည်", callback_data="adm_deduct_type_main")
    )
    markup.row(
        InlineKeyboardButton("⚡ စုစုပေါင်း လက်ကျန်ငွေမှ အကုန်နှုတ်မည်", callback_data="adm_deduct_type_all")
    )
    markup.row(InlineKeyboardButton("🔙 မူလ Menu သို့ ပြန်သွားရန်", callback_data="back_to_main"))
    return markup
