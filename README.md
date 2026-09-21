# Outline Key Bot 🤖🔑

H & E FEATURE PREMIUM VPN — Outline VPN Key ရောင်းခြင်းအတွက် Telegram Bot
(Telegram bot for selling Outline VPN keys: wallet top-up, auto key delivery,
redeem codes, expiry cron, admin reports).

> Architecture: Flask webhook + [pyTelegramBotAPI](https://github.com/eternnoar/pyTelegramBotAPI),
> state များကို Upstash Redis (Vercel KV) တွင်သိမ်းပြီး မရှိပါက `/tmp/*.json`
> fallback ဖြင့် အလုပ်လုပ်သည်။ Deploy target မှာ **Vercel** (serverless) ဖြစ်သည်။

## ✨ Features

**User side**
- Force-join channel gate (`/start` → Verify button)
- Plan ဝယ်ယူခြင်း (Starter → Ultimate, auto key delivery via Outline API)
- Ultimate VIP plan အတွက် key renew / new key ရွေးချယ်မှု
- Wallet system — ငွေဖြည့်ခြင်း (ပြေစာ photo + OCR → Admin approve)
- Redeem code (single / shared mode, ရက်သက်တမ်းပါ bonus credit)
- Data usage စစ်ဆေးခြင်း, ဝယ်ယူမှုမှတ်တမ်း, Key လဲလှယ်တောင်းဆိုခြင်း

**Admin side**
- `/deduct`, `/stats`, `/usage`, `/customers` commands
- Redeem code generator wizard (amount → mode → days → count)
- Key view / delete, manual key dispatch (custom 5-device plans)
- Key replacement approve/reject, broadcast (text + photo)
- Monthly revenue report, per-server usage stats

**Ops**
- Nightly cron (`/cron-check`, 23:30 UTC): expiry/GB-full သတိပေးချက် +
  သက်တမ်းကုန်သော key များ အလိုအလျောက် ဖျက်ခြင်း
- Universal entry route (see "Vercel routing" note below)

> ⚠️ **Vercel routing သတိပြုရန်** — ဒီ project ရဲ့ `vercel.json` က request
> တိုင်းကို `/api/index.py` ဆီ rewrite လုပ်တာမို့ **Flask ဆီ PATH_INFO အနေနဲ့
> `/api/index.py` ကိုသာ ရောက်လာပါတယ်** (client ရဲ့ တကယ့် path မဟုတ်)။
> ဒါကြောင့် `bot_app/routes.py` က path-agnostic ဖြစ်အောင် ရေးထားပါတယ်:
> - **POST** (path ဘယ်ဟာဖြစ်ဖြစ်) → Telegram update (webhook)
> - **GET + `User-Agent: vercel-cron/*`** → expiry cron run
> - အခြား **GET** တိုင်း → `Bot is running perfectly!` (200)
>
> Cron ကို လက်ဖြင့် run လိုပါက:
> ```bash
> curl -H 'User-Agent: vercel-cron/1.0' https://<your-app>.vercel.app/cron-check
> ```


## 📁 Project Structure

```
index.py              # Entry shim + local runner (`python index.py`)
api/index.py          # Vercel serverless entry (imports bot_app)
bot_app/
├── __init__.py       # import လုပ်ရုံနဲ့ handlers + routes register ဖြစ်သည်
├── config.py         # Env-first settings (secret များကို env မှသာ)
├── extensions.py     # Flask app + TeleBot singleton
├── routes.py         # /webhook, /health, /cron-check, POST /
├── keyboards.py      # Reply + inline keyboard factories
├── texts.py          # User-facing message builders
├── utils.py          # Pure helpers + is_user_subscribed
├── timeutil.py       # Myanmar time (UTC+6:30) helpers
├── handlers/         # gate, shop, topup, wallet, redeem, keys,
│                     # history, admin, menu (catch-all), common
├── helpers/          # callback_guard (dedup), payment_text
├── services/         # billing, orders, outline, notifier, ocr,
│                     # reports, registry, states
└── storage/          # kv.py (Upstash REST), paths.py (/tmp fallback)
scripts/set_webhook.py  # Webhook check/set/reset manager
tests/                  # pytest suite (network-free)
.github/workflows/ci.yml
```

> ⚠️ Handler **import order = registration order** (`bot_app/handlers/__init__.py`).
> TeleBot သည် ပထမဆုံး ကိုက်ညီသော handler ကိုသာ run သောကြောင့်
> `menu.py` (catch-all text router) ကို အမြဲ အလုံးစုံ handler များ ပြီးမှ import ရမည်။

## 🚀 Local Development

Python **3.12** (repo တွင် `.python-version` ပါဝင်သည်):

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt -r requirements-dev.txt

cp .env.example .env      # တန်ဖိုးအစစ်များ ထည့်ပါ
python index.py           # polling mode (local test အလွယ်ဆုံး)
```

Webhook mode ဖြင့် local run လုပ်လိုပါက:

```bash
python index.py --mode webhook --port 5000 --webhook-url https://<public-url>/webhook
```

Options: `--mode polling|webhook` (default ကို `BOT_MODE` env ဖြင့်လည်း ထိန်းနိုင်),
`--port` (default `PORT`, 5000), `--webhook-url`.

Local တွင် `KV_REST_API_URL/TOKEN` မထည့်ထားပါက state များ `/tmp/*.json` တွင်
သိမ်းသည် (serverless filesystem မဟုတ်သောကြောင့် Vercel တွင် Redis မဖြစ်မနေလိုအပ်)။

## ☁️ Vercel Deployment

1. Repo ကို Vercel သို့ connect လုပ်ပါ (`vercel.json` တွင် `api/index.py` function,
   rewrite အားလုံး, daily cron ပြီးသား)။
2. **Upstash Redis** (Vercel Marketplace သို့မဟုတ် Upstash console) ချိတ်ပါ —
   `KV_REST_API_URL` + `KV_REST_API_TOKEN` env vars အလိုအလျောက် ရသည်။
3. **Environment Variables** တင်ပါ (**မဖြစ်မနေ** — code ထဲမှာ hardcoded
   fallback မရှိတော့ပါ။ မထည့်ထားရင် bot က dummy token နဲ့ run နေပြီး
   စာတွေကို တုံ့ပြန်မှာ မဟုတ်ပါ):

   | Variable | ရှင်းလင်းချက် |
   |---|---|
   | `TELEGRAM_TOKEN` | @BotFather မှ token (**မဖြစ်မနေ**) |
   | `REQUIRED_CHANNEL` | Force-join channel (`@channel`) |
   | `ADMIN_CHAT_IDS` | Comma-separated admin Telegram IDs |
   | `OUTLINE_API_URL_1..3` | Outline server Management API URLs |
   | `OCR_API_KEY` | [ocr.space](https://ocr.space) API key (ပြေစာဖတ်ရန်) |
   | `MY_PAYMENT_PHONES` | ကိုယ်ပိုင်အကောင့်ဖုန်းနံပါတ်များ (OCR filter) |
   | `KV_REST_API_URL/TOKEN` | Upstash Redis (Vercel KV integration နဲ့ auto) |
   | `BOT_MODE`, `PORT`, `WEBHOOK_URL` | local run အတွက်သာ |

   > 💡 Env var တင်ပြီးတိုင်း **Redeploy** လုပ်ရပါမယ် (Vercel က env အသစ်ကို
   > deployment အသစ်မှာသာ ထည့်ပေးတာမို့) — Dashboard → Deployments →
   > ⋯ → Redeploy။

4. Webhook ချိတ်ပါ (domain deploy ပြီးမှ):

   ```bash
   export TELEGRAM_TOKEN=... WEBHOOK_URL=https://<your-app>.vercel.app/webhook
   python scripts/set_webhook.py check   # လက်ရှိ အခြေအနေ စစ်ဆေး
   python scripts/set_webhook.py set     # allowed_updates အပြည့်ဖြင့် set
   python scripts/set_webhook.py reset   # ပျက်နေလျှင် delete + set
   ```

   `check` သည် `allowed_updates` ထဲ `callback_query` ပါ/မပါ (inline button
   များ သေဆုံးနေတဲ့ ယခင် incident ကာကွယ်ချက်)၊ URL ကိုက်ညီမှု၊ pending
   updates, delivery error တို့ကို စစ်ပြပေးသည်။ Exit code: 0 = OK, 1 = FAIL,
   2 = usage error။ Token ကို output မှာ မပြပါ။

> ℹ️ Webhook URL ကို bare domain (`https://app.vercel.app/`) အဖြစ်လည်း
> ထားနိုင်သည် — `POST /` ကို webhook အဖြစ် လက်ခံထားသည်။

## 🧪 Tests & Lint

```bash
pytest -q          # 37 tests — network မသုံး (Telegram/Outline mocked)
pyflakes index.py api/index.py bot_app/ tests/ scripts/
```

CI (`.github/workflows/ci.yml`) တွင် syntax check → pyflakes → pytest →
vercel.json validation → (PR) preview deploy ပါသည်။ Tests များသည် secrets
မလိုအပ်ဘဲ run ရသည် (tests/conftest.py မှ safe defaults ထည့်ပေးသည်)။

## 🔐 Security Notes

- Secret များကို **ဘယ်တော့မှ code ထဲ မထည့်ပါနှင့်** — env vars သီးသန့်သုံးပါ။
- Git history ထဲ ယခင် commit ဖြင့် ယိုစိမ့်ခဲ့သည့် token/key များကို
  **@BotFather နှင့် Outline Management API တွင် revoke/regenerate** လုပ်ပါ။
- Outline API URLs သည် management credentials ဖြစ်သည် — လျို့ဝှက်ထားရန် လိုအပ်သည်။

## 🩺 Troubleshooting

| လက္ခဏာ | ဖြေရှင်းနည်း |
|---|---|
| Inline button များ တုံ့နှေး/မအလုပ်လုပ် | `python scripts/set_webhook.py check` — `callback_query` ပါစေရန် `set`/`reset` |
| State များ ပျောက်သွားသည် | Vercel တွင် Redis မချိတ်ရသေး (`/tmp` သည် ephemeral) |
| Cron မ run | Vercel Cron → `vercel.json` (`/cron-check`, 23:30 UTC) စစ်ပါ |
| Key ထုတ်မရ | Outline API URL များ / server online ဖြစ်မှု စစ်ပါ |

