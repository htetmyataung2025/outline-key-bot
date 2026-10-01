"""Plan browsing, wallet purchase, renew flow."""

import random
import string
from datetime import timedelta

from dateutil.relativedelta import relativedelta
from bot_app.timeutil import myanmar_now
from telebot.types import InlineKeyboardButton, InlineKeyboardMarkup

from bot_app.config import ADMIN_CHAT_IDS, PLANS
from bot_app.extensions import bot
from bot_app.handlers.common import send_force_join_message
from bot_app.helpers.callback_guard import is_callback_processed
from bot_app.helpers.deeplink import get_key_delivery_markup
from bot_app.keyboards import get_back_inline_keyboard, get_plan_keyboard
from bot_app.services.billing import get_user_balance, get_user_balance_breakdown, update_user_balance
from bot_app.services.orders import (
    save_key_mapping, save_sale_transaction, save_user_purchase_record,
)
from bot_app.services.outline import (
    create_outline_key, get_configured_servers, get_server_display_name,
    get_user_ultimate_keys, renew_or_create_unlimited_key, renew_specific_unlimited_key,
)
from bot_app.utils import is_user_subscribed


@bot.callback_query_handler(func=lambda call: call.data.startswith("selectplan_"))
def handle_select_plan(call):
    bot.answer_callback_query(call.id)
    chat_id = call.message.chat.id
    if not is_user_subscribed(chat_id):
        send_force_join_message(chat_id)
        return

    plan_code = call.data.replace("selectplan_", "")
    plan = PLANS.get(plan_code)

    if plan:
        amount = plan["price"]
        balance = get_user_balance(chat_id)
        is_admin = str(chat_id) in [str(aid) for aid in ADMIN_CHAT_IDS]
        
        _, bonus_bal, _ = get_user_balance_breakdown(chat_id)
        has_redeem_credit = (bonus_bal > 0) and not is_admin

        if plan_code == "ultimate" and not has_redeem_credit:
            user_keys = get_user_ultimate_keys(chat_id, "1")
            if len(user_keys) > 0:
                markup = InlineKeyboardMarkup()
                for idx, uk in enumerate(user_keys, 1):
                    markup.row(InlineKeyboardButton(f"♻️ Key #{idx} ({uk['name'][:25]}) သက်တမ်းတိုးမည်", callback_data=f"renew_choice_{plan_code}_1_{uk['id']}"))
                markup.row(InlineKeyboardButton("➕ Key အသစ် ထပ်ဝယ်မည်", callback_data=f"renew_choice_{plan_code}_1_new"))
                markup.row(InlineKeyboardButton("🔙 Plan များသို့ ပြန်သွားရန်", callback_data="back_to_plans"))
                markup.row(InlineKeyboardButton("🔙 မူလ Menu သို့ ပြန်သွားရန်", callback_data="back_to_main"))

                choice_text = (
                    f"🌌 <b>Ultimate VIP Plan ဝယ်ယူခြင်း</b>\n\n"
                    f"💡 လူကြီးမင်းတွင် လက်ရှိ Active ဖြစ်နေသော Ultimate VIP Key <b>({len(user_keys)} ခု)</b> ရှိနေသည်ကို တွေ့ရှိရပါသည်။\n\n"
                    f"👇 အောက်ပါတို့မှ <b>သက်တမ်းတိုးမည့် Key အဟောင်း</b> ကို ရွေးချယ်ပါ (သို့မဟုတ်) <b>ကီးအသစ် အစအဆုံး ဝယ်ယူရန်</b> ရွေးချယ်ပေးပါခင်ဗျာ:"
                )
                try:
                    bot.edit_message_text(choice_text, chat_id=chat_id, message_id=call.message.message_id, parse_mode="HTML", reply_markup=markup)
                except Exception:
                    bot.send_message(chat_id, choice_text, parse_mode="HTML", reply_markup=markup)
                return

        markup = InlineKeyboardMarkup()
        if balance >= amount or is_admin:
            if plan.get("manual"):
                markup.row(InlineKeyboardButton(f"💳 Wallet ဖြင့် တန်းဝယ်မည် ({amount:,} Ks)", callback_data=f"buywallet_{plan_code}_VIP"))
            elif plan_code == "ultimate" or has_redeem_credit:
                srv1_tag = "Redeem Credit" if has_redeem_credit else "Main Server"
                markup.row(InlineKeyboardButton(f"📡 {get_server_display_name('1')} 🇸🇬 ({srv1_tag}) ဖြင့် ဝယ်မည်", callback_data=f"buywallet_{plan_code}_1"))
            else:
                # One button per configured server — the Settings page is the
                # source of truth, so adding/removing servers there updates
                # this list without a redeploy.
                for srv in get_configured_servers():
                    sid = str(srv.get("id"))
                    markup.row(InlineKeyboardButton(f"📡 {get_server_display_name(sid)} ဖြင့် ဝယ်မည်", callback_data=f"buywallet_{plan_code}_{sid}"))
        else:
            shortfall = amount - balance
            markup.row(InlineKeyboardButton(f"💰 ငွေ {shortfall:,} Ks ထပ်ဖြည့်ရန်", callback_data="btn_open_topup"))
            
        markup.row(InlineKeyboardButton("🔙 Plan များသို့ ပြန်သွားရန်", callback_data="back_to_plans"))
        markup.row(InlineKeyboardButton("🔙 မူလ Menu သို့ ပြန်သွားရန်", callback_data="back_to_main"))

        balance_disp = "♾️" if is_admin else f"{balance:,} MMK"
        balance_status = "✅ ဝယ်ယူရန် လုံလောက်ပါသည်" if (balance >= amount or is_admin) else f"⚠️ ငွေမလုံလောက်ပါ (ထပ်ဖြည့်ရန်: {amount - balance:,} Ks)"
        
        server_notice = f"\n💡 <i>(Redeem ငွေ လက်ကျန်ပါရှိသဖြင့် {get_server_display_name('1')} မှသာ ထုတ်ပေးမည် ဖြစ်ပါသည်)</i>" if has_redeem_credit else ""

        text = (
            f"🛍️ <b>ဝယ်ယူမည့် Plan အချက်အလက်</b>\n\n"
            f"📮 <b>Plan:</b> {plan['name']}\n\n"
            f"🗃️ <b>Data:</b> {plan['data']} ( ၁လစာ )\n\n"
            f"💵 <b>ကျသင့်ငွေ:</b> {amount:,} MMK\n\n"
            f"━━━━━━━━━━━━━━━\n"
            f"💳 <b>လူကြီးမင်း၏ လက်ကျန်ငွေ:</b> <b>{balance_disp}</b>\n"
            f"အခြေအနေ: <b>{balance_status}</b>\n"
            f"━━━━━━━━━━━━━━━\n{server_notice}\n"
            f"👇 ဝယ်ယူလိုပါက အောက်ပါ ဆာဗာခလုတ်များမှ မိမိနှစ်သက်ရာကို ရွေးချယ်နှိပ်ပါခင်ဗျာ:"
        )
        try:
            bot.edit_message_text(text, chat_id=chat_id, message_id=call.message.message_id, parse_mode="HTML", reply_markup=markup)
        except Exception:
            bot.send_message(chat_id, text, parse_mode="HTML", reply_markup=markup)


