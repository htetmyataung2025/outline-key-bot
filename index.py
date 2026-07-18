import os
import requests
from flask import Flask, request, jsonify
import telebot
from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton, ReplyKeyboardMarkup, KeyboardButton
import re
import base64
from datetime import datetime
from dateutil.relativedelta import relativedelta

app = Flask(__name__)

# Token & API Configuration
TELEGRAM_TOKEN = "8779558815:AAEaXF6rRqCVM-PFhbOlwgubSknk5xTiKvU"
OUTLINE_API_URL = "https://h.e.feature.hma.qzz.io:49429/YkDBSn3KwUaICBvzDQtvxQ"

# 🔑 အစ်ကို့ရဲ့ Telegram Chat ID အမှန်
ADMIN_CHAT_ID = "8778394176"  

bot = telebot.TeleBot(TELEGRAM_TOKEN, threaded=False)
requests.packages.urllib3.disable_warnings()

user_selected_plans = {}

PLANS = {
    "starter": {"name": "Starter Plan", "data": "25 GB", "price": "1,000 Ks"},
    "basic": {"name": "Basic Plan", "data": "50 GB", "price": "2,000 Ks"},
    "standard": {"name": "Standard Plan", "data": "75 GB", "price": "3,000 Ks"},
    "premium": {"name": "Premium Plan", "data": "100 GB", "price": "4,000 Ks"},
    "vip": {"name": "VIP Plan", "data": "150 GB", "price": "5,000 Ks"},
    "pro": {"name": "Pro Plan", "data": "200 GB", "price": "7,000 Ks"},
    "ultimate": {"name": "Ultimate VIP Plan", "data": "Unlimited", "price": "10,000 Ks"},
}

def bytes_to_gb(bytes_value):
    return round(bytes_value / (1000 ** 3), 2)

def clean_ss_url(url_str):
    if not url_str:
        return ""
    main_part = url_str.replace("ss://", "").split("#")[0].split("?")[0]
    return main_part.strip()

def get_main_menu_keyboard():
    markup = ReplyKeyboardMarkup(resize_keyboard=True, row_width=2)
    btn_buy = KeyboardButton("🛒 Plan များ ကြည့်ရန်")
    btn_check = KeyboardButton("📊 Data Usage စစ်ရန်")
    markup.add(btn_buy, btn_check)
    return markup

def get_plan_keyboard():
    markup = InlineKeyboardMarkup()
    markup.row(InlineKeyboardButton("🌟 Starter (25 GB) - 1,000 Ks", callback_data="buy_starter"))
    markup.row(InlineKeyboardButton("💎 Basic (50 GB) - 2,000 Ks", callback_data="buy_basic"))
    markup.row(InlineKeyboardButton("⚡ Standard (75 GB) - 3,000 Ks", callback_data="buy_standard"))
    markup.row(InlineKeyboardButton("🔥 Premium (100 GB) - 4,000 Ks", callback_data="buy_premium"))
    markup.row(InlineKeyboardButton("👑 VIP (150 GB) - 5,000 Ks", callback_data="buy_vip"))
    markup.row(InlineKeyboardButton("🚀 Pro (200 GB) - 7,000 Ks", callback_data="buy_pro"))
    markup.row(InlineKeyboardButton("🌌 Ultimate VIP (Unlimted) - 10,000 Ks", callback_data="buy_ultimate"))
    return markup

# /start Command
@bot.message_handler(commands=['start'])
def send_welcome(message):
    welcome_text = (
        "👋 မင်္ဂလာပါ! H & E FEATURE VPN ဝန်ဆောင်မှု Bot မှ ကြိုဆိုပါတယ်။\n\n"
        "👇 အောက်ခြေက Menu Button တွေကို အသုံးပြုပြီး မိမိတို့ အလိုရှိရာကို ရွေးချယ်နိုင်ပါတယ်ခင်ဗျာ။"
    )
    bot.reply_to(message, welcome_text, reply_markup=get_main_menu_keyboard(), parse_mode="Markdown")

# /buy Command
@bot.message_handler(commands=['buy'])
def send_plans(message):
    bot.reply_to(message, "🛒 **ကျေးဇူးပြု၍ သင်ဝယ်ယူလိုသော VPN Plan ကို ရွေးချယ်ပေးပါခင်ဗျာ:**", reply_markup=get_plan_keyboard())

