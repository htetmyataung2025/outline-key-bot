"""Main menu dispatcher: reply-keyboard text router + state dialogs."""

import random
import re

from dateutil.relativedelta import relativedelta
from bot_app.timeutil import myanmar_now
from telebot.types import InlineKeyboardButton, InlineKeyboardMarkup

from bot_app.config import ADMIN_CHAT_IDS
from bot_app.extensions import bot
from bot_app.handlers.common import send_force_join_message
from bot_app.helpers.payment_text import get_payment_instruction_text
from bot_app.helpers.deeplink import get_key_delivery_markup, get_key_grid_markup
from bot_app.keyboards import (
    get_admin_deduct_type_keyboard, get_admin_rd_amounts_keyboard, get_back_inline_keyboard,
    get_main_menu_keyboard, get_plan_keyboard, get_topup_amounts_keyboard,
)
from bot_app.services.billing import (
    add_expiring_bonus_to_wallet, admin_deduct_specific_funds, get_user_balance_breakdown,
    load_expiring_credits,
)
from bot_app.services.orders import (
    get_order_id_for_key, get_user_combined_purchase_records, is_code_expired,
    load_all_users, load_redeem_codes, save_redeem_codes, save_user_id,
    save_user_purchase_record,
)
from bot_app.services.outline import (
    fetch_key_from_server, get_configured_servers, get_customer_summary_stats,
    get_server_display_name, get_servers_total_usage, search_users_by_query,
)
from bot_app.services.slips import record_audit_log, review_slip
from bot_app.services.registry import save_persistent_key
from bot_app.services.reports import get_monthly_revenue_report
from bot_app.services.profiles import touch_user
from bot_app.services.states import (
    clear_all_states, get_admin_deduct_state, get_admin_reject_state, get_broadcast_state, get_custom_topup_state,
    get_manual_dispatch_state, get_redeem_state, get_replacement_state, get_search_state,
    set_admin_deduct_state, set_admin_reject_state, set_broadcast_state, set_custom_topup_state,
    set_manual_dispatch_state, set_redeem_state, set_replacement_state, set_search_state,
    set_topup_state,
)
from bot_app.utils import bytes_to_gb, is_user_subscribed


