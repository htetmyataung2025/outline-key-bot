import os
import requests
from telegram import Update
from telegram.ext import Application, CommandHandler, ContextTypes

# Environment Variables များ (Vercel မှာ ထည့်ပေးရမည်)
TELEGRAM_TOKEN = os.getenv("8779558815:AAEaXF6rRqCVM-PFhbOlwgubSknk5xTiKvU")
OUTLINE_API_URL = os.getenv("https://h.e.feature.hma.qzz.io:49429/YkDBSn3KwUaICBvzDQtvxQ") # ဥပမာ- https://123.45.67.89:51083/secret-path

# SSL Warning များကို ပိတ်ထားရန် (Outline self-signed cert သုံးထားလျှင် လိုအပ်သည်)
requests.packages.urllib3.disable_warnings()

# Data standard သတ်မှတ်ရန် Function
def bytes_to_gb(bytes_value):
    return round(bytes_value / (1024 ** 3), 2)

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("👋 မင်္ဂလာပါ! Outline Key ရဲ့ Data Usage စစ်ဆေးဖို့ /usage [Key ID] သို့မဟုတ် အားလုံးစစ်ရန် /all ကိုနှိပ်ပါ။")

async def get_usage(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        # Outline Server ဆီက Data Usage လှမ်းယူခြင်း
        response = requests.get(f"{OUTLINE_API_URL}/metrics/transfer", verify=False, timeout=10)
        data = response.json()
        bytes_transferred = data.get("bytesTransferredByUserId", {})

        if context.args:
            # Key ID တစ်ခုတည်း စစ်ဆေးခြင်း
            key_id = context.args[0]
            usage_bytes = bytes_transferred.get(key_id, 0)
            usage_gb = bytes_to_gb(usage_bytes)
            await update.message.reply_text(f"🔑 **Key ID:** {key_id}\n📊 **Data Used:** {usage_gb} GB")
        else:
            await update.message.reply_text("💡 ကျေးဇူးပြု၍ Key ID ထည့်ပေးပါ။ ဥပမာ - `/usage 1`")

    except Exception as e:
        await update.message.reply_text(f"❌ အမှားအယွင်းတစ်ခုရှိနေပါသည်- {str(e)}")

async def get_all_usage(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        # Key ID အားလုံးနှင့် ၎င်းတို့၏ အမည်များကို ယူရန်
        keys_resp = requests.get(f"{OUTLINE_API_URL}/access-keys", verify=False, timeout=10)
        metrics_resp = requests.get(f"{OUTLINE_API_URL}/metrics/transfer", verify=False, timeout=10)
        
        keys_data = keys_resp.json().get("accessKeys", [])
        bytes_transferred = metrics_resp.json().get("bytesTransferredByUserId", {})

        report = "📊 **Outline Keys Data Usage List:**\n\n"
        for key in keys_data:
            k_id = key.get("id")
            name = key.get("name", f"Key {k_id}")
            usage_bytes = bytes_transferred.get(k_id, 0)
            usage_gb = bytes_to_gb(usage_bytes)
            report += f"👤 {name} (ID: {k_id}) -> {usage_gb} GB\n"

        await update.message.reply_text(report)
    except Exception as e:
        await update.message.reply_text(f"❌ အမှားအယွင်းရှိပါသည်- {str(e)}")

# Vercel Serverless Function အတွက် ပင်မ Handler
app = Application.builder().token(TELEGRAM_TOKEN).build()
app.add_handler(CommandHandler("start", start))
app.add_handler(CommandHandler("usage", get_usage))
app.add_handler(CommandHandler("all", get_all_usage))

# Vercel Webhook mapping အတွက် အသုံးပြုရန်
async def handler(request):
    # Telegram Webhook မှလာသော တောင်းဆိုချက်များကို ဖြေရှင်းရန်
    return await app.fetch_main()