# Plan Button Callback
@bot.callback_query_handler(func=lambda call: call.data.startswith("buy_"))
def handle_buy_callback(call):
    plan_code = call.data.replace("buy_", "")
    plan = PLANS.get(plan_code)
    chat_id = call.message.chat.id
    
    if plan:
        user_selected_plans[chat_id] = plan
        payment_text = (
            f"✅ **သင်ရွေးချယ်ထားသော Plan:**\n"
            f"📌 {plan['name']} ({plan['data']}) - {plan['price']}\n\n"
            f"━━━━━━━━━━━━━━━\n"
            f"💰 **ငွေလွှဲရမည့် အကောင့်အချက်အလက်များ:**\n\n"
            f"📱 **KBZ Pay** - `09699970092`\n"
            f"👤 Htet Myat Aung\n\n"
            f"📱 **Wave Pay** - `09699970092`\n"
            f"👤 Htet Myat Aung\n\n"
            f"📱 **AYA Pay** - `09699970092`\n"
            f"👤 Htet Myat Aung\n\n"
            f"📱 **Uab Pay** - `09699970092`\n"
            f"👤 Htet Myat Aung\n"
            f"━━━━━━━━━━━━━━━\n\n"
            f"🙏🏻 ပိုက်ဆံချေဖို့ Ngwelweပြီး Screenshot လေး ပို့ပေးပါခင်ဗျာ🥰\n"
            f"*(ငွေလွှဲပြေစာ ပို့ပေးပြီးပါက လူကြီးမင်းထံသို့ VPN Key လင့်ခ်အား အမြန်ဆုံး ဖန်တီးပေးပို့သွားမည် ဖြစ်ပါသည်)*"
        )
        bot.send_message(chat_id, payment_text, parse_mode="Markdown")
        bot.answer_callback_query(call.id)

# Screenshot Received (အစ်ကို့ဆီ အချက်အလက် တန်းပို့ပေးမည့်အပိုင်း)
@bot.message_handler(content_types=['photo'])
def handle_payment_screenshot(message):
    chat_id = message.chat.id
    user_name = message.from_user.first_name if message.from_user.first_name else "HMA User"
    username = f"@{message.from_user.username}" if message.from_user.username else "No Username"
    
    plan_info = user_selected_plans.get(chat_id, {"name": "သတ်မှတ်မထားသော Plan", "price": "မသိရှိပါ"})
    current_time = datetime.now().strftime("%d/%m/%Y %I:%M %p")

    # အစ်ကို့ဆီ ပို့ပေးမည့် သေသပ်လှပသော စာသားပုံစံ
    admin_alert_text = (
        f"💰 **ငွေလွှဲပြေစာ အသစ်ရောက်ရှိလာပါပြီ!**\n\n"
        f"👤 **ဝယ်ယူသူနာမည်:** {user_name} ({username})\n"
        f"📦 **ရွေးချယ်ထားသော Plan:** {plan_info['name']}\n"
        f"💵 **ကျသင့်ငွေပမာဏ:** {plan_info['price']}\n"
        f"⏰ **ပေးပို့သည့်အချိန်:** {current_time}\n"
        f"🆔 **User Chat ID:** `{chat_id}`\n\n"
        f"📢 *ပြေစာရှိ ID ၅ လုံးကို စစ်ဆေးပါ။ အတည်ပြုလိုပါက ဤစာသားကို Reply ပြန်ပြီး VPN Key (ss://...) ကို ရိုက်ပို့ပေးလိုက်ပါဗျာ။*"
    )
    
    try:
        bot.send_photo(ADMIN_CHAT_ID, message.photo[-1].file_id, caption=admin_alert_text, parse_mode="Markdown")
        bot.reply_to(message, "⏳ လူကြီးမင်း ပေးပို့လိုက်သော Ngwelweပြေစာအား လက်ခံရရှိပါပြီဗျာ။ စနစ်မှ အတည်ပြုပြီးသည်နှင့် VPN Key လင့်ခ်အား ဤနေရာသို့ ချက်ချင်း ပို့ဆောင်ပေးမည် ဖြစ်ပါသည်။ ကျေးဇူးတင်ပါသည်ခင်ဗျာ။")
    except Exception as e:
        bot.reply_to(message, "❌ စနစ်အတွင်း ယာယီချိတ်ဆက်မှု ပြတ်တောက်နေပါသည်။ ခေတ္တစောင့်ဆိုင်းပြီးမှ ပြန်လည်ပေးပို့ပေးပါရန်။")

