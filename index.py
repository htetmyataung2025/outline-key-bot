import os
import requests
from flask import Flask, request, jsonify
import telebot

app = Flask(__name__)

# API Link နှင့် Token ကို ကုဒ်ထဲတွင် တိုက်ရိုက်ထည့်သွင်းထားခြင်း
TELEGRAM_TOKEN = "8779558815:AAEaXF6rRqCVM-PFhbOlwgubSknk5xTiKvU"
OUTLINE_API_URL = "https://h.e.feature.hma.qzz.io:49429/YkDBSn3KwUaICBvzDQtvxQ"

bot = telebot.TeleBot(TELEGRAM_TOKEN, threaded=False)
requests.packages.urllib3.disable_warnings()

def bytes_to_gb(bytes_value):
    return round(bytes_value / (1024 ** 3), 2)

@bot.message_handler(commands=['start'])
def send_welcome(message):
    bot.reply_to(message, "👋 မင်္ဂလာပါ! Outline Data Usage Bot အဆင်သင့်ဖြစ်ပါပြီ။\n\n📊 အားလုံးစစ်ရန်: /all\n🔑 သီးသန့်စစ်ရန်: /usage [Key ID]")

@bot.message_handler(commands=['usage'])
def get_usage(message):
    try:
        response = requests.get(f"{OUTLINE_API_URL}/metrics/transfer", verify=False, timeout=10)
        data = response.json()
        bytes_transferred = data.get("bytesTransferredByUserId", {})

        args = message.text.split()[1:]
        if args:
            input_value = args[0]
            key_id = input_value
            
            # အကယ်၍ user က ss:// link ကြီး ထည့်လာရင် ID ကို ဖြတ်ယူခြင်း
            if "outline=1" in input_value:
                try:
                    # ဥပမာ outline=5#Name ထဲက 5 ကို ဖြတ်ယူမည်
                    part = input_value.split("outline=")[1]
                    key_id = part.split("#")[0]
                except:
                    pass

            usage_bytes = bytes_transferred.get(key_id, 0)
            usage_gb = bytes_to_gb(usage_bytes)
            bot.reply_to(message, f"🔑 **Key ID:** {key_id}\n📊 **Data Used:** {usage_gb} GB")
        else:
            bot.reply_to(message, "💡 ကျေးဇူးပြု၍ Key ID (သို့မဟုတ်) Key Link ထည့်ပေးပါ။ ဥပမာ - `/usage 5` သို့မဟုတ် `/usage ss://...`")
    except Exception as e:
        bot.reply_to(message, f"❌ Server သို့ ချိတ်ဆက်၍မရပါ- {str(e)}")

@bot.message_handler(commands=['all'])
def get_all_usage(message):
    try:
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

        bot.reply_to(message, report)
    except Exception as e:
        bot.reply_to(message, f"❌ Data ဆွဲမရပါ- {str(e)}")

# Catch-all Webhook Route
@app.route('/', defaults={'path': ''}, methods=['POST', 'GET'])
@app.route('/<path:path>', methods=['POST', 'GET'])
def index(path):
    if request.method == 'POST':
        json_string = request.get_data().decode('utf-8')
        update = telebot.types.Update.de_json(json_string)
        bot.process_new_updates([update])
        return jsonify({"status": "ok"}), 200
    return "Bot is running perfectly!", 200
