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
        # API များမှ Data ဆွဲယူခြင်း
        keys_resp = requests.get(f"{OUTLINE_API_URL}/access-keys", verify=False, timeout=10)
        metrics_resp = requests.get(f"{OUTLINE_API_URL}/metrics/transfer", verify=False, timeout=10)
        
        keys_data = keys_resp.json().get("accessKeys", [])
        bytes_transferred = metrics_resp.json().get("bytesTransferredByUserId", {})

        args = message.text.split()[1:]
        if args:
            input_value = args[0]
            key_id = None
            found_name = None

            # အကယ်၍ Link format ဖြင့် ပေးပို့လာပါက (# အနောက်က နာမည်ကို အဓိက ရှာဖွေမည်)
            if "#" in input_value:
                try:
                    # # အနောက်က အစိတ်အပိုင်းကို ယူပြီး ဉပမာ အလံ Emoji များ သို့မဟုတ် စာလုံးဆန်းများကို ဖယ်ထုတ်၍ စာသား သန့်စင်ခြင်း
                    raw_name = input_value.split("#")[1]
                    import re
                    # အင်္ဂလိပ်စာလုံး၊ ဂဏန်းနှင့် Space, Underline တို့ကိုပဲ ယူမည်
                    clean_name = "".join(re.findall(r'[a-zA-Z0-9_\s]', raw_name)).replace("_", " ").strip().lower()
                    
                    # Outline Access Keys ထဲတွင် ထိုနာမည် ပါဝင်မှု ရှိ၊ မရှိ ပတ်ရှာခြင်း
                    for key in keys_data:
                        k_name = key.get("name", "").lower()
                        # clean_name (ဥပမာ "thu ya") သည် key name (ဥပမာ "thu ya tg 18.8.2026") ထဲမှာ ပါသလား စစ်ဆေးခြင်း
                        if clean_name and clean_name in k_name:
                            key_id = str(key.get("id"))
                            found_name = key.get("name")
                            break
                except Exception as e:
                    print(f"Error parsing name: {e}")

            # အကယ်၍ နာမည်ဖြင့် ရှာမတွေ့ခဲ့ပါက (သို့မဟုတ်) Link မဟုတ်ဘဲ ID သီးသန့် ရိုက်ထည့်လာပါက
            if not key_id:
                import re
                # Link ထဲတွင် outline=X ပါက X ကို ယူရန် ကြိုးစားခြင်း
                match_outline = re.search(r'outline=(\d+)', input_value)
                if match_outline:
                    key_id = match_outline.group(1)
                else:
                    # ဂဏန်းသီးသန့် (ဥပမာ /usage 5) ဆိုလျှင် ထိုဂဏန်းကို ယူမည်
                    match_numeric = re.search(r'\d+', input_value)
                    if match_numeric:
                        key_id = match_numeric.group(0)

            # စစ်ဆေးမည့် ID ကို ရှာဖွေတွေ့ရှိပါက Data Usage ပြသခြင်း
            if key_id:
                # အကယ်၍ နာမည်ကိုပါ သိခဲ့လျှင် Name ပါ ပြမည်၊ မသိလျှင် ID သာ ပြမည်
                if not found_name:
                    for key in keys_data:
                        if str(key.get("id")) == str(key_id):
                            found_name = key.get("name")
                            break
                
                name_display = found_name if found_name else f"Key {key_id}"
                usage_bytes = bytes_transferred.get(str(key_id), 0)
                usage_gb = bytes_to_gb(usage_bytes)
                
                bot.reply_to(message, f"👤 **User:** {name_display} (ID: {key_id})\n📊 **Data Used:** {usage_gb} GB")
            else:
                bot.reply_to(message, "❌ Key ID သို့မဟုတ် Key Link ကို စနစ်တကျ ရှာဖွေ၍ မရနိုင်ပါသဖြင့် ပြန်လည်စစ်ဆေးပေးပါ။")
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
