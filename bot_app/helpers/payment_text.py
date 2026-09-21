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

