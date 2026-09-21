"""Admin sales/revenue reports."""

from bot_app.timeutil import myanmar_now

from bot_app.services.orders import load_sales_history


def get_monthly_revenue_report():
    now = myanmar_now()
    now_str = now.strftime("%d/%m/%Y (%I:%M %p)")
    current_year = now.year
    current_month = now.month
    today_str = now.strftime("%Y-%m-%d")

    sales_history = load_sales_history()

    s1_keys, s1_rev, s1_today_keys, s1_today_rev = 0, 0, 0, 0
    s2_keys, s2_rev, s2_today_keys, s2_today_rev = 0, 0, 0, 0
    s3_keys, s3_rev, s3_today_keys, s3_today_rev = 0, 0, 0, 0
    vip_keys, vip_rev, vip_today_keys, vip_today_rev = 0, 0, 0, 0

    today_plans = {}

    for item in sales_history:
        item_year = item.get("year")
        item_month = item.get("month")
        
        if item_year == current_year and item_month == current_month:
            srv = str(item.get("server", "1"))
            price = int(item.get("price", 0))
            p_name = item.get("plan_name", "Plan")
            p_months = item.get("months", 1)
            p_key_str = f"{p_name} [{p_months} လစာ]"
            is_today = (item.get("date") == today_str)

            if is_today:
                today_plans[p_key_str] = today_plans.get(p_key_str, 0) + 1

            if srv == "1":
                s1_keys += 1
                s1_rev += price
                if is_today: s1_today_keys += 1; s1_today_rev += price
            elif srv == "2":
                s2_keys += 1
                s2_rev += price
                if is_today: s2_today_keys += 1; s2_today_rev += price
            elif srv == "3":
                s3_keys += 1
                s3_rev += price
                if is_today: s3_today_keys += 1; s3_today_rev += price
            else:
                vip_keys += 1
                vip_rev += price
                if is_today: vip_today_keys += 1; vip_today_rev += price

    total_keys = s1_keys + s2_keys + s3_keys + vip_keys
    total_rev = s1_rev + s2_rev + s3_rev + vip_rev
    today_keys = s1_today_keys + s2_today_keys + s3_today_keys + vip_today_keys
    today_rev = s1_today_rev + s2_today_rev + s3_today_rev + vip_today_rev

    def format_sales_breakdown(plans_dict):
        if not plans_dict:
            return "   • <i>မရှိသေးပါ</i>"
        lines = []
        for k, v in plans_dict.items():
            lines.append(f"   • {k}: <b>{v}</b> ခု")
        return "\n".join(lines)

    report = (
        f"💵 <b>MONTHLY SALES REVENUE REPORT</b>\n"
        f"📅 <b>စစ်ဆေးသည့် ရက်စွဲ:</b> <code>{now_str}</code>\n"
        f"━━━━━━━━━━━━━━━━━\n\n"
        f"🔥 <b>ဒီနေ့ ရောင်းရငွေ (Today's Sales)</b>\n"
        f"🔑 ရောင်းရသော Key: <b>{today_keys} ခု</b>\n"
        f"{format_sales_breakdown(today_plans)}\n"
        f"💰 ဒီနေ့ ဝင်ငွေ: <b>{today_rev:,} Ks</b>\n\n"
        f"━━━━━━━━━━━━━━━━━\n\n"
        f"📡 <b>Server 1 🇸🇬 :</b> <b>{s1_rev:,} Ks</b> ({s1_keys} ခု)\n"
        f"📡 <b>Server 2 🇸🇬 :</b> <b>{s2_rev:,} Ks</b> ({s2_keys} ခု)\n"
        f"📡 <b>Server 3 🇸🇬 :</b> <b>{s3_rev:,} Ks</b> ({s3_keys} ခု)\n"
        f"⚡ <b>VIP (စိတ်ကြိုက်သုံး) :</b> <b>{vip_rev:,} Ks</b> ({vip_keys} ခု)\n\n"
        f"━━━━━━━━━━━━━━━━━\n"
        f"🌐 <b>Total This Month Paid Keys:</b> <b>{total_keys} ခု</b>\n"
        f"💎 <b>ဒီလ စုစုပေါင်း ဝင်ငွေ:</b> <b>{total_rev:,} MMK</b>\n\n"
    )
    return report