@bot.callback_query_handler(func=lambda call: call.data.startswith("renew_choice_"))
def handle_renew_choice(call):
    bot.answer_callback_query(call.id)
    chat_id = call.message.chat.id
    parts = call.data.split("_")
    plan_code = parts[2]
    server_num = parts[3]
    choice_val = parts[4]

    plan = PLANS.get(plan_code)
    if not plan:
        return

    amount = plan["price"]
    balance = get_user_balance(chat_id)
    is_admin = str(chat_id) in [str(aid) for aid in ADMIN_CHAT_IDS]

    if not is_admin and balance < amount:
        bot.answer_callback_query(call.id, "❌ လက်ကျန်ငွေ မလုံလောက်ပါ။", show_alert=True)
        return

    order_id = "#" + "".join(random.choices(string.ascii_uppercase + string.digits, k=6))
    new_bal, used_bonus_days = update_user_balance(chat_id, -amount)
    
    chat_info = bot.get_chat(chat_id)
    user_first = chat_info.first_name if chat_info.first_name else ""
    user_last = chat_info.last_name if chat_info.last_name else ""
    user_name = f"{user_first} {user_last}".strip() or "HMA Customer"

    vpn_key = None
    key_name = None
    expire_date = None
    disp_gb = plan["data"]
    apply_days = None if is_admin else used_bonus_days

    if choice_val == "new":
        vpn_key, key_name, expire_date = create_outline_key(server_num, user_name, plan_info=plan, target_chat_id=chat_id, months_count=1, custom_days=apply_days, is_giveaway=False, order_id=order_id)
    else:
        today = myanmar_now()
        if apply_days:
            expire_date = (today + timedelta(days=apply_days)).strftime("%d.%m.%Y")
        else:
            expire_date = (today + relativedelta(months=1)).strftime("%d.%m.%Y")
        
        vpn_key, key_name, expire_date = renew_specific_unlimited_key(server_num, choice_val, months_count=1, custom_days=apply_days, order_id=order_id)

    if not vpn_key:
        update_user_balance(chat_id, amount)
        bot.send_message(chat_id, "❌ ဆာဗာလိုင်းမရသဖြင့် မဆောင်ရွက်နိုင်ပါ။ ငွေအား ပြန်လည်ထည့်သွင်းပေးထားပါသည်။", reply_markup=get_back_inline_keyboard())
        return

    save_sale_transaction(server_num, chat_id, plan_code, plan['name'], 1, amount, order_id=order_id)
    save_user_purchase_record(
        chat_id=chat_id,
        order_id=order_id,
        plan_name=plan['name'],
        disp_gb=disp_gb,
        months_count=1,
        price_str=f"{amount:,} Ks",
        server_num=server_num,
        expire_date=expire_date,
        vpn_key=vpn_key
    )

    clean_name = user_name.strip().lower()
    save_key_mapping(clean_name, chat_id)

    exp_info_text = f"⏰ <b>သက်တမ်းကုန်ဆုံးရက်:</b> {expire_date}"
    if apply_days:
        exp_info_text += f" <i>(Redeem Wallet ငွေအလိုက် {apply_days} ရက် သက်တမ်း)</i>"

    user_disp_bal = "♾️" if is_admin else f"{new_bal:,} MMK"
    success_text = (
        f"🎉 <b>ဝယ်ယူမှု အောင်မြင်ပါသည်ခင်ဗျာ!</b>\n\n"
        f"🧾 <b>Order ID:</b> <code>{order_id}</code>\n\n"
        f"🛍️ <b>Plan:</b> {plan['name']} ({disp_gb})\n\n"
        f"📡 <b>Server:</b> {get_server_display_name(server_num)}\n\n"
        f"{exp_info_text}\n\n"
        f"💳 <b>ကျန်ရှိသော လက်ကျန်ငွေ:</b> <code>{user_disp_bal}</code>\n\n"
        f"🔑 <b>လူကြီးမင်း၏ VPN Key:</b>\n\n"
        f"<code>{vpn_key}</code>\n\n"
        f"☝️ Key ကို တစ်ချက်နှိပ်ရုံဖြင့် Auto Copy ကူးနိုင်သလို၊ အောက်က Button များကို နှိပ်ပြီးလည်း တိုက်ရိုက်ထည့်သွင်း အသုံးပြုနိုင်ပါပြီခင်ဗျာ။"
    )
    try:
        bot.edit_message_text(success_text, chat_id=chat_id, message_id=call.message.message_id, parse_mode="HTML", reply_markup=get_key_delivery_markup(vpn_key))
    except Exception:
        bot.send_message(chat_id, success_text, parse_mode="HTML", reply_markup=get_key_delivery_markup(vpn_key))


