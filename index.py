import os
import requests
from flask import Flask, request, jsonify
import telebot
import re
import base64
from datetime import datetime
from dateutil.relativedelta import relativedelta

app = Flask(__name__)

# Token & API Configuration
TELEGRAM_TOKEN = "8779558815:AAEaXF6rRqCVM-PFhbOlwgubSknk5xTiKvU"
OUTLINE_API_URL = "https://h.e.feature.hma.qzz.io:49429/YkDBSn3KwUaICBvzDQtvxQ"

bot = telebot.TeleBot(TELEGRAM_TOKEN, threaded=False)
requests.packages.urllib3.disable_warnings()

def bytes_to_gb(bytes_value):
    # Outline Manager အတိုင်း ကွက်တိတူညီစေရန် 1 GB = 1,000,000,000 bytes ဖြင့် တွက်ချက်ခြင်း
    return round(bytes_value / (1000 ** 3), 2)

def clean_ss_url(url_str):
    """ URL ထဲမှ မလိုအပ်သော params များနှင့် tags များကို ဖြတ်ထုတ်ရန် """
    if not url_str:
        return ""
    main_part = url_str.replace("ss://", "").split("#")[0].split("?")[0]
    return main_part.strip()

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

        target_key = None

        # ၁။ အကယ်၍ ကီးနောက်မှာ # ခံပြီး နာမည်ပါလာပါက နာမည်ဖြင့် အရင်ရှာခြင်း
        if "#" in input_value:
            try:
                raw_name = input_value.split("#")[1]
                clean_name = "".join(re.findall(r'[a-zA-Z0-9_\s]', raw_name)).replace("_", " ").strip().lower()
                
                if clean_name:
                    for key in keys_data:
                        k_name = key.get("name", "").lower()
                        if clean_name in k_name:
                            target_key = key
                            break
            except Exception as e:
                print(f"Name match error: {e}")

        # ၂။ နာမည်ဖြင့် ရှာမတွေ့ပါက သို့မဟုတ် # နာမည်မပါလာပါက URL string ဖြင့် ကွက်တိတိုက်စစ်ခြင်း
        if not target_key and input_value.startswith("ss://"):
            input_clean = clean_ss_url(input_value)
            
            for key in keys_data:
                server_access_url = key.get("accessUrl", "")
                if server_access_url:
                    server_clean = clean_ss_url(server_access_url)
                    if input_clean and (input_clean in server_clean or server_clean in input_clean):
                        target_key = key
                        break

        # ၃။ အကယ်၍ numeric ID သီးသန့် ပို့လာပါက
        if not target_key:
            match_numeric = re.search(r'^\d+$', input_value)
            if match_numeric:
                for key in keys_data:
                    if str(key.get("id")) == str(match_numeric.group(0)):
                        target_key = key
                        break

        # စစ်ဆေးမည့် Key အစစ်အမှန်အား တွေ့ရှိပါက Result ထုတ်ပေးခြင်း
        if target_key:
            full_name = target_key.get("name", "HMA User")
            key_id = str(target_key.get("id"))
            
            # နာမည်ကို သန့်စင်ခြင်း
            display_name = full_name.split("tg")[0].split("Tg")[0].replace("_", " ").strip()
            if not display_name:
                display_name = "HMA Customer"
            
            # ရက်စွဲအား နာမည်အမှန်ထဲမှ ရှာဖွေတွက်ချက်ပြီး 0 ဖြုတ်ခြင်း
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
            
            # Result Display
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
            bot.reply_to(message, "❌ ခွင့်လွှတ်ပါဗျာ၊ ထည့်သွင်းထားသော Key Link မှားယွင်းနေသဖြင့် သို့မဟုတ် Server တွင် မရှိသဖြင့် ရှာမတွေ့ပါ။ ပြန်လည်စစ်ဆေးပေးပါဦး။")
            
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
