Import os
import requests
from flask import Flask, request, jsonify
import telebot
import re
from datetime import datetime
from dateutil.relativedelta import relativedelta

app = Flask(__name__)

# Token & API Configuration
TELEGRAM_TOKEN = "8779558815:AAEaXF6rRqCVM-PFhbOlwgubSknk5xTiKvU"
OUTLINE_API_URL = "https://h.e.feature.hma.qzz.io:49429/YkDBSn3KwUaICBvzDQtvxQ"

bot = telebot.TeleBot(TELEGRAM_TOKEN, threaded=False)
requests.packages.urllib3.disable_warnings()

def bytes_to_gb(bytes_value):
    return round(bytes_value / (1024 ** 3), 2)

# /start Command
@bot.message_handler(commands=['start'])
def send_welcome(message):
    welcome_text = (
        "👋 မင်္ဂလာပါ! H & E FEATURE Data Usage Bot မှ ကြိုဆိုပါတယ်။\n\n"
        "📊 ကျွန်တော်ဆီက ဝယ်ယူထားတဲ့ VPN သက်တမ်းနဲ့ Data အသုံးပြုမှုကို စစ်ဆေးရန်အတွက် ဘာ Command မှ ရိုက်စရာမလိုပါဘူးခင်ဗျာ။\n\n"
        "👇 **ကျွန်တော်ဆီက ဝယ်ယူထားတဲ့ VPN Key Link ကို Copyယူပြီး Chat ထဲသို့ တိုက်ရိုက် ပို့ပေးလိုက်ပါ။\n\n"
        "👉 Copy ယူလာတဲ့ `ss://...` နဲ့စတဲ့ Key တစ်ခုလုံးကို ဒီမှာတန်းပြီး Paste ချပို့ပြီးစစ်နိုင်ပါတယ်။"
    )
    bot.reply_to(message, welcome_text, parse_mode="Markdown")

# စာသား သို့မဟုတ် Key Link များ တန်းပို့လာပါက ဖမ်းယူစစ်ဆေးပေးမည့်စနစ်
@bot.message_handler(func=lambda message: True)
def handle_all_messages(message):
    input_value = message.text.strip()
    
    if input_value.startswith('/'):
        return

    try:
        keys_resp = requests.get(f"{OUTLINE_API_URL}/access-keys", verify=False, timeout=10)
        metrics_resp = requests.get(f"{OUTLINE_API_URL}/metrics/transfer", verify=False, timeout=10)
        
        keys_data = keys_resp.json().get("accessKeys", [])
        bytes_transferred = metrics_resp.json().get("bytesTransferredByUserId", {})

        key_id = None
        target_key = None

        if "#" in input_value:
            try:
                raw_name = input_value.split("#")[1]
                clean_name = "".join(re.findall(r'[a-zA-Z0-9_\s]', raw_name)).replace("_", " ").strip().lower()
                
                for key in keys_data:
                    k_name = key.get("name", "").lower()
                    if clean_name and clean_name in k_name:
                        key_id = str(key.get("id"))
                        target_key = key
                        break
            except Exception as e:
                print(f"Error parsing name: {e}")

        if not key_id:
            match_outline = re.search(r'outline=(\d+)', input_value)
            extracted_id = match_outline.group(1) if match_outline else re.search(r'\d+', input_value).group(0) if re.search(r'\d+', input_value) else None
            
            if extracted_id:
                for key in keys_data:
                    if str(key.get("id")) == str(extracted_id):
                        key_id = str(key.get("id"))
                        target_key = key
                        break

        if key_id and target_key:
            full_name = target_key.get("name", "HMA User")
            display_name = full_name.split("tg")[0].replace("_", " ").strip()
            
            date_match = re.search(r'\d{1,2}\.\d{1,2}\.\d{4}', full_name)
            if date_match:
                end_date_raw = date_match.group(0)
                try:
                    e_parts = end_date_raw.split('.')
                    end_date = f"{int(e_parts[0])}.{int(e_parts[1])}.{e_parts[2]}"
                    
                    end_date_obj = datetime.strptime(end_date_raw, "%d.%m.%Y")
                    start_date_obj = end_date_obj - relativedelta(months=1)
                    start_date = f"{start_date_obj.day}.{start_date_obj.month}.{start_date_obj.year}"
                except:
                    end_date = end_date_raw
                    start_date = "သတ်မှတ်မထားပါ"
            else:
                end_date = "သတ်မှတ်မထားပါ"
                start_date = "သတ်မှတ်မထားပါ"

            limit_bytes = target_key.get("dataLimit", {}).get("bytes")
            if limit_bytes:
                plan_gb = f"{bytes_to_gb(limit_bytes)} GB"
            else:
                plan_gb = "Unlimited"

            usage_bytes = bytes_transferred.get(str(key_id), 0)
            usage_gb = bytes_to_gb(usage_bytes)
            
            # Telegram မှ စာသားကျုံ့ပစ်သည့်စနစ်အား မသုံးနိုင်အောင် Code Block (```) ဖြင့် ညီညာစွာ ဝန်းရံထားခြင်း
            result_text = (
                f"```\n"
                f"👤 အသုံးပြုသူ: {display_name}\n"
                f"📅 Start Date: {start_date}\n"
                f"⏳ End Date: {end_date}\n"
                f"📋 ဝယ်ယူထားသော Plan: {plan_gb}\n"
                f"📊 အသုံးပြုပြီးသား Data: {usage_gb} GB\n"
                f"```"
            )
            bot.reply_to(message, result_text, parse_mode="MarkdownV2")
        else:
            bot.reply_to(message, "❌ ခွင့်လွှတ်ပါဗျာ၊ ထည့်သွင်းထားသော Key Link မှားယွင်းနေသဖြင့် ရှာမတွေ့ပါ။ ပြန်လည်စစ်ဆေးပေးပါဦး။")
            
    except Exception as e:
        bot.reply_to(message, f"❌ Server သို့ ချိတ်ဆက်၍မရပါ- {str(e)}")

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