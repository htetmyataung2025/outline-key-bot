"""Payment-slip OCR via OCR.space + transaction-id extraction."""

import base64
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


# ---------------------------------------------------------------------------
# Slip amount extraction (Bot Update #20)
#
# Customers pick the top-up amount BEFORE uploading the slip, and many pick
# the wrong one (e.g. select 1,000 Ks, send a 5,000 Ks slip). The slip photo
# itself is the truth, so at intake the OCR text is also mined for the
# transfer amount and — when one is confidently read — it replaces the
# customer-selected amount on the recorded slip.
# ---------------------------------------------------------------------------

AMOUNT_LABELS = [
    "amount", "total", "ပမာဏ", "ငွေပမာဏ", "လွှဲငွေ", "ပေးချေ",
]

_MONEY_TOKEN_RE = re.compile(r"\d[\d,]*\d(?:\.\d{1,2})?|\d(?:\.\d{1,2})?")
_CURRENCY_RE = re.compile(r"(?:ks|mmk|ကျပ်)", re.IGNORECASE)


def _money_value(token):
    """Parse one OCR number token into an int Ks amount, or None.

    Accepts comma-grouped ("4,000.00"), decimal ("4000.00") and plain
    round numbers ("5000"). Rejects fragments of dates, times, phone
    numbers and transaction references: those are either too long, not
    round, or outside the plausible top-up range.
    """
    token = (token or "").strip()
    if not token:
        return None
    has_comma = "," in token
    has_decimal = "." in token
    try:
        value = float(token.replace(",", ""))
    except ValueError:
        return None
    if value != int(value):
        return None
    amount = int(value)
    if amount < 100 or amount > 1_000_000:
        return None
    int_part = token.replace(",", "").split(".")[0]
    if len(int_part) > 7:
        return None  # phone numbers / transaction references
    if not (has_comma or has_decimal or amount % 100 == 0):
        return None  # bare non-round numbers are usually dates / ids
    return amount


def _amounts_in_line(line):
    out = []
    for m in _MONEY_TOKEN_RE.finditer(line):
        v = _money_value(m.group(0))
        if v is not None:
            out.append(v)
    return out


def extract_slip_amount(ocr_text):
    """Best-effort transfer amount (int Ks) from slip OCR text, or None."""
    if not ocr_text:
        return None
    text = clean_ocr_text_thoroughly(ocr_text)
    for ph in MY_PAYMENT_PHONES:
        text = text.replace(ph, "")
    lines = text.splitlines()

    # 1) Label-anchored: the amount printed next to an amount label, or on
    #    the line directly under it (some receipts stack label and value).
    for i, line in enumerate(lines):
        lowered = line.lower()
        if "balance" in lowered:
            continue  # a balance line is never the transfer amount
        if any(lbl in lowered for lbl in AMOUNT_LABELS):
            vals = _amounts_in_line(line)
            if vals:
                return vals[0]
            if i + 1 < len(lines):
                vals = _amounts_in_line(lines[i + 1])
                if vals:
                    return vals[0]

    # 2) Currency-anchored: numbers sitting next to Ks / MMK / ကျပ်.
    anchored = []
    for line in lines:
        for m in _MONEY_TOKEN_RE.finditer(line):
            window = line[max(0, m.start() - 4): m.end() + 5]
            if _CURRENCY_RE.search(window):
                v = _money_value(m.group(0))
                if v is not None:
                    anchored.append(v)
    if anchored:
        # Most repeated value wins; ties go to the first one seen.
        return max(set(anchored), key=lambda v: (anchored.count(v), -anchored.index(v)))
    return None


def parse_slip_ocr_bytes(img_bytes):
    """OCR raw image bytes via OCR.space (base64), same engine as slips."""
    if not img_bytes:
        return ""
    try:
        payload = {
            'apikey': OCR_API_KEY,
            'base64Image': "data:image/jpeg;base64," + base64.b64encode(img_bytes).decode(),
            'language': 'eng',
            'isOverlayRequired': False,
            'OCREngine': '2',
        }
        res = requests.post('https://api.ocr.space/parse/image', data=payload, timeout=20)
        if res.status_code == 200:
            result = res.json()
            if result.get("IsErroredOnProcessing") == False:
                parsed_results = result.get("ParsedResults", [])
                if parsed_results:
                    return parsed_results[0].get("ParsedText", "")
    except Exception as e:
        print("OCR API Error (bytes):", e)
    return ""


# ---------------------------------------------------------------------------
# Slip-photo gate (Bot Update #21)
#
# Some customers upload a photo that is not a payment slip at all (an app
# install screenshot, a random picture) — usually because something else
# went wrong and the top-up upload is the only photo channel they find.
# Those photos used to land in the admin review queue as fake slips. The
# gate checks the OCR text of every slip photo for ANY sign of a real
# wallet receipt — a transaction reference, a transfer amount, the
# shop's own receiving number/name, or a wallet brand (KBZ / Wave / AYA /
# CB / UAB). The check is deliberately generous: a photo is bounced only
# when NOTHING slip-like is found, so a genuine but blurry receipt still
# passes (and each flow offers an explicit "this IS a real slip" escape
# hatch that records it flagged as unverified).
# ---------------------------------------------------------------------------

