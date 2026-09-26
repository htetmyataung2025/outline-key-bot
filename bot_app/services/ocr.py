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

# Labels that mark the transaction-reference line on KBZPay / Wave Money /
# AYA Pay / CB receipts — English and Burmese variants the OCR tends to emit.
TX_KEYWORDS = [
    "transaction", "trx", "txn", "reference", "ref", "receipt", "invoice",
    "statement", "လုပ်ဆောင်ချက်", "လုပ်ဆောင်မှု", "ကိုးကား", "အတည်ပြုကုဒ်", "အမှတ်",
]

# Myanmar mobile numbers: 09 + 7-9 digits, or 94-99 + 6-9 digits. The bare
# fallback must never mistake one for a transaction id (that produced ids
# like #912520 taken from the recipient phone line).
_PHONE_LIKE = re.compile(r'^0?9[4-9]\d{6,9}$')
# 8-digit dates DDMMYYYY / YYYYMMDD (e.g. "29/08/2026" after dash cleanup).
_DATE_LIKE = re.compile(
    r'^(?:[0-2]?\d|3[01])(?:0[1-9]|1[0-2])(?:19|20)\d{2}$'
    r'|^(?:19|20)\d{2}(?:0[1-9]|1[0-2])(?:[0-2]?\d|3[01])$'
)


def _digits_after_keyword(clean_line):
    """Digits that appear AFTER the keyword inside one cleaned line.

    Position-aware so a phone number sitting before the label on the same
    line ("Receiver 09xxx Transaction 112233445566") is not picked up.
    """
    lowered = clean_line.lower()
    for kw in TX_KEYWORDS:
        idx = lowered.find(kw)
        if idx != -1:
            digits = re.findall(r'\d{6,24}', clean_line[idx + len(kw):])
            if digits:
                return digits[0][-6:]
    return None


def extract_transaction_last6(ocr_text):
    if not ocr_text:
        return None

    normalized_text = clean_ocr_text_thoroughly(ocr_text)
    for ph in MY_PAYMENT_PHONES:
        normalized_text = normalized_text.replace(ph, "")

    lines = normalized_text.splitlines()
    for i, line in enumerate(lines):
        clean_l = line.replace(" ", "").replace("-", "")
        hit = _digits_after_keyword(clean_l)
        if hit:
            return hit
        if any(k in clean_l.lower() for k in TX_KEYWORDS) and i + 1 < len(lines):
            next_l = lines[i + 1].replace(" ", "").replace("-", "")
            next_digits = re.findall(r'\d{6,24}', next_l)
            if next_digits:
                return next_digits[0][-6:]

    # KBZPay statement refs start with "010" and are 15-23 digits long.
    kpay_match = re.search(r'(?<!\d)(010\d{12,20})(?!\d)', normalized_text.replace(" ", ""))
    if kpay_match:
        return kpay_match.group(1)[-6:]

    # Last resort: first long digit run that is not a phone number or a date.
    for num in re.findall(r'(?<!\d)\d{8,15}(?!\d)', normalized_text.replace("-", " ")):
        if _PHONE_LIKE.match(num) or _DATE_LIKE.match(num):
            continue
        return num[-6:]

    return None


def extract_order_id_and_tx(file_path=None):
    """Return ``(order_id, tx_last6)``.

    ``tx_last6`` is the transaction reference the id was derived from
    (empty string when the id fell back to random) so the dashboard can
    show and audit what OCR actually read.
    """
    if file_path:
        ocr_text = parse_slip_ocr(file_path)
        last6 = extract_transaction_last6(ocr_text)
        if last6 and len(last6) == 6:
            return f"#{last6}", last6

    chars = string.ascii_uppercase + string.digits
    rand_part = ''.join(random.choices(chars, k=6))
    return f"#{rand_part}", ""


def generate_order_id_from_slip(file_path=None):
    return extract_order_id_and_tx(file_path)[0]
