"""Admin sales/revenue reports."""

from bot_app.timeutil import myanmar_now

from bot_app.services.orders import load_sales_history
from bot_app.services.outline import get_configured_servers, get_server_display_name


def get_monthly_revenue_report():
    now = myanmar_now()
    now_str = now.strftime("%d/%m/%Y (%I:%M %p)")
    current_year = now.year
    current_month = now.month
    today_str = now.strftime("%Y-%m-%d")

    sales_history = load_sales_history()

    # One bucket per server id; non-numeric server tags (manual "VIP" orders)
    # are grouped under VIP. Buckets follow the Settings server list, so
    # adding/removing a server there re-shapes this report automatically.
    stats = {}

    today_plans = {}

    for item in sales_history:
        item_year = item.get("year")
        item_month = item.get("month")

        if item_year == current_year and item_month == current_month:
            srv = str(item.get("server", "1"))
            bucket = srv if srv.isdigit() else "VIP"
            price = int(item.get("price", 0))
            p_name = item.get("plan_name", "Plan")
            p_months = item.get("months", 1)
            p_key_str = f"{p_name} [{p_months} လစာ]"
            is_today = (item.get("date") == today_str)

            if is_today:
                today_plans[p_key_str] = today_plans.get(p_key_str, 0) + 1

            s = stats.setdefault(bucket, {"keys": 0, "rev": 0, "today_keys": 0, "today_rev": 0})
            s["keys"] += 1
            s["rev"] += price
            if is_today:
                s["today_keys"] += 1
                s["today_rev"] += price

    total_keys = sum(s["keys"] for s in stats.values())
    total_rev = sum(s["rev"] for s in stats.values())
    today_keys = sum(s["today_keys"] for s in stats.values())
    today_rev = sum(s["today_rev"] for s in stats.values())

    def format_sales_breakdown(plans_dict):
        if not plans_dict:
            return "   • <i>မရှိသေးပါ</i>"
        lines = []
        for k, v in plans_dict.items():
            lines.append(f"   • {k}: <b>{v}</b> ခု")
        return "\n".join(lines)

    # Row order: configured servers (Settings order) → VIP → legacy ids still
    # present in sales history but since removed from Settings, so historical
    # revenue never disappears from the report.
    ordered_buckets = [str(srv.get("id")) for srv in get_configured_servers()]
    if "VIP" not in ordered_buckets:
        ordered_buckets.append("VIP")
    ordered_buckets += [b for b in stats if b not in ordered_buckets]

    server_lines = []
    for bucket in ordered_buckets:
        s = stats.get(bucket, {"keys": 0, "rev": 0})
        if bucket == "VIP":
            server_lines.append(f"⚡ <b>VIP (စိတ်ကြိုက်သုံး) :</b> <b>{s['rev']:,} Ks</b> ({s['keys']} ခု)")
        else:
            server_lines.append(f"📡 <b>{get_server_display_name(bucket)} :</b> <b>{s['rev']:,} Ks</b> ({s['keys']} ခု)")
    server_section = "\n".join(server_lines)

    report = (
        f"💵 <b>MONTHLY SALES REVENUE REPORT</b>\n"
        f"📅 <b>စစ်ဆေးသည့် ရက်စွဲ:</b> <code>{now_str}</code>\n"
        f"━━━━━━━━━━━━━━━━━\n\n"
        f"🔥 <b>ဒီနေ့ ရောင်းရငွေ (Today's Sales)</b>\n"
        f"🔑 ရောင်းရသော Key: <b>{today_keys} ခု</b>\n"
        f"{format_sales_breakdown(today_plans)}\n"
        f"💰 ဒီနေ့ ဝင်ငွေ: <b>{today_rev:,} Ks</b>\n\n"
        f"━━━━━━━━━━━━━━━━━\n\n"
        f"{server_section}\n\n"
        f"━━━━━━━━━━━━━━━━━\n"
        f"🌐 <b>Total This Month Paid Keys:</b> <b>{total_keys} ခု</b>\n"
        f"💎 <b>ဒီလ စုစုပေါင်း ဝင်ငွေ:</b> <b>{total_rev:,} MMK</b>\n\n"
    )
    return report
