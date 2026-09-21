"""Payment-slip OCR via OCR.space + transaction-id extraction."""

import random
import re
import string

import requests

from bot_app.config import MY_PAYMENT_PHONES, OCR_API_KEY, TELEGRAM_TOKEN


def parse_slip_ocr(file_path):
    try:
        file_url = f"https://api.telegram.org/file/bot{TELEGRAM_TOKEN}/{file_path}"
        img_resp = requests.get(file_url, timeout=12)
        if img_resp.status_code == 200:
            files = {'file': ('slip.jpg', img_resp.content, 'image/jpeg')}
            payload = {
                'apikey': OCR_API_KEY,
                'language': 'eng',
                'isOverlayRequired': False,
                'OCREngine': '2'
            }
            res = requests.post('https://api.ocr.space/parse/image', files=files, data=payload, timeout=20)
            if res.status_code == 200:
                result = res.json()
                if result.get("IsErroredOnProcessing") == False:
                    parsed_results = result.get("ParsedResults", [])
                    if parsed_results:
                        return parsed_results[0].get("ParsedText", "")
    except Exception as e:
        print("OCR API Error:", e)
    return ""

def clean_ocr_text_thoroughly(text):
    if not text:
        return ""
    mm_map = {
        '၀': '0', '၁': '1', '၂': '2', '၃': '3', '၄': '4',
        '၅': '5', '၆': '6', '၇': '7', '၈': '8', '၉': '9'
    }
    for mm_char, en_char in mm_map.items():
        text = text.replace(mm_char, en_char)
    return text

def extract_transaction_last6(ocr_text):
    if not ocr_text:
        return None
        
    normalized_text = clean_ocr_text_thoroughly(ocr_text)
    for ph in MY_PAYMENT_PHONES:
        normalized_text = normalized_text.replace(ph, "")

    lines = normalized_text.splitlines()
    for i, line in enumerate(lines):
        clean_l = line.replace(" ", "").replace("-", "")
        if any(k in clean_l.lower() for k in ["transaction", "trx", "လုပ်ဆောင်ချက်", "လုပ်ဆောင်မှု", "အိုင်ဒီ", "အမှတ်"]):
            digits = re.findall(r'\d{6,24}', clean_l)
            if digits:
                return digits[0][-6:]
            if i + 1 < len(lines):
                next_l = lines[i+1].replace(" ", "").replace("-", "")
                next_digits = re.findall(r'\d{6,24}', next_l)
                if next_digits:
                    return next_digits[0][-6:]

    kpay_match = re.search(r'\b(010\d{13,20})\b', normalized_text.replace(" ", ""))
    if kpay_match:
        return kpay_match.group(1)[-6:]

    all_numbers = re.findall(r'\b\d{8,15}\b', normalized_text.replace("-", " "))
    for num in all_numbers:
        if not num.startswith("09") and not num.startswith("9699"):
            return num[-6:]

    return None

def generate_order_id_from_slip(file_path=None):
    if file_path:
        ocr_text = parse_slip_ocr(file_path)
        last6 = extract_transaction_last6(ocr_text)
        if last6 and len(last6) == 6:
            return f"#{last6}"
            
    chars = string.ascii_uppercase + string.digits
    rand_part = ''.join(random.choices(chars, k=6))
    return f"#{rand_part}"