# Text/Key Handler
@bot.message_handler(func=lambda message: True)
def handle_all_messages(message):
    input_value = message.text.strip()
    chat_id = message.chat.id

    if input_value == "🛒 Plan များ ကြည့်ရန်":
        bot.send_message(chat_id, "🛒 **ကျေးဇူးပြု၍ သင်ဝယ်ယူလိုသော VPN Plan ကို ရွေးချယ်ပေးပါခင်ဗျာ:**", reply_markup=get_plan_keyboard())
        return
        
    if input_value == "📊 Data Usage စစ်ရန်":
        check_guide = (
            "👇 **သင့်ရရှိထားသော VPN Key Link ကို ပို့ပေးပါ:**\n\n"
            "👉 Copy ယူလာတဲ့ `ss://...` နဲ့စတဲ့ Key တစ်ခုလုံးကို ဒီ Chat ထဲသို့ တန်းပြီး Paste ချပို့ပြီး စစ်ဆေးနိုင်ပါတယ်ဗျာ။"
        )
        bot.send_message(chat_id, check_guide, parse_mode="Markdown")
        return

    # ADMIN REPLY BYPASS SYSTEM
    if str(chat_id) == str(ADMIN_CHAT_ID) and message.reply_to_message:
        reply_caption = message.reply_to_message.caption
        if reply_caption and "User Chat ID:" in reply_caption:
            try:
                target_user_id = re.search(r'User Chat ID:\s*`?(\d+)`?', reply_caption).group(1)
                success_message = (
                    f"🎉 **လူကြီးမင်း၏ Ngwelweမှုအား အောင်မြင်စွာ အတည်ပြုပြီးပါပြီဗျာ!**\n\n"
                    f"🔑 **သင်၏ VPN Key လင့်ခ်မှာ အောက်ပါအတိုင်း ဖြစ်ပါသည်:**\n"
                    f"`{input_value}`\n\n"
                    f"👉 အထက်ပါ ကီးလင့်ခ်အား ကော်ပီယူ၍ ဆော့ဖ်ဝဲထဲတွင် ထည့်သွင်းအသုံးပြုနိုင်ပါပြီခင်ဗျာ။ ကျေးဇူးတင်ရှိပါသည်!"
                )
                bot.send_message(target_user_id, success_message, parse_mode="Markdown")
                bot.reply_to(message, "✅ Customer ထံသို့ VPN Key အား အောင်မြင်စွာ လှမ်းပို့ပေးလိုက်ပါပြီဗျာ။")
                return
            except Exception as e:
                bot.reply_to(message, f"❌ ကီးပို့ရာတွင် အမှားအယွင်းရှိပါသည်- {str(e)}")
                return

    if input_value.startswith('/'):
        return

    # Outline API Usage Check
    try:
        keys_resp = requests.get(f"{OUTLINE_API_URL}/access-keys", verify=False, timeout=10)
        metrics_resp = requests.get(f"{OUTLINE_API_URL}/metrics/transfer", verify=False, timeout=10)
        
        keys_data = keys_resp.json().get("accessKeys", [])
        bytes_transferred = metrics_resp.json().get("bytesTransferredByUserId", {})

        target_key = None

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
            except:
                pass

        if not target_key and input_value.startswith("ss://"):
            input_clean = clean_ss_url(input_value)
            for key in keys_data:
                server_access_url = key.get("accessUrl", "")
                if server_access_url:
                    server_clean = clean_ss_url(server_access_url)
                    if input_clean and (input_clean in server_clean or server_clean in input_clean):
                        target_key = key
                        break

        if not target_key:
            match_numeric = re.search(r'^\d+$', input_value)
            if match_numeric:
                for key in keys_data:
                    if str(key.get("id")) == str(match_numeric.group(0)):
                        target_key = key
                        break

        if target_key:
            full_name = target_key.get("name", "HMA User")
            key_id = str(target_key.get("id"))
            display_name = full_name.split("tg")[0].split("Tg")[0].replace("_", " ").strip()
            if not display_name:
                display_name = "HMA Customer"
            
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
            plan_gb = f"{bytes_to_gb(limit_bytes)} GB" if limit_bytes else "Unlimited"
            usage_bytes = bytes_transferred.get(str(key_id), 0)
            usage_gb = bytes_to_gb(usage_bytes)
            
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
