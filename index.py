import os
import requests
from flask import Flask, request, jsonify
import telebot
from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton, ReplyKeyboardMarkup, KeyboardButton, WebAppInfo
import re
import base64
import json
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

# Vercel တွင် Memory Reset ဖြစ်ခြင်းမှ ကာကွယ်ရန် Temp File ဖြင့် Plan သိမ်းဆည်းသည့်စနစ်
STATE_FILE = "/tmp/user_plans.json"

def load_user_plans():
    if os.path.exists(STATE_FILE):
        try:
            with open(STATE_FILE, 'r') as f:
                return json.load(f)
        except:
            return {}
    return {}

def save_user_plan(chat_id, plan_data):
    plans = load_user_plans()
    plans[str(chat_id)] = plan_data
    try:
        with open(STATE_FILE, 'w') as f:
            json.dump(plans, f)
    except:
        pass

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
    # 🌟 Website ခလုတ်ကို ဖြုတ်ပြီး Admin ဆက်သွယ်ရန် ခလုတ်ကို အောက်ခြေအလယ်တွင် ထားရှိခြင်း
    markup = ReplyKeyboardMarkup(resize_keyboard=True, row_width=2)
    btn_buy = KeyboardButton("🛒 Plan များ ကြည့်ရန်")
    btn_check = KeyboardButton("📊 Data Usage စစ်ရန်")
    btn_free = KeyboardButton("🎁 Public Free Key")
    btn_admin = KeyboardButton("👨‍💻 Admin သို့ ဆက်သွယ်ရန်")
    
    markup.add(btn_buy, btn_check)
    markup.add(btn_free)
    markup.add(btn_admin)
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
        "👋 မင်္ဂလာပါ! H & E FEATURE PREMIUM VPN ဝန်ဆောင်မှု Bot မှ ကြိုဆိုပါတယ်။\n\n"
        "👇 အောက်ခြေက Menu Button တွေကို အသုံးပြုပြီး မိမိတို့ အလိုရှိရာကို ရွေးချယ်နိုင်ပါတယ်ခင်ဗျာ।"
    )
    
    try:
        # 📸 စာရိုက်ဘားဘေးတွင် နာမည်အား "Main Website" ဟု ပြောင်းလဲသတ်မှတ်ခြင်း
        bot.set_chat_menu_button(message.chat.id, telebot.types.MenuButtonWebApp(
            type="web_app",
            text="Main Website",
            web_app=WebAppInfo(url="https://h-e.feature.hma.qzz.io"))
        )
    except:
        pass
        
    bot.reply_to(message, welcome_text, reply_markup=get_main_menu_keyboard())

# /buy Command
@bot.message_handler(commands=['buy'])
def send_plans(message):
    bot.reply_to(message, "🛒 ကျေးဇူးပြု၍ ဝယ်ယူလိုသော VPN Plan ကို ရွေးချယ်ပေးပါခင်ဗျာ:", reply_markup=get_plan_keyboard())

# Plan Button Callback
@bot.callback_query_handler(func=lambda call: call.data.startswith("buy_"))
def handle_buy_callback(call):
    plan_code = call.data.replace("buy_", "")
    plan = PLANS.get(plan_code)
    chat_id = call.message.chat.id
    
    if plan:
        # File state ထဲတွင် သေချာစွာ သိမ်းဆည်းခြင်း
        save_user_plan(chat_id, plan)
        
        payment_text = (
            f"✅ သင်ရွေးချယ်ထားသော Plan:\n"
            f"📌 {plan['name']} ({plan['data']}) - {plan['price']}\n\n"
            f"━━━━━━━━━━━━━━━\n"
            f"💰 ငွေလွှဲရမည့် အကောင့်အချက်အလက်များ:\n\n"
            f"📱 KBZ Pay - 09699970092\n"
            f"👤 Htet Myat Aung\n\n"
            f"📱 Wave Pay - 09699970092\n"
            f"👤 Htet Myat Aung\n\n"
            f"📱 AYA Pay - 09699970092\n"
            f"👤 Htet Myat Aung\n\n"
            f"📱 Uab Pay - 09699970092\n"
            f"👤 Htet Myat Aung\n"
            f"━━━━━━━━━━━━━━━\n\n"
            f"🙏🏻 ငွေလွှဲပြီး Screenshotလေး ပို့ပေးပါခင်ဗျာ🥰\n"
            f"(ပြေစာစစ်ဆေးပြီးသည်နှင့် VPN Key ကို အမြန်ဆုံး ပို့ပေးပါမည်။)"
        )
        bot.send_message(chat_id, payment_text)
        bot.answer_callback_query(call.id)