@bot.message_handler(func=lambda message: message.content_type == "text", content_types=["text"])
def handle_all_messages(message):
    if not message.text:
        return
    input_value = message.text.strip()
    chat_id = message.chat.id
    save_user_id(chat_id)
    touch_user(message.from_user)

    if not is_user_subscribed(chat_id):
        send_force_join_message(chat_id)
        return

    # ✍️ စိတ်ကြိုက်ငွေပမာဏ ကီးဘုတ်မှ ရိုက်ထည့်ခြင်း Handler
    if get_custom_topup_state(chat_id):
        clean_amt_str = re.sub(r'[^\d]', '', input_value)
        if clean_amt_str and clean_amt_str.isdigit():
            amt = int(clean_amt_str)
            if amt < 500:
                bot.reply_to(message, "⚠️ အနည်းဆုံး ဖြည့်သွင်းငွေမှာ <b>500 Ks</b> ဖြစ်ပါသည်ခင်ဗျာ။ ကျေးဇူးပြု၍ ပြန်လည်ရိုက်ထည့်ပေးပါ:", parse_mode="HTML")
                return
            set_custom_topup_state(chat_id, False)
            set_topup_state(chat_id, amt)
            payment_text = get_payment_instruction_text(amt)
            markup = InlineKeyboardMarkup()
            markup.row(InlineKeyboardButton("🔙 ငွေပမာဏ ပြန်ရွေးရန်", callback_data="btn_open_topup"))
            markup.row(InlineKeyboardButton("🔙 မူလ Menu သို့ ပြန်သွားရန်", callback_data="back_to_main"))
            bot.send_message(chat_id, payment_text, parse_mode="HTML", reply_markup=markup)
            return
        else:
            bot.reply_to(message, "❌ ဂဏန်းသီးသန့် (ဥပမာ- <code>15000</code>) သာ ရိုက်ထည့်ပေးပါခင်ဗျာ:", parse_mode="HTML")
            return

    # ❌ Admin Slip Reject Reason Handler — the second step of the Telegram
    # reject flow started by the "❌ Reject" button (topup.handle_reject_topup_start).
    if str(chat_id) in [str(aid) for aid in ADMIN_CHAT_IDS]:
        reject_state = get_admin_reject_state(chat_id)
        if reject_state:
            topup_id = reject_state.get("slip_id")
            if input_value.strip() == "/cancel_reject":
                set_admin_reject_state(chat_id, None)
                bot.reply_to(message, "✅ Slip ပယ်ဖျက်ခြင်း ပယ်ဖျက်လိုက်ပါပြီခင်ဗျာ။", parse_mode="HTML")
                return
            set_admin_reject_state(chat_id, None)
            result = review_slip(topup_id, "REJECT", reviewed_by=message.from_user.id, reason=input_value.strip())
            if result.get("success"):
                bot.reply_to(
                    message,
                    f"❌ <b>Top-Up ID: <code>{topup_id}</code> ကို ပယ်ဖျက်ပြီးပါပြီ။</b>\n"
                    f"👤 Customer ထံ အသိပေးစာ ရောက်ရှိသွားပါမည်။",
                    parse_mode="HTML",
                )
            else:
                bot.reply_to(
                    message,
                    f"⚠️ ပယ်ဖျက်မရပါ — {result.get('error', 'unknown error')}",
                    parse_mode="HTML",
                )
            return

    # 💸 Admin ငွေနှုတ်သည့် Dialog State Handler
    if str(chat_id) in [str(aid) for aid in ADMIN_CHAT_IDS]:
        deduct_state = get_admin_deduct_state(chat_id)
        if deduct_state:
            step = deduct_state.get("step")
            dtype = deduct_state.get("type", "all")
            
            # Step 1: Customer ID လက်ခံခြင်း
            if step == "ask_user":
                target_user_id = input_value.strip()
                if not target_user_id.isdigit():
                    bot.reply_to(message, "❌ Customer ၏ Telegram Chat ID ကို ဂဏန်းသီးသန့်သာ ရိုက်ထည့်ပါခင်ဗျာ:")
                    return
                deduct_state["target_user_id"] = target_user_id
                deduct_state["step"] = "ask_amount"
                set_admin_deduct_state(chat_id, deduct_state)

                m_b, b_b, t_b = get_user_balance_breakdown(target_user_id)
                bot.reply_to(
                    message,
                    f"👤 <b>Customer ID:</b> <code>{target_user_id}</code>\n"
                    f"💵 လက်ကျန်ငွေ ပမာဏ: <b>{m_b:,} Ks</b>\n"
                    f"🎁 Redeem Bonus: <b>{b_b:,} Ks</b>\n"
                    f"💎 စုစုပေါင်းလက်ကျန်: <b>{t_b:,} Ks</b>\n\n"
                    f"👇 <b>နှုတ်ယူလိုသော ငွေပမာဏ</b> ကို ဂဏန်းသီးသန့် ရိုက်ပို့ပေးပါခင်ဗျာ:",
                    parse_mode="HTML"
                )
                return

            # Step 2: ငွေပမာဏ လက်ခံပြီး အမှန်တကယ် နှုတ်ယူခြင်း
            elif step == "ask_amount":
                clean_amt = re.sub(r'[^\d]', '', input_value)
                if not clean_amt.isdigit() or int(clean_amt) <= 0:
                    bot.reply_to(message, "❌ မှန်ကန်သော ငွေပမာဏကို ဂဏန်းသီးသန့် ရိုက်ထည့်ပါခင်ဗျာ:")
                    return

                target_user_id = deduct_state.get("target_user_id")
                amt_to_deduct = int(clean_amt)
                set_admin_deduct_state(chat_id, None)

                deducted, m_bal, b_bal, final_bal = admin_deduct_specific_funds(target_user_id, amt_to_deduct, deduct_type=dtype)

                record_audit_log(
                    message.from_user.id,
                    "BALANCE_DEDUCT",
                    "user",
                    target_user_id,
                    {"amount": deducted, "new_balance": final_bal, "requested": amt_to_deduct, "via": "telegram"},
                )

                bot.reply_to(
                    message,
                    f"✅ <b>ငွေပြန်နှုတ်ခြင်း အောင်မြင်ပါသည်!</b>\n\n"
                    f"👤 Customer ID: <code>{target_user_id}</code>\n"
                    f"💵 နှုတ်ယူငွေ: <b>-{deducted:,} MMK</b>\n"
                    f"💳 User ၏ လက်ရှိ ကျန်ငွေ: <b>{final_bal:,} MMK</b> (လက်ကျန်ငွေ ပမာဏ: {m_bal:,} Ks | Redeem: {b_bal:,} Ks)",
                    parse_mode="HTML"
                )

                try:
                    bot.send_message(
                        target_user_id,
                        f"⚠️ <b>အသိပေးချက်:</b>\n\nလူကြီးမင်း၏ Wallet ထဲမှ (<b>-{deducted:,} MMK</b>) အား Admin မှ ပြန်လည်နှုတ်ယူလိုက်ပါသည်ခင်ဗျာ။\n\n💳 လက်ရှိ သုံးနိုင်သော စုစုပေါင်း လက်ကျန်ငွေ: <b>{final_bal:,} MMK</b>",
                        parse_mode="HTML"
                    )
                except:
                    pass
                return

    # 🔑 Admin Manual Dispatch State Handler
    if str(chat_id) in [str(aid) for aid in ADMIN_CHAT_IDS]:
        manual_state = get_manual_dispatch_state(chat_id)
        if manual_state:
            set_manual_dispatch_state(chat_id, None)
            target_user_id = manual_state.get("target_chat_id")
            order_id = manual_state.get("order_id")
            plan_name = manual_state.get("plan_name", "စိတ်ကြိုက်သုံး Plan (5 Device)")
            disp_gb = manual_state.get("disp_gb", "Unlimited Data (5 Device)")
            months_count = manual_state.get("months", 1)

            today = myanmar_now()
            expire_date = (today + relativedelta(months=months_count)).strftime("%d.%m.%Y")

            save_user_purchase_record(
                chat_id=target_user_id,
                order_id=order_id,
                plan_name=plan_name,
                disp_gb=disp_gb,
                months_count=months_count,
                price_str="-",
                server_num="VIP",
                expire_date=expire_date,
                vpn_key=input_value
            )
            save_persistent_key("VIP", f"custom_{order_id}", f"{plan_name} ({target_user_id}) {expire_date}", input_value, None, order_id, target_user_id)

            success_message = (
                f"🎉 <b>လူကြီးမင်း၏ VPN Key ရောက်ရှိပါပြီခင်ဗျာ!</b>\n\n"
                f"🧾 <b>Order ID:</b> <code>{order_id}</code>\n\n"
                f"🛍️ <b>Plan:</b> {plan_name} ({disp_gb})\n\n"
                f"⏰ <b>သက်တမ်းကုန်ဆုံးရက်:</b> {expire_date}\n\n"
                f"🔑 <b>လူကြီးမင်း၏ VPN Key:</b>\n\n"
                f"<code>{input_value}</code>\n\n"
                f"☝️ Key ကို တစ်ချက်နှိပ်ရုံဖြင့် Auto Copy ကူးနိုင်သလို၊ အောက်က Button များကို နှိပ်ပြီးလည်း တိုက်ရိုက်ထည့်သွင်း အသုံးပြုနိုင်ပါပြီခင်ဗျာ။"
            )
            try:
                bot.send_message(target_user_id, success_message, parse_mode="HTML", reply_markup=get_key_delivery_markup(input_value))
                bot.reply_to(message, f"✅ <b>Order ID: {order_id} အတွက် Customer ထံသို့ Key အား အောင်မြင်စွာ ပို့ပေးလိုက်ပါပြီခင်ဗျာ။</b>", parse_mode="HTML")
            except Exception as e:
                bot.reply_to(message, f"❌ Customer ထံ ပို့မရပါ - {str(e)}")
            return

    # 📢 Admin Broadcast Text
    if str(chat_id) in [str(aid) for aid in ADMIN_CHAT_IDS] and get_broadcast_state(chat_id):
        set_broadcast_state(chat_id, False)
        all_users = load_all_users()
        success_count = 0
        bot.send_message(chat_id, f"⏳ Broadcast စာအား User စုစုပေါင်း ({len(all_users)}) ဆီ အကုန် ပို့ပေးနေပါသည်...")
        for uid in all_users:
            if str(uid) in [str(aid) for aid in ADMIN_CHAT_IDS]: continue
            try:
                bot.send_message(uid, input_value, parse_mode="HTML")
                success_count += 1
            except:
                pass
        bot.send_message(chat_id, f"✅ <b>Broadcast ပို့ပြီးပါပြီ!</b>\n\nရောက်ရှိသူ: <b>{success_count} / {len(all_users)}</b>", parse_mode="HTML")
        record_audit_log(
            message.from_user.id,
            "BROADCAST",
            "broadcast",
            str(len(all_users)),
            {"message_type": "text", "sent": success_count, "recipients": len(all_users)},
        )
        return

    # 🛍️ Plan များဝယ်ရန်
    if input_value in ["🛍️ Plan များဝယ်ရန်", "Plan များဝယ်ရန်", "🛍️ Plan များ ကြည့်ရန်", "Plan များ ကြည့်ရန်"]:
        clear_all_states(chat_id)
        bot.send_message(chat_id, "🧸 လူကြီးမင်း ဝယ်ယူလိုသော VPN Plan ကို ရွေးချယ်ပေးပါခင်ဗျာ:", reply_markup=get_plan_keyboard())
        return

    # 💰 ငွေဖြည့်ရန်
    if input_value in ["💰 ငွေဖြည့်ရန်", "ငွေဖြည့်ရန်", "💰 ငွေဖြည့်ရန် (Top-Up)"]:
        clear_all_states(chat_id)
        bot.send_message(
            chat_id,
            "💰 <b>Wallet ထဲသို့ ဖြည့်သွင်းလိုသော ငွေပမာဏကို ရွေးချယ်ပေးပါ:</b>\n\n"
            "💡 <i>ငွေကြိုတင် ဖြည့်ထားခြင်းဖြင့် Plan များကို ၂၄ နာရီလုံး Bot မှ ချက်ချင်း Auto ထုတ်ယူနိုင်ပါသည်ခင်ဗျာ။</i>",
            parse_mode="HTML",
            reply_markup=get_topup_amounts_keyboard()
        )
        return

    # 💳 လက်ကျန်ငွေ
    if input_value in ["💳 လက်ကျန်ငွေ", "လက်ကျန်ငွေ", "💳 လက်ကျန်ငွေ / Wallet"]:
        clear_all_states(chat_id)
        is_admin = str(chat_id) in [str(aid) for aid in ADMIN_CHAT_IDS]
        main_bal, bonus_bal, total_bal = get_user_balance_breakdown(chat_id)
        
        bonus_detail_str = ""
        if bonus_bal > 0:
            expiring_data = load_expiring_credits().get(str(chat_id), [])
            lines = []
            for g in expiring_data:
                if g.get("remaining", 0) > 0:
                    lines.append(f"   • <b>+{g['remaining']:,} Ks</b> (သက်တမ်းကုန်မည့်ရက်: <code>{g['expire_disp']}</code>)")
            if lines:
                bonus_detail_str = "\n⏳ <b>ရက်စွဲပါ လက်ကျန်ငွေများ:</b>\n" + "\n".join(lines) + "\n"

        crown = " 👑" if is_admin else ""
        main_bal_disp = "♾️" if is_admin else f"{main_bal:,} MMK"
        total_bal_disp = "♾️" if is_admin else f"{total_bal:,} MMK"

        user_first = message.from_user.first_name if message.from_user.first_name else ""
        user_last = message.from_user.last_name if message.from_user.last_name else ""
        full_name = f"{user_first} {user_last}".strip() or "HMA User"

        wallet_text = (
            f"💳 <b>လူကြီးမင်း၏ Wallet အချက်အလက်</b>\n\n"
            f"👤 <b>အသုံးပြုသူ:</b> {full_name}{crown}\n"
            f"🆔 <b>Chat ID:</b> <code>{chat_id}</code>\n\n"
            f"💵 <b>လက်ကျန်ငွေ ပမာဏ:</b> {main_bal_disp}\n"
            f"🎁 <b>Redeem လက်ကျန်ငွေ:</b> {bonus_bal:,} MMK\n"
            f"{bonus_detail_str}"
            f"━━━━━━━━━━━━━━━\n"
            f"💎 <b>စုစုပေါင်း သုံးနိုင်သောငွေ:</b> <b>{total_bal_disp}</b>\n"
            f"━━━━━━━━━━━━━━━\n\n"
        )
        markup = InlineKeyboardMarkup()
        markup.row(
            InlineKeyboardButton("💰 ငွေဖြည့်ရန်", callback_data="btn_open_topup"),
            InlineKeyboardButton("🎟️ Redeem Code သုံးမည်", callback_data="btn_open_redeem")
        )
        markup.row(InlineKeyboardButton("🔙 မူလ Menu သို့ ပြန်သွားရန်", callback_data="back_to_main"))
        bot.send_message(chat_id, wallet_text, parse_mode="HTML", reply_markup=markup)
        return

    # 🧰 Data ပမာဏစစ်ရန်
    if input_value in ["🧰 Data ပမာဏစစ်ရန်", "Data ပမာဏစစ်ရန်", "🧰 Data လက်ကျန်စစ်ရန်", "🧰 Data Usage စစ်ရန်"]:
        clear_all_states(chat_id)
        check_guide = (
            "👇 <b>လက်ကျန် Data စစ်ဆေးရန်:</b>\n\n"
            "ဝယ်ယူထားသော VPN Key Link (<code>ss://...</code>) အား ဤ Chat ထဲသို့ Paste ချ၍ ပေးပို့စစ်ဆေးနိုင်ပါသည်ခင်ဗျာ။"
        )
        bot.send_message(chat_id, check_guide, parse_mode="HTML", reply_markup=get_back_inline_keyboard())
        return

    # 📇 ဝယ်ယူမှုမှတ်တမ်း
    if input_value in ["📇 ဝယ်ယူမှုမှတ်တမ်း", "ဝယ်ယူမှုမှတ်တမ်း"]:
        clear_all_states(chat_id)
        records = get_user_combined_purchase_records(chat_id)
        if not records:
            empty_msg = (
                "📇 <b>လူကြီးမင်း၏ ဝယ်ယူမှုမှတ်တမ်း</b>\n\n"
                "<i>လက်ရှိတွင် ဝယ်ယူထားသော မှတ်တမ်း မရှိသေးပါခင်ဗျာ။ '🛍️ Plan များဝယ်ရန်' မှတစ်ဆင့် စတင်ဝယ်ယူနိုင်ပါသည်ခင်ဗျာ။</i>"
            )
            bot.send_message(chat_id, empty_msg, parse_mode="HTML", reply_markup=get_back_inline_keyboard())
            return

        history_texts = []
        for idx, rec in enumerate(reversed(records), 1):
            sid = str(rec.get('server', '1'))
            srv_name = "VIP Server 🇸🇬" if sid == "VIP" else get_server_display_name(sid)
            vpn_k = rec.get('vpn_key', '')
            key_block = f"<code>{vpn_k}</code>" if vpn_k != "N/A" else "<i>(Key လဲလှယ်ရန် Menu ရှိ '♻️ Key လဲရန်' အသုံးပြုနိုင်ပါသည်)</i>"

            item_txt = (
                f"<b>#{idx} | ဝယ်ယူမှု အချက်အလက်</b>\n\n"
                f"🧾 <b>Order ID:</b> <code>{rec.get('order_id', 'N/A')}</code>\n\n"
                f"📅 <b>အချိန်:</b> <code>{rec.get('timestamp', 'N/A')}</code>\n\n"
                f"🛍️ <b>Plan:</b> {rec.get('plan_name', '')} ({rec.get('disp_gb', '')})\n\n"
                f"📡 <b>Server:</b> {srv_name}\n\n"
                f"⏰ <b>သက်တမ်းကုန်ရက်:</b> <code>{rec.get('expire_date', 'N/A')}</code>\n\n"
                f"🔑 <b>VPN Key:</b>\n\n"
                f"{key_block}"
            )
            history_texts.append(item_txt)

        final_history_msg = (
            f"📇 <b>လူကြီးမင်း ဝယ်ယူခဲ့သော VPN Key များ ({len(records)} ခု):</b>\n\n" +
            "\n\n━━━━━━━━━━━━━━━━━\n\n".join(history_texts) +
            "\n\n☝️ <i>Key ကို တစ်ချက်နှိပ်ရုံဖြင့် Auto Copy ကူးနိုင်သလို၊ အောက်က Button များကို နှိပ်ပြီးလည်း တိုက်ရိုက်ထည့်သွင်း အသုံးပြုနိုင်ပါပြီခင်ဗျာ။</i>"
        )

        # Neat 2-column app grid (Outline | V2Box / INCY | မူလ Menu) — each
        # button relays through the /go page into the app; keys not in the
        # registry are skipped automatically.
        key_urls = [rec.get('vpn_key') for rec in reversed(records)
                    if rec.get('vpn_key') and rec.get('vpn_key') != "N/A"]
        history_markup = get_key_grid_markup(key_urls)

        if len(final_history_msg) > 4000:
            pieces = [final_history_msg[i:i+4000] for i in range(0, len(final_history_msg), 4000)]
            for piece in pieces[:-1]:
                bot.send_message(chat_id, piece, parse_mode="HTML")
            bot.send_message(chat_id, pieces[-1], parse_mode="HTML", reply_markup=history_markup)
        else:
            bot.send_message(chat_id, final_history_msg, parse_mode="HTML", reply_markup=history_markup)
        return

    # ♻️ Key လဲရန်
    if input_value in ["♻️ Key လဲရန်", "Key လဲရန်"]:
        clear_all_states(chat_id)
        set_replacement_state(chat_id, True)
        replace_guide = (
            "♻️ <b>VPN Key အစားထိုး လဲလှယ်ရန်:</b>\n\n"
            "👇 အဆင်မပြေ ဖြစ်နေသော VPN Key (<code>ss://...</code>) ကို ဒီ Chat ထဲသို့ Paste ချ ပေးပို့ပေးပါခင်ဗျာ။\n"
            "<i>(Bot မှ ကျန်ရှိသော ရက်/Data များကို စစ်ဆေး၍ Admin ထံ အစားထိုး တောင်းဆိုပေးပါမည်။)</i>"
        )
        bot.send_message(chat_id, replace_guide, parse_mode="HTML", reply_markup=get_back_inline_keyboard())
        return

    # 👨‍💻 Admin ဆက်သွယ်ရန်
    if input_value in ["👨‍💻 Admin ဆက်သွယ်ရန်", "Admin ဆက်သွယ်ရန်", "👨‍💻 Admin သို့ ဆက်သွယ်ရန်"]:
        clear_all_states(chat_id)
        admin_link_markup = InlineKeyboardMarkup()
        admin_link_markup.add(InlineKeyboardButton("💬 စာပို့ရန် နှိပ်ပါ", url="https://t.me/H_M_A_2026"))
        admin_link_markup.add(InlineKeyboardButton("🔙 မူလ Menu သို့ ပြန်သွားရန်", callback_data="back_to_main"))
        bot.send_message(chat_id, "👇 အောက်ကခလုတ်ကိုနှိပ်ပြီး Admin ထံ တိုက်ရိုက်စာပို့ ဆက်သွယ်နိုင်ပါပြီဗျာ။", reply_markup=admin_link_markup)
        return

    # 🎁 Daily Reward (Points)
    if input_value in ["🎁 Daily Reward", "Daily Reward"]:
        clear_all_states(chat_id)
        from bot_app.config import points_enabled

        if not points_enabled():
            bot.send_message(
                chat_id,
                "🎁 <b>Daily Reward စနစ်ကို ယာယီ ပိတ်ထားပါသည်။</b>\n\n"
                "မကြာမီ ပြန်လည် ဖွင့်လှစ်ပေးပါမည်ခင်ဗျာ။",
                parse_mode="HTML",
            )
            return
        from bot_app.handlers.points import build_reward_view

        text, markup = build_reward_view(chat_id)
        bot.send_message(chat_id, text, parse_mode="HTML", reply_markup=markup)
        return

    # 🏆 Points Leaderboard
    if input_value in ["🏆 Leaderboard", "🏆 Points Leaderboard", "Leaderboard"]:
        clear_all_states(chat_id)
        from bot_app.config import points_enabled

        if not points_enabled():
            bot.send_message(
                chat_id,
                "🏆 <b>Leaderboard ကို ယာယီ ပိတ်ထားပါသည်။</b>\n\n"
                "မကြာမီ ပြန်လည် ဖွင့်လှစ်ပေးပါမည်ခင်ဗျာ။",
                parse_mode="HTML",
            )
            return
        from bot_app.handlers.leaderboard import build_leaderboard_view

        text, markup = build_leaderboard_view(chat_id, "7d")
        bot.send_message(chat_id, text, parse_mode="HTML", reply_markup=markup)
        return

    # 🎟️ Wallet Amount Redeem Code စစ်ဆေးခြင်း Handler
    if get_redeem_state(chat_id):
        set_redeem_state(chat_id, False)
        
        is_admin = str(chat_id) in [str(aid) for aid in ADMIN_CHAT_IDS]
        if not is_admin:
            _, bonus_bal, _ = get_user_balance_breakdown(chat_id)
            if bonus_bal > 0:
                bot.send_message(
                    chat_id,
                    f"⚠️ <b>ခွင့်လွှတ်ပါခင်ဗျာ၊ လူကြီးမင်းတွင် လက်ရှိ အသုံးပြုနိုင်သော Redeem Bonus လက်ကျန်ငွေ ({bonus_bal:,} MMK) ရှိနေဆဲ ဖြစ်ပါသဖြင့် နောက်ထပ် Code အသစ်ကို ထပ်မံ ရယူခွင့် မရှိသေးပါခင်ဗျာ။</b>\n\n"
                    f"💡 <i>အဆိုပါငွေဖြင့် Plan ဝယ်ယူအသုံးပြုပြီးမှ (သို့မဟုတ် ရက်စေ့ကုန်ဆုံးသွားမှ) သာ နောက်ထပ် Code အသစ်ကို ရယူနိုင်ပါမည်ခင်ဗျာ။</i>",
                    parse_mode="HTML",
                    reply_markup=get_back_inline_keyboard()
                )
                return

        codes = load_redeem_codes()
        code_input = input_value.strip().lower()
        
        matched_code_key = None
        for c_k in codes.keys():
            if c_k.strip().lower() == code_input:
                matched_code_key = c_k
                break

        if matched_code_key:
            code_info = codes[matched_code_key]
            if is_code_expired(code_info):
                bot.send_message(chat_id, f"❌ <b>ဤ Code ၏ သက်တမ်း ကုန်ဆုံးသွားပါပြီ။</b>\n\n🎟️ <code>{matched_code_key}</code> (ကုန်ဆုံးရက်: {code_info.get('expires_at')})", parse_mode="HTML", reply_markup=get_back_inline_keyboard())
                return
            validity_days = int(code_info.get("validity_days", 1))
            mode = code_info.get("mode", "single")
            user_str_id = str(chat_id)
            claimed_users = code_info.get("claimed_users", [])

            # လူအများခွဲသုံးစနစ်
            if mode == "shared":
                if not is_admin and user_str_id in claimed_users:
                    bot.send_message(chat_id, "⚠️ <b>သင်သည် ဤ Code အား ရယူပြီးဖြစ်ပါသည်ခင်ဗျာ။</b>\n<i>(Code တစ်ခုလျှင် လူတစ်ဦး ၁ ကြိမ်သာ ရယူနိုင်ပါသည်)</i>", parse_mode="HTML", reply_markup=get_back_inline_keyboard())
                    return
                
                remaining = int(code_info.get("remaining", 0))
                if remaining < 500:
                    del codes[matched_code_key]
                    save_redeem_codes(codes)
                    bot.send_message(chat_id, "❌ <b>ဤ Code ၏ သတ်မှတ်ထားသော ပမာဏ ပြည့်သွားပါပြီဖြစ်၍ အသုံးပြု၍ မရတော့ပါခင်ဗျာ။</b>", parse_mode="HTML", reply_markup=get_back_inline_keyboard())
                    return

                possible_amounts = [1000, 2000, 3000]
                valid_options = [opt for opt in possible_amounts if opt <= remaining]

                if not valid_options:
                    awarded_amt = remaining
                else:
                    weights = [70, 20, 10][:len(valid_options)]
                    awarded_amt = random.choices(valid_options, weights=weights, k=1)[0]
                
                new_balance, exp_disp = add_expiring_bonus_to_wallet(chat_id, awarded_amt, validity_days)
                remaining -= awarded_amt
                claimed_users.append(user_str_id)
                code_info["remaining"] = remaining
                code_info["claimed_users"] = claimed_users
                
                if remaining < 500:
                    del codes[matched_code_key]
                else:
                    codes[matched_code_key] = code_info
                    
                save_redeem_codes(codes)

                user_name = message.from_user.first_name if message.from_user.first_name else "Winner"
                crown_icon = " 👑" if is_admin else ""
                disp_total_bal = "♾️" if is_admin else f"{new_balance:,} MMK"

                success_msg = (
                    f"🎉 <b>ဂုဏ်ယူပါတယ်ခင်ဗျာ! Redeem Code အောင်မြင်စွာ အသုံးပြုပြီးပါပြီ။</b>\n\n"
                    f"👤 <b>အသုံးပြုသူ:</b> {user_name}{crown_icon}\n"
                    f"🎟️ <b>Code:</b> <code>{matched_code_key}</code>\n"
                    f"💵 <b>ရရှိသော Wallet ငွေ:</b> <b>+{awarded_amt:,} MMK</b>\n"
                    f"⏰ <b>ငွေသက်တမ်း:</b> <b>{validity_days} ရက် (ကုန်ဆုံးရက်: {exp_disp})</b>\n\n"
                    f"💳 <b>လက်ရှိ သုံးနိုင်သော စုစုပေါင်းငွေ:</b> <b>{disp_total_bal}</b>\n\n"
                    f"💡 <i>ဤငွေဖြင့် ဝယ်ယူသော Key ၏ သက်တမ်းသည်လည်း {validity_days} ရက် ဖြစ်ပါမည်ခင်ဗျာ။</i>"
                )
                bot.send_message(chat_id, success_msg, parse_mode="HTML", reply_markup=get_back_inline_keyboard())

                for aid in ADMIN_CHAT_IDS:
                    try:
                        bot.send_message(
                            aid, 
                            f"🎟️ <b>Shared Redeem Code Claimed:</b>\n\nCustomer: {user_name}{crown_icon} (ID: <code>{chat_id}</code>) သည် Code <code>{matched_code_key}</code> မှ <b>{awarded_amt:,} MMK</b> ({validity_days} ရက် သက်တမ်း) ရယူသွားပါပြီ။\n(လက်ကျန် ပမာဏ: {remaining:,} MMK)",
                            parse_mode="HTML"
                        )
                    except:
                        pass
                return

            # တစ်ဦးတည်းသုံးစနစ်
            else:
                amt_to_add = int(code_info.get("amount", 1000))
                del codes[matched_code_key]
                save_redeem_codes(codes)
                
                new_balance, exp_disp = add_expiring_bonus_to_wallet(chat_id, amt_to_add, validity_days)
                user_name = message.from_user.first_name if message.from_user.first_name else "Winner"
                crown_icon = " 👑" if is_admin else ""
                disp_total_bal = "♾️" if is_admin else f"{new_balance:,} MMK"

                success_msg = (
                    f"🎉 <b>ဂုဏ်ယူပါတယ်ခင်ဗျာ! Redeem Code အောင်မြင်စွာ အသုံးပြုပြီးပါပြီ။</b>\n\n"
                    f"👤 <b>အသုံးပြုသူ:</b> {user_name}{crown_icon}\n"
                    f"🎟️ <b>Code:</b> <code>{matched_code_key}</code>\n"
                    f"💵 <b>ရရှိသော Wallet ငွေ:</b> <b>+{amt_to_add:,} MMK</b>\n"
                    f"⏰ <b>ငွေသက်တမ်း:</b> <b>{validity_days} ရက် (ကုန်ဆုံးရက်: {exp_disp})</b>\n\n"
                    f"💳 <b>လက်ရှိ သုံးနိုင်သော စုစုပေါင်းငွေ:</b> <b>{disp_total_bal}</b>\n\n"
                    f"💡 <i>ဤငွေဖြင့် ဝယ်ယူသော Key ၏ သက်တမ်းသည်လည်း {validity_days} ရက် ဖြစ်ပါမည်ခင်ဗျာ။</i>"
                )
                bot.send_message(chat_id, success_msg, parse_mode="HTML", reply_markup=get_back_inline_keyboard())

                for aid in ADMIN_CHAT_IDS:
                    try:
                        bot.send_message(
                            aid, 
                            f"🎟️ <b>Single Redeem Code Claimed:</b>\n\nCustomer: {user_name}{crown_icon} (ID: <code>{chat_id}</code>) သည် Code <code>{matched_code_key}</code> ဖြင့် <b>{amt_to_add:,} MMK</b> ({validity_days} ရက် သက်တမ်း) ရယူသွားပါပြီခင်ဗျာ။",
                            parse_mode="HTML"
                        )
                    except:
                        pass
                return
        else:
            bot.send_message(chat_id, "❌ <b>ထည့်သွင်းထားသော Redeem Code မှားယွင်းနေပါသည် (သို့မဟုတ်) အသုံးပြုပြီးသား ဖြစ်နေပါသည်ခင်ဗျာ။</b>", parse_mode="HTML", reply_markup=get_back_inline_keyboard())
            return

    # 🔍 Cus ရှာရန် (Admin)
    if input_value == "🔍 Cus ရှာရန်":
        clear_all_states(chat_id)
        if str(chat_id) not in [str(aid) for aid in ADMIN_CHAT_IDS]:
            bot.reply_to(message, "❌ ခွင့်လွှတ်ပါ၊ ဒီ ခလုတ်သည် Admin သီးသန့် အသုံးပြုနိုင်သော ခလုတ်ဖြစ်ပါသည်။")
            return
        
        bot.send_message(chat_id, "⏳ Customer စာရင်းများကို တွက်ချက်နေပါသည်...")
        summary_msg = get_customer_summary_stats()
        set_search_state(chat_id, True)
        bot.send_message(chat_id, summary_msg, parse_mode="HTML", reply_markup=get_back_inline_keyboard())
        return

    # 🎟️ Gen RD Code (Admin)
    if input_value == "🎟️ Gen RD Code":
        clear_all_states(chat_id)
        if str(chat_id) not in [str(aid) for aid in ADMIN_CHAT_IDS]:
            bot.reply_to(message, "❌ ခွင့်လွှတ်ပါ၊ ဒီ ခလုတ်သည် Admin သီးသန့် ဖြစ်ပါသည်။")
            return
        bot.send_message(
            chat_id,
            "🎟️ <b>Wallet Amount Redeem Code ထုတ်ရန်:</b>\n\nကျေးဇူးပြု၍ မည်သည့် <b>ငွေပမာဏ</b> အတွက် Code ထုတ်ယူမည်ကို ရွေးချယ်ပေးပါခင်ဗျာ:",
            parse_mode="HTML",
            reply_markup=get_admin_rd_amounts_keyboard()
        )
        return

    # 💸 ငွေနှုတ်ရန် (Admin Menu Button)
    if input_value == "💸 ငွေနှုတ်ရန်":
        clear_all_states(chat_id)
        if str(chat_id) not in [str(aid) for aid in ADMIN_CHAT_IDS]:
            bot.reply_to(message, "❌ ခွင့်လွှတ်ပါ၊ ဒီ ခလုတ်သည် Admin သီးသန့် ဖြစ်ပါသည်။")
            return
        bot.send_message(
            chat_id,
            "💸 <b>Customer များထံမှ ငွေပြန်လည်နှုတ်ယူခြင်း:</b>\n\nကျေးဇူးပြု၍ မည်သည့် လက်ကျန်ငွေအမျိုးအစားကို နှုတ်ယူလိုသည်ကို ရွေးချယ်ပေးပါခင်ဗျာ:",
            parse_mode="HTML",
            reply_markup=get_admin_deduct_type_keyboard()
        )
        return

    # 📢 Broadcast စာပို့ရန် (Admin)
    if input_value == "📢 Broadcast စာပို့ရန်":
        clear_all_states(chat_id)
        if str(chat_id) not in [str(aid) for aid in ADMIN_CHAT_IDS]:
            bot.reply_to(message, "❌ ခွင့်လွှတ်ပါ၊ ဒီ ခလုတ်သည် Admin သီးသန့် ဖြစ်ပါသည်။")
            return
        all_users = load_all_users()
        set_broadcast_state(chat_id, True)
        bot.send_message(chat_id, f"📢 <b>Broadcast စာပို့ရန်:</b> (User စုစုပေါင်း: {len(all_users)})\n\n👇 ပို့လိုသော စာသား သို့မဟုတ် ဓာတ်ပုံ ပို့ပေးပါခင်ဗျာ:", parse_mode="HTML", reply_markup=get_back_inline_keyboard())
        return

    if str(chat_id) in [str(aid) for aid in ADMIN_CHAT_IDS] and get_search_state(chat_id):
        set_search_state(chat_id, False)
        bot.send_message(chat_id, f"⏳ <b>'{input_value}'</b> ဖြင့် ရှာဖွေနေပါသည်...", parse_mode="HTML")
        matches, search_markup = search_users_by_query(input_value)
        if matches:
            search_markup.add(InlineKeyboardButton("🔙 မူလ Menu သို့ ပြန်သွားရန်", callback_data="back_to_main"))
            bot.send_message(chat_id, f"🔎 <b>ရှာဖွေတွေ့ရှိသော စာရင်း ({len(matches)} ခု):</b>\n\n👇 အသေးစိတ်ကြည့်ရန် နှိပ်ပါ -", parse_mode="HTML", reply_markup=search_markup)
        else:
            bot.send_message(chat_id, f"❌ <b>'{input_value}'</b> ဖြင့် ရှာမတွေ့ပါခင်ဗျာ။", parse_mode="HTML", reply_markup=get_back_inline_keyboard())
        return

    # Key Replacement Request Flow
    if get_replacement_state(chat_id):
        set_replacement_state(chat_id, False)
        bot.send_message(chat_id, "⏳ Key အား စစ်ဆေးနေပါသည်...")

        target_key, bytes_transferred, server_num = None, None, None
        for api_url in [
            (srv.get("api_url", "")).rstrip("/") or ""
            for srv in get_configured_servers()
        ]:
            if not api_url:
                continue
            target_key, bytes_transferred, server_num = fetch_key_from_server(api_url, input_value)
            if target_key:
                break

        if target_key:
            full_name = target_key.get("name", "HMA User")
            key_id = str(target_key.get("id"))
            date_match = re.search(r'\d{1,2}\.\d{1,2}\.(\d{4}|\d{2})', full_name)
            exp_date = date_match.group(0) if date_match else "30.09.2026"

            limit_bytes = target_key.get("dataLimit", {}).get("bytes", 0)
            usage_bytes = bytes_transferred.get(key_id, 0)
            total_gb = bytes_to_gb(limit_bytes) if limit_bytes else 500
            used_gb = bytes_to_gb(usage_bytes)
            rem_gb = max(0, round(total_gb - used_gb, 2))

            alert_text = (
                f"♻️ <b>KEY REPLACEMENT REQUEST</b>\n\n"
                f"👤 ဝယ်ယူသူ: {message.from_user.first_name}\n"
                f"🆔 Chat ID: <code>{chat_id}</code>\n"
                f"📡 Server: Server {server_num}\n"
                f"🔑 Key အဟောင်း: {full_name}\n"
                f"🧰 ကျန်ရှိ Data: <b>{rem_gb} GB</b> / {total_gb} GB\n"
                f"⏰ သက်တမ်းကုန်ရက်: <b>{exp_date}</b>"
            )
            markup = InlineKeyboardMarkup()
            target_servers = get_configured_servers()
            if target_servers:
                for srv in target_servers:
                    sid = str(srv.get("id"))
                    btn_label = f"📡 {get_server_display_name(sid)} သို့"
                    markup.add(InlineKeyboardButton(btn_label, callback_data=f"replace_srv{sid}_{server_num}_{key_id}_{chat_id}_{rem_gb}_{exp_date}"))
            markup.row(InlineKeyboardButton("❌ Reject", callback_data=f"replace_reject_{chat_id}_{key_id}"))

            for aid in ADMIN_CHAT_IDS:
                try: bot.send_message(aid, alert_text, parse_mode="HTML", reply_markup=markup)
                except: pass

            bot.send_message(chat_id, "✅ <b>Key စစ်ဆေးမှု အောင်မြင်ပါသည်။ Admin မှ အမြန်ဆုံး လဲလှယ်ပေးပါမည်။</b>", parse_mode="HTML", reply_markup=get_back_inline_keyboard())
            return
        else:
            bot.send_message(chat_id, "❌ ပေးပို့ထားသော Key ရှာမတွေ့ပါ။", parse_mode="HTML", reply_markup=get_back_inline_keyboard())
            return

    if input_value == "📊 Total Data Usage":
        clear_all_states(chat_id)
        if str(chat_id) not in [str(aid) for aid in ADMIN_CHAT_IDS]: return
        bot.send_message(chat_id, "📡 Data Usage တွက်ချက်နေပါသည်...")
        report_text = get_servers_total_usage()
        bot.send_message(chat_id, report_text, parse_mode="HTML", reply_markup=get_back_inline_keyboard())
        return

    if input_value in ["💰 လစဉ် ဝင်ငွေ", "လစဉ် ဝင်ငွေ"]:
        clear_all_states(chat_id)
        if str(chat_id) not in [str(aid) for aid in ADMIN_CHAT_IDS]: return
        bot.send_message(chat_id, "💰 ရောင်းရငွေ စာရင်း တွက်ချက်နေပါသည်...")
        rev_report = get_monthly_revenue_report()
        bot.send_message(chat_id, rev_report, parse_mode="HTML", reply_markup=get_back_inline_keyboard())
        return

    if input_value in ["🤖 Bot Refresh", "/refresh"]:
        clear_all_states(chat_id)
        bot.send_message(chat_id, "🤖 <b>Bot စနစ်အား Refresh ပြုလုပ်ပြီးပါပြီခင်ဗျာ!</b>", parse_mode="HTML", reply_markup=get_main_menu_keyboard(chat_id))
        return

    if input_value.startswith('/'):
        return

    # ⚡️ Data ပမာဏစစ်ဆေးခြင်း (User Paste Key)
    target_key, bytes_transferred, server_num = None, None, None
    for api_url in [
        (srv.get("api_url", "")).rstrip("/") or ""
        for srv in get_configured_servers()
    ]:
        if not api_url:
            continue
        target_key, bytes_transferred, server_num = fetch_key_from_server(api_url, input_value)
        if target_key:
            break

    if target_key:
        try:
            full_name = target_key.get("name", "HMA User")
            key_id = str(target_key.get("id"))
            
            display_name = full_name
            date_match_str = None
            for m in re.finditer(r'\d{1,2}\.\d{1,2}\.(\d{4}|\d{2})', full_name):
                date_match_str = m.group(0)

            if date_match_str: display_name = display_name.replace(date_match_str, "")
            display_name = display_name.replace("[GW]", "").replace("[gw]", "").split("tg")[0].replace("_", " ").strip() or "HMA Customer"

            if date_match_str:
                e_parts = date_match_str.split('.')
                day, month, year_str = int(e_parts[0]), int(e_parts[1]), e_parts[2]
                year = int("20" + year_str) if len(year_str) == 2 else int(year_str)
                end_date = f"{day}.{month}.{year}"
                has_date = True
            else:
                has_date = False

            limit_bytes = target_key.get("dataLimit", {}).get("bytes")
            plan_gb_val = bytes_to_gb(limit_bytes) if limit_bytes else 500
            plan_gb = f"{plan_gb_val} GB" if limit_bytes else "Unlimited"
            
            if bytes_transferred:
                usage_bytes = bytes_transferred.get(str(key_id), 0)
                usage_gb = bytes_to_gb(usage_bytes)
                usage_gb_str = f"{usage_gb} GB"
                rem_gb_str = f"{max(0, round(plan_gb_val - usage_gb, 2))} GB" if limit_bytes else "Unlimited"
            else:
                usage_gb_str = "ဆာဗာလိုင်းမရသဖြင့် မသိရှိနိုင်ပါ"
                rem_gb_str = plan_gb
            
            order_id_disp = get_order_id_for_key(full_name)
            ord_line = f"🧾 Order ID : <code>{order_id_disp}</code>\n" if order_id_disp != "N/A" else ""
            server_disp = f"Singapore Server {server_num} 🇸🇬" if bytes_transferred else f"Singapore Server {server_num} 🇸🇬 <i>(⚠️ Server Offline)</i>"

            result_text = (
                f"👤 အသုံးပြုသူ : {display_name}\n\n"
                f"{ord_line}\n\n"
                f"📡 Server : {server_disp}\n\n"
                f"🛍️ ဝယ်ယူထားသော Plan : {plan_gb}\n\n"
                f"🧰 အသုံးပြုပြီးသား Data : {usage_gb_str}\n\n"
                f"🗃️ ကျန်ရှိသော Data : <b>{rem_gb_str}</b>\n\n"
                f"⏰ သက်တမ်းကုန်ဆုံးရက်: {end_date if has_date else 'မသိရှိပါ'}"
            )
            bot.reply_to(message, result_text, parse_mode="HTML", reply_markup=get_back_inline_keyboard())
            return
        except Exception as e:
            bot.reply_to(message, f"❌ ဒေတာတွက်ချက်မှု မှားယွင်းနေပါသည်- {str(e)}")
            return

    not_found_msg = (
        "❌ <b>ခွင့်လွှတ်ပါဗျာ၊ တစ်ခုခုမှားနေပါတယ်ခင်ဗျာ။</b>\n\n"
        "💡 <i>Menu ခလုတ်များ Refresh လုပ်လိုပါက အောက်ပါ '🤖 Bot Refresh' ခလုတ် သို့မဟုတ် /start ကို နှိပ်ပေးပါခင်ဗျာ။</i>"
    )
    bot.reply_to(message, not_found_msg, parse_mode="HTML", reply_markup=get_main_menu_keyboard(chat_id))

