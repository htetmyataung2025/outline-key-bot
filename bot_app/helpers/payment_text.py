"""Payment instruction text (pure string builder)."""


def get_payment_instruction_text(amt):
    return (
        f"✅ <b>Wallet ထဲသို့ ငွေဖြည့်သွင်းရန်</b>\n"
        f"💵 ဖြည့်သွင်းမည့် ပမာဏ: <b>{amt:,} Ks</b>\n\n"
        f"━━━━━━━━━━━━━━━\n"
        f"💰 <b>ငွေလွှဲရမည့် အကောင့်အချက်အလက်များ:</b>\n\n"
        f"📱 <b>KBZ Pay</b> - <code>09699970092</code>\n"
        f"👤 Htet Myat Aung\n\n"
        f"📱 <b>Wave Pay</b> - <code>09699970092</code>\n"
        f"👤 Htet Myat Aung\n\n"
        f"📱 <b>AYA Pay</b> - <code>09699970092</code>\n"
        f"👤 Htet Myat Aung\n\n"
        f"📱 <b>Uab Pay</b> - <code>09699970092</code>\n"
        f"👤 Htet Myat Aung\n\n"
        f"📱 <b>CB Pay</b> - <code>09699970092</code>\n"
        f"👤 Htet Myat Aung\n\n"
        f"━━━━━━━━━━━━━━━\n\n"
        f"👉 အထက်ပါ အကောင့်တစ်ခုခုသို့ <b>{amt:,} Ks</b> တိတိကျကျ လွှဲပေးပါခင်ဗျာ။\n\n"
        f"🙏🏻 ငွေလွှဲပြီး 📸 <b>Screenshot (ပြေစာ)</b> လေး ပို့ပေးပါခင်ဗျာ🥰\n\n"
        f"<i>Admin မှ ပြေစာစစ်ဆေးအတည်ပြုပြီးသည်နှင့် Wallet ထဲသို့ ချက်ချင်း ငွေထည့်သွင်းပေးပါမည်။ ကျေးဇူးတင်ပါသည်ခင်ဗျာ။ 🙏</i>"
    )


def build_admin_topup_notice(amount, new_balance, reason=""):
    """Customer notice for a manual admin Top-Up (no Top-Up ID — added by hand)."""
    lines = [
        "🎉 <b>ငွေဖြည့်သွင်းမှု အောင်မြင်ပါသည်!</b>\n",
        f"💵 ဖြည့်သွင်းငွေ: <b>+{amount:,} MMK</b>\n",
        f"💳 လက်ရှိ Wallet လက်ကျန်ငွေ: <b>{new_balance:,} MMK</b>",
    ]
    if reason and str(reason).strip():
        lines.append(f"\n📝 မှတ်ချက်: {str(reason).strip()}")
    lines.append(
        "\n🛍️ '<b>Plan များဝယ်ရန်</b>' Menu မှတစ်ဆင့် VPN Key များကို "
        "အချိန်မရွေး စိတ်ကြိုက် ဝယ်ယူနိုင်ပါပြီခင်ဗျာ!"
    )
    return "\n".join(lines)


def build_admin_deduct_notice(amount, new_balance, reason=""):
    """Customer notice for a manual admin Deduct."""
    lines = [
        "📉 <b>ငွေပြန်နုတ်ယူခြင်း အောင်မြင်ပါသည်</b>\n",
        f"💵 နုတ်ယူငွေ: <b>-{amount:,} MMK</b>\n",
        f"💳 လက်ရှိ Wallet လက်ကျန်ငွေ: <b>{new_balance:,} MMK</b>",
    ]
    if reason and str(reason).strip():
        lines.append(f"\n📝 မှတ်ချက်: {str(reason).strip()}")
    lines.append("\nℹ️ မေးမြန်းစရာရှိပါက Admin ထံ တိုက်ရိုက် ဆက်သွယ်ပေးပါခင်ဗျာ။")
    return "\n".join(lines)