SLIP_BRAND_MARKERS = (
    "kbz", "kpay", "wave", "aya", "cbpay", "cb pay", "uab", "onepay",
)

# Shown when a photo is bounced by the gate. The bot variant (HTML) is
# paired with an inline "this IS a real slip" button; the plain variant
# goes into the app / Mini App JSON responses.
NOT_A_SLIP_NOTICE_BOT = (
    "⚠️ <b>ဒီပုံက ငွေလွှဲပြေစာ မဟုတ်ပါဘူး ခင်ဗျာ။</b>\n\n"
    "KBZ Pay / Wave Pay / AYA Pay စတဲ့ Pay app ထဲက ငွေလွှဲ ပြီးသား "
    "ပြေစာ ပုံကို ပို့ပေးပါ။\n\n"
    "ပြေစာ အစစ် ဖြစ်ပြီး ပုံ မှုန်နေလို့ စနစ်က ဖတ်မရတာဆိုရင် "
    "အောက်က ခလုတ်ကို နှိပ်ပြီး Admin စစ်ပေးဖို့ ပို့နိုင်ပါတယ်။"
)

NOT_A_SLIP_MESSAGE = (
    "ဒီပုံက ငွေလွှဲပြေစာ မဟုတ်ပါဘူး ခင်ဗျာ။ KBZ Pay / Wave Pay / AYA Pay "
    "ထဲက ငွေလွှဲ ပြီးသား ပြေစာ ပုံကို ပို့ပေးပါ။ ပြေစာ အစစ် ဖြစ်ပါက "
    "Telegram Bot (@H_E_FEATURE_Bot) မှတစ်ဆင့် ပြန်ပို့နိုင်ပါတယ်။"
)


def slip_photo_is_probable(ocr_text):
    """True when the OCR text shows ANY sign of a real payment slip."""
    if not ocr_text:
        return False
    if extract_transaction_last6(ocr_text):
        return True
    if extract_slip_amount(ocr_text) is not None:
        return True
    cleaned = clean_ocr_text_thoroughly(ocr_text)
    squashed = cleaned.replace(" ", "").replace("-", "")
    for ph in MY_PAYMENT_PHONES:
        digits = re.sub(r"\D", "", str(ph))
        if digits and digits in squashed:
            return True
    lowered = cleaned.lower()
    if "htet myat aung" in lowered:
        return True
    return any(marker in lowered for marker in SLIP_BRAND_MARKERS)


def extract_slip_facts(file_path=None):
    """One OCR pass returning ``(order_id, tx_last6, amount, probable)``.

    ``amount`` is the transfer amount read off the slip (int Ks) or None
    when OCR could not read one confidently. ``probable`` is the Bot
    Update #21 gate verdict: whether the photo looks like a payment
    slip at all.
    """
    ocr_text = parse_slip_ocr(file_path) if file_path else ""
    amount = extract_slip_amount(ocr_text)
    last6 = extract_transaction_last6(ocr_text)
    probable = slip_photo_is_probable(ocr_text)
    if last6 and len(last6) == 6:
        return f"#{last6}", last6, amount, probable
    chars = string.ascii_uppercase + string.digits
    rand_part = ''.join(random.choices(chars, k=6))
    return f"#{rand_part}", "", amount, probable


def extract_amount_and_tx_from_bytes(img_bytes):
    """``(tx_last6, amount, probable)`` for flows that receive raw bytes."""
    ocr_text = parse_slip_ocr_bytes(img_bytes)
    if not ocr_text:
        return "", None, False
    return (
        extract_transaction_last6(ocr_text) or "",
        extract_slip_amount(ocr_text),
        slip_photo_is_probable(ocr_text),
    )


def resolve_slip_amount(selected, detected):
    """Decide the amount to record for a slip: ``(final_amount, status)``.

    Status ``"ocr"`` — OCR read the slip; its amount wins (this is the
    auto-fill that stops a wrong customer selection being recorded).
    Status ``"selected"`` — OCR found nothing trustworthy; keep the
    customer's amount and let the admin/agent verify from the photo.
    A detected amount under the 500 Ks minimum top-up is never trusted:
    an OCR misread must not silently shrink a customer's slip.
    """
    try:
        selected = int(selected or 0)
    except (TypeError, ValueError):
        selected = 0
    if detected is not None and detected >= 500:
        return detected, "ocr"
    return selected, "selected"


def extract_order_id_and_tx(file_path=None):
    """Return ``(order_id, tx_last6)``.

    ``tx_last6`` is the transaction reference the id was derived from
    (empty string when the id fell back to random) so the dashboard can
    show and audit what OCR actually read.
    """
    order_id, tx_last6, _amount, _probable = extract_slip_facts(file_path)
    return order_id, tx_last6


def generate_order_id_from_slip(file_path=None):
    return extract_order_id_and_tx(file_path)[0]
