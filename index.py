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
            
            # အကယ်၍ ss:// link အပြည့်အစုံ ပါလာပါက 
            if "ss://" in input_value or "outline=" in input_value:
                import re
                # နည်းလမ်း (၁): outline=X ကို အရင်ရှာမည်
                match_outline = re.search(r'outline=(\d+)', input_value)
                # နည်းလမ်း (၂): Link ထဲမှာ တစ်ခြားနံပါတ် ဥပမာ /5/ သို့မဟုတ် id=5 ပါရင် ရှာရန်
                match_id = re.search(r'(?:id=|/access-keys/|/)(\d+)(?:[?#]|$)', input_value)
                
                # အစ်ကို့ Link ထဲမှာ Thu_Ya က ID 5 ဖြစ်ပေမယ့် outline=1 ဖြစ်နေရင် 
                # အမည် (#Thu_Ya) ကိုပါ စစ်ပြီး metrics ထဲက ဆွဲထုတ်ဖို့ ကြိုးစားခြင်း
                if "#" in input_value:
                    try:
                        name_tag = input_value.split("#")[1].strip()
                        # အကယ်၍ အမည်ကို metrics သို့မဟုတ် access-keys ထဲမှာ တိုက်ရိုက်ရှာလို့ရလျှင် ရှာမည်
                        # ဒါပေမယ့် metrics/transfer ထဲမှာက ID နံပါတ်ပဲ ပါတာမို့ access-keys API ကိုပါ လှမ်းခေါ်ပြီး ID ရှာပါမယ်
                        keys_resp = requests.get(f"{OUTLINE_API_URL}/access-keys", verify=False, timeout=10)
                        keys_data = keys_resp.json().get("accessKeys", [])
                        for key in keys_data:
                            if name_tag.lower() in key.get("name", "").lower():
                                key_id = key.get("id")
                                break
                    except:
                        pass
                
                # အပေါ်က အမည်နဲ့ ရှာမတွေ့မှ Link ထဲက နံပါတ်ကို ယူမည်
                if key_id == input_value:
                    if match_outline:
                        key_id = match_outline.group(1)
                    elif match_id:
                        key_id = match_id.group(1)

            usage_bytes = bytes_transferred.get(str(key_id), 0)
            usage_gb = bytes_to_gb(usage_bytes)
            bot.reply_to(message, f"🔑 **Key ID:** {key_id}\n📊 **Data Used:** {usage_gb} GB")
        else:
            bot.reply_to(message, "💡 ကျေးဇူးပြု၍ Key ID (သို့မဟုတ်) Key Link ထည့်ပေးပါ။ ဥပမာ - `/usage 5`")
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