@bot.callback_query_handler(func=lambda call: call.data.startswith("buywallet_"))
def handle_buy_with_wallet(call):
    bot.answer_callback_query(call.id)
    lock_key = f"buy_wallet_{call.message.message_id}_{call.data}"
    if is_callback_processed(lock_key):
        return

    parts = call.data.split("_")
    plan_code = parts[1]
    server_num = parts[2]
    plan = PLANS.get(plan_code)
    chat_id = call.message.chat.id

    if not plan:
        return

    amount = plan["price"]
    balance = get_user_balance(chat_id)
    is_admin = str(chat_id) in [str(aid) for aid in ADMIN_CHAT_IDS]

    if not is_admin and balance < amount:
        bot.answer_callback_query(call.id, "❌ လက်ကျန်ငွေ မလုံလောက်ပါ။ ကျေးဇူးပြု၍ ငွေအရင်ဖြည့်ပေးပါ။", show_alert=True)
        return

    order_id = "#" + "".join(random.choices(string.ascii_uppercase + string.digits, k=6))
    new_bal, used_bonus_days = update_user_balance(chat_id, -amount)
    
    chat_info = bot.get_chat(chat_id)
    user_first = chat_info.first_name if chat_info.first_name else ""
    user_last = chat_info.last_name if chat_info.last_name else ""
    user_name = f"{user_first} {user_last}".strip() or "HMA Customer"

    if plan.get("manual"):
        save_sale_transaction("VIP", chat_id, plan_code, plan["name"], plan.get("months", 1), amount, order_id=order_id)
        
        admin_alert = (
            f"⚡ <b>စိတ်ကြိုက်သုံး 5 Device Plan အော်ဒါအသစ် (ငွေပေးချေပြီး)</b>\n\n"
            f"🧾 Order ID: <code>{order_id}</code>\n"
            f"👤 ဝယ်ယူသူ: {user_name}\n"
            f"🆔 Chat ID: <code>{chat_id}</code>\n"
            f"🛍️ Plan: <b>{plan['name']}</b>\n"
            f"💵 ဖြတ်တောက်ပြီးငွေ: <b>{amount:,} MMK</b>\n\n"
            f"👇 အောက်ပါခလုတ်ကိုနှိပ်၍ Key အား ပေးပို့ပေးပါခင်ဗျာ:"
        )
        markup = InlineKeyboardMarkup()
        markup.add(InlineKeyboardButton("🔑 Send Key to Customer", callback_data=f"ask_send_key_{chat_id}_{order_id}"))
        
        for aid in ADMIN_CHAT_IDS:
            try:
                bot.send_message(aid, admin_alert, parse_mode="HTML", reply_markup=markup)
            except:
                pass

        user_disp_bal = "♾️" if is_admin else f"{new_bal:,} MMK"
        user_msg = (
            f"🎉 <b>အော်ဒါမှာယူမှု အောင်မြင်ပါသည်!</b>\n\n"
            f"🧾 <b>Order ID:</b> <code>{order_id}</code>\n\n"
            f"🛍️ <b>Plan:</b> {plan['name']}\n"
            f"💵 <b>ကျသင့်ငွေ:</b> -{amount:,} MMK\n"
            f"💳 <b>လက်ကျန်ငွေ:</b> {user_disp_bal}\n\n"
            f"💡 <i>ဤ Plan သည် စိတ်ကြိုက်သုံး Plan ဖြစ်သဖြင့် Admin မှ ခေတ္တအတွင်း Key အား ပြင်ဆင်၍ ပို့ပေးပါမည်ခင်ဗျာ။ စောင့်ဆိုင်းပေးပါရန် မေတ္တာရပ်ခံအပ်ပါသည်။</i>"
        )
        try:
            bot.edit_message_text(user_msg, chat_id=chat_id, message_id=call.message.message_id, parse_mode="HTML", reply_markup=get_back_inline_keyboard())
        except Exception:
            bot.send_message(chat_id, user_msg, parse_mode="HTML", reply_markup=get_back_inline_keyboard())
        return
    
    vpn_key = None
    key_name = None
    expire_date = None
    disp_gb = plan["data"]

    apply_days = None if is_admin else used_bonus_days

    if plan_code == "ultimate":
        vpn_key, key_name, expire_date, _ = renew_or_create_unlimited_key(server_num, user_name, chat_id, months_count=1, custom_days=apply_days, order_id=order_id)
    else:
        vpn_key, key_name, expire_date = create_outline_key(server_num, user_name, plan_info=plan, target_chat_id=chat_id, months_count=1, custom_days=apply_days, is_giveaway=False, order_id=order_id)

    if not vpn_key:
        update_user_balance(chat_id, amount)
        bot.send_message(chat_id, "❌ ဆာဗာလိုင်းမရသဖြင့် Key မွေးမရပါ။ ကျသင့်ငွေအား Wallet ထဲသို့ ပြန်လည် ထည့်သွင်းပေးထားပါသည်။", reply_markup=get_back_inline_keyboard())
        return

    save_sale_transaction(server_num, chat_id, plan_code, plan['name'], 1, amount, order_id=order_id)
    save_user_purchase_record(
        chat_id=chat_id,
        order_id=order_id,
        plan_name=plan['name'],
        disp_gb=disp_gb,
        months_count=1,
        price_str=f"{amount:,} Ks",
        server_num=server_num,
        expire_date=expire_date,
        vpn_key=vpn_key
    )

    clean_name = user_name.strip().lower()
    save_key_mapping(clean_name, chat_id)

    exp_info_text = f"⏰ <b>သက်တမ်းကုန်ဆုံးရက်:</b> {expire_date}"
    if apply_days:
        exp_info_text += f" <i>(Redeem Wallet ငွေအလိုက် {apply_days} ရက် သက်တမ်း)</i>"

    user_disp_bal = "♾️" if is_admin else f"{new_bal:,} MMK"
    success_text = (
        f"🎉 <b>ဝယ်ယူမှု အောင်မြင်ပါသည်ခင်ဗျာ!</b>\n\n"
        f"🧾 <b>Order ID:</b> <code>{order_id}</code>\n\n"
        f"🛍️ <b>Plan:</b> {plan['name']} ({disp_gb})\n\n"
        f"📡 <b>Server:</b> {get_server_display_name(server_num)}\n\n"
        f"{exp_info_text}\n\n"
        f"💳 <b>ကျန်ရှိသော လက်ကျန်ငွေ:</b> <code>{user_disp_bal}</code>\n\n"
        f"🔑 <b>လူကြီးမင်း၏ VPN Key:</b>\n\n"
        f"<code>{vpn_key}</code>\n\n"
        f"☝️ Key ကို တစ်ချက်နှိပ်ရုံဖြင့် Auto Copy ကူးနိုင်သလို၊ အောက်က Button များကို နှိပ်ပြီးလည်း တိုက်ရိုက်ထည့်သွင်း အသုံးပြုနိုင်ပါပြီခင်ဗျာ။"
    )
    try:
        bot.edit_message_text(success_text, chat_id=chat_id, message_id=call.message.message_id, parse_mode="HTML", reply_markup=get_key_delivery_markup(vpn_key))
    except Exception:
        bot.send_message(chat_id, success_text, parse_mode="HTML", reply_markup=get_key_delivery_markup(vpn_key))

    for aid in ADMIN_CHAT_IDS:
        try:
            bot.send_message(
                aid,
                f"🛍️ <b>Customer ကီးဝယ်ယူသွားပါပြီခင်ဗျာ။</b>\n\n"
                f"🧾 Order ID: <code>{order_id}</code>\n"
                f"👤 Customer: {user_name} (ID: <code>{chat_id}</code>)\n"
                f"🛍️ Plan: {plan['name']}\n"
                f"📡 Server: {get_server_display_name(server_num)}\n"
                f"💵 ရရှိငွေ: {amount:,} MMK\n"
                f"⏰ သက်တမ်း: {expire_date} ({f'Redeem ငွေဖြင့် {apply_days} ရက်' if apply_days else '၁လစာ'})",
                parse_mode="HTML"
            )
        except:
            pass


@bot.callback_query_handler(func=lambda call: call.data == "back_to_plans")
def handle_back_to_plans(call):
    bot.answer_callback_query(call.id)
    chat_id = call.message.chat.id
    bot.edit_message_text(
        "🧸 ကျေးဇူးပြု၍ ဝယ်ယူလိုသော VPN Plan ကို ရွေးချယ်ပေးပါခင်ဗျာ:",
        chat_id=chat_id,
        message_id=call.message.message_id,
        reply_markup=get_plan_keyboard()
    )

# 🔑 Admin Manual Key Send Callback