# Screenshot Received
@bot.message_handler(content_types=['photo'])
def handle_payment_screenshot(message):
    chat_id = message.chat.id
    user_name = message.from_user.first_name if message.from_user.first_name else "HMA User"
    username = f"@{message.from_user.username}" if message.from_user.username else "No Username"
    
    # File ထဲမှ Plan ကို လှမ်းထုတ်ယူခြင်း
    user_plans = load_user_plans()
    plan_info = user_plans.get(str(chat_id), {"name": "သတ်မှတ်မထားသော Plan", "data": "မသိရှိပါ", "price": "မသိရှိပါ"})
    
    # 📅 အချိန်ကိုဖြုတ်ပြီး ရက်စွဲသီးသန့်ပဲ ထုတ်ယူခြင်း
    current_date = datetime.fromtimestamp(message.date).strftime("%d/%m/%Y")

    # အစ်ကို့ဆီ ပို့ပေးမည့် သေသပ်လှပသော စာသားပုံစံ
    admin_alert_text = (
        f"💰 ငွေလွှဲပြေစာအသစ်\n"
        f"👤 ဝယ်ယူသူနာမည်: {user_name} ({username})\n"
        f"📦 ရွေးချယ်ထားသော Plan: {plan_info['name']} ({plan_info.get('data', '')})\n"
        f"💵 ကျသင့်ငွေပမာဏ: {plan_info['price']}\n"
        f"📅 ပေးပို့သည့်ရက်စွဲ: {current_date}\n"
        f"🆔 User Chat ID: {chat_id}\n"
        f"📢 ပြေစာရှိ ID ကို သေချာစစ်ဆေးပါ။"
    )
    
    try:
        bot.send_photo(ADMIN_CHAT_ID, message.photo[-1].file_id, caption=admin_alert_text)
        bot.reply_to(message, "⏳ ငွေလွှဲပြေစာအား စစ်ဆေးနေပါသည်။ Admin အတည်ပြုပြီးပါက VPN Key ကို ချက်ချင်းပို့ပေးပါမည်။ ကျေးဇူးတင်ပါသည်ခင်ဗျာ။ 🙏")
    except Exception as e:
        bot.reply_to(message, f"❌ အစ်ကို့ထံ ပို့၍မရပါ - Bot အား အစ်ကို့အကောင့်မှ Start နှိပ်ထားရန် လိုအပ်ပါသည်။")

# Text/Key Handler
@bot.message_handler(func=lambda message: True)
def handle_all_messages(message):
    input_value = message.text.strip()
    chat_id = message.chat.id

    if input_value == "🛒 Plan များ ကြည့်ရန်":
        bot.send_message(chat_id, "🛒  လူကြီးမင်း ဝယ်ယူလိုသော VPN Plan ကို ရွေးချယ်ပေးပါခင်ဗျာ:", reply_markup=get_plan_keyboard())
        return
        
    if input_value == "📊 Data Usage စစ်ရန်":
        check_guide = (
            "👇 ဝယ်ယူထားသော VPN Key ကို ဒီမှာ Paste ချပေးပါ:\n\n"
            " 🫶 Key ကို Copy ယူလာတဲ့ ss://... နဲ့စတဲ့ Key တစ်ခုလုံးကို ဒီ Chat ထဲသို့ တန်းပြီး Paste ချပို့ပြီး စစ်ဆေးနိုင်ပါတယ်ခင်ဗျာ။"
        )
        bot.send_message(chat_id, check_guide)
        return

    # 🎁 Public Free Key ขလုတ်နှိပ်ခြင်း
    if input_value == "🎁 Public Free Key":
        free_key = "ss://Y2hhY2hhMjAtaWV0Zi1wb2x5MTMwNTpFQTVIUmNwYW1odkQyNnY5ZnNBNFgw@h.e.feature.hma.qzz.io:443/?outline=1#🚀🌩️ HMA | Thunder Strike ⚡️"
        free_text = (
            f"🎁 <b>H & E FEATURE PREMIUM VPN မှ လူအများအတွက် 1.5TBအထိ အခမဲ့သုံးစွဲနိုင်သော Premium Key ဖြစ်ပါတယ်ခင်ဗျာ။</b>\n\n"
            f"<code>{free_key}</code>\n\n"
            f"☝️ အပေါ်က ကီးလေးကို <b>တစ်ချက်တည်း နှိပ်လိုက်ရုံဖြင့်</b> Auto Copy ကူးသွားပါလိမ့်မယ်ခင်ဗျာ။"
        )
        bot.send_message(chat_id, free_text, parse_mode="HTML")
        return

    # 👨‍💻 Admin သို့ ဆက်သွယ်ရန် ขလုတ်နှိပ်ခြင်း
    if input_value == "👨‍💻 Admin သို့ ဆက်သွယ်ရန်":
        admin_link_markup = InlineKeyboardMarkup()
        admin_link_markup.add(InlineKeyboardButton("💬 စာပို့ရန် နှိပ်ပါ", url="https://t.me/H_M_A_2026"))
        bot.send_message(chat_id, "👇 အောက်ကခလုတ်ကိုနှိပ်ပြီး Admin ထံ တိုက်ရိုက်စာပို့ ဆက်သွယ်နိုင်ပါပြီဗျာ။", reply_markup=admin_link_markup)
        return

    # ADMIN REPLY BYPASS SYSTEM 
    if str(chat_id) == str(ADMIN_CHAT_ID) and message.reply_to_message:
        reply_caption = message.reply_to_message.caption
        if reply_caption and "User Chat ID:" in reply_caption:
            try:
                target_user_id = re.search(r'User Chat ID:\s*(\d+)', reply_caption).group(1)
                
                success_message = (
                    f"🎉 <b>ငွေလွှဲမှု အောင်မြင်စွာ အတည်ပြုပြီးပါပြီခင်ဗျာ။</b>\n\n"
                    f"🔑 <b>လူကြီးမင်း ဝယ်ယူထားသော VPN Key ကို အောက်တွင် ရယူနိုင်ပါပြီ။</b>\n\n"
                    f"<code>{input_value}</code>\n\n"
                    f"☝️အပေါ်က ကီးကို <b>တစ်ချက်တည်း နှိပ်လိုက်ရုံဖြင့်</b> Auto Copy ကူးသွားပါလိမ့်မယ်ခင်ဗျာ။ ကြိုက်နှစ်သက်ရာ VPN App ထဲသို့ ထည့်သွင်းအသုံးပြုနိုင်ပါပြီခင်ဗျာ။ ကျေးဇူးတင်ရှိပါသည်!"
                )
                bot.send_message(target_user_id, success_message, parse_mode="HTML")
                bot.reply_to(message, "✅ Customer ထံသို့ VPN Keyအား အောင်မြင်စွာ ပို့ပေးလိုက်ပါပြီခင်ဗျာ။")
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