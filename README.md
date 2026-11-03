# Outline Key Bot & Control Center 🤖🔑

H & E FEATURE PREMIUM VPN — Outline VPN Key ရောင်းချခြင်း၊ စီမံခန့်ခွဲခြင်းနှင့် Customer Portal အတွက် Hybrid Platform (Telegram Bot + Vue 3 Admin Web Control Center + Telegram Mini App).

> Architecture: Flask webhook + [pyTelegramBotAPI](https://github.com/eternnoar/pyTelegramBotAPI) + Vue 3 Frontends (Desktop Web Dashboard & Telegram Mini App),
> state များကို Upstash Redis (Vercel KV) တွင်သိမ်းပြီး မရှိပါက `/tmp/*.json` fallback ဖြင့် အလုပ်လုပ်သည်။ Deploy target မှာ **Vercel** (serverless) ဖြစ်သည်။

## ✨ Features

**Customer Side (Bot & Telegram Mini App)**
- Force-join channel gate (`/start` → Verify button)
- Customer Telegram Mini App (TMA): Zero-click HMAC-SHA256 authentication, 1-Click Outline App launch with automatic key import
- Plan ဝယ်ယူခြင်း (Starter → Ultimate, auto key delivery via Outline API)
- Ultimate VIP plan အတွက် key renew / new key ရွေးချယ်မှု
- Wallet system — ငွေဖြည့်ခြင်း (ပြေစာ photo + OCR → Admin approve)
- Loyalty Points & Daily Reward — နေ့စဉ် claim ပြုလုပ်ပြီး Points စုဆောင်းနိုင်ခြင်း, Leaderboard အဆင့်ရပ်တည်မှု
- Redeem code (single / shared mode, ရက်သက်တမ်းပါ bonus credit)
- Data usage စစ်ဆေးခြင်း, ဝယ်ယူမှုမှတ်တမ်း, Key လဲလှယ်တောင်းဆိုခြင်း

**Admin Control Center (Web & Mobile TMA)**
- Vue 3 + Naive UI Dark Theme Dashboard (`dashboard/`): Live Telemetry, Key management, Slip approval queue, Dynamic server settings
- `/deduct`, `/stats`, `/usage`, `/customers` bot commands
- Redeem code generator wizard (amount → mode → days → count)
- Key view / delete, manual key dispatch (custom 5-device plans)
- Key replacement approve/reject, broadcast (text + photo)
- Monthly revenue report, per-server usage stats, purchases history with live SSE refresh

**Ops & Security**
- Nightly cron (`/cron-check`, 23:30 UTC): expiry/GB-full သတိပေးချက် + သက်တမ်းကုန်သော key များ အလိုအလျောက် ဖျက်ခြင်း
- `/myid` — ကိုယ့် Telegram Chat/User ID နှင့် admin status ကို ပြသည်
- Cryptographic HMAC-SHA256 signature verification for Telegram Mini App API (`/api/user/*`)
- Bearer token / Admin credentials authentication for Admin REST API (`/api/admin/*`)
- `GET /diag?key=…` — secret-safe config self-check (README Troubleshooting တွင်)
- Universal entry route (see "Vercel routing" note below)

> ⚠️ **Vercel routing သတိပြုရန်** — ဒီ project ရဲ့ `vercel.json` က request
> တိုင်းကို `/api/index.py` ဆီ rewrite လုပ်တာမို့ **Flask ဆီ PATH_INFO အနေနဲ့
> `/api/index.py` ကိုသာ ရောက်လာပါတယ်** (client ရဲ့ တကယ့် path မဟုတ်)။
> ဒါကြောင့် `bot_app/routes.py` က path-agnostic ဖြစ်အောင် ရေးထားပါတယ်:
> - **POST** (path ဘယ်ဟာဖြစ်ဖြစ်) → Telegram update (webhook)
> - **GET + `User-Agent: vercel-cron/*`** → expiry cron run
> - **REST APIs** (`/api/admin/*`, `/api/user/*`) → Blueprint-based handlers
> - အခြား **GET** တိုင်း → `Bot is running perfectly!` (200)
>
> Cron ကို လက်ဖြင့် run လိုပါက:
> ```bash
> curl -H 'User-Agent: vercel-cron/1.0' https://<your-app>.vercel.app/cron-check
> ```


## 📁 Project Structure

```
index.py                 # Entry shim + local runner (`python index.py`)
api/index.py             # Vercel serverless entry (imports bot_app)
bot_app/
├── __init__.py          # import လုပ်ရုံနဲ့ handlers + routes register ဖြစ်သည်
├── config.py            # Env-first settings (secret များကို env မှသာ)
├── extensions.py        # Flask app + TeleBot singleton
├── routes.py            # /webhook, /health, /cron-check, POST /
├── routes_admin.py      # /api/admin/* (Control Center REST API)
├── routes_user.py       # /api/user/* (Telegram Mini App REST API)
├── keyboards.py         # Reply + inline keyboard factories
├── texts.py             # User-facing message builders
├── utils.py             # Pure helpers + is_user_subscribed
├── timeutil.py          # Myanmar time (UTC+6:30) helpers
├── handlers/            # gate, shop, topup, wallet, redeem, keys,
│                        # history, admin, menu (catch-all), common
├── helpers/             # auth guards (HMAC / Admin), callback_guard, payment_text
├── services/            # billing, orders, outline, notifier, ocr,
│                        # points, reports, registry, states, settings
└── storage/             # kv.py (Upstash REST), paths.py (/tmp fallback), versioning.py
dashboard/               # Vue 3 + Naive UI Admin Control Center
mini_app/                # Vue 3 + Tailwind CSS Customer Telegram Mini App
scripts/                 # set_webhook, cleanup_test_data, restore_from_outline
tests/                   # pytest suite (401 tests, network-free)
.github/workflows/ci.yml # Automated CI (Lint, Backend Tests, Frontend Typecheck & Build)
```

> ⚠️ Handler **import order = registration order** (`bot_app/handlers/__init__.py`).
> TeleBot သည် ပထမဆုံး ကိုက်ညီသော handler ကိုသာ run သောကြောင့်
> `menu.py` (catch-all text router) ကို အမြဲ အလုံးစုံ handler များ ပြီးမှ import ရမည်။

## 🚀 Local Development

### 1. Backend (Python 3.12)

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
`--port` (default `PORT`, 5000), `--webhook-url`, `--remove-webhook`.

### 2. Frontend (Dashboard & Mini App)

```bash
# Admin Control Center (Dashboard)
cd dashboard
npm install
npm run dev               # http://localhost:5173

# Customer Telegram Mini App
cd ../mini_app
npm install
npm run dev               # http://localhost:3000
```

> 🛡️ **Production webhook ကို ကာကွယ်ချက်** — polling mode က Telegram webhook ကို
> ဖျက်ရပါတယ် (မဖျက်ရင် `409 Conflict` တက်တယ်)။ ဒါကြောင့် **webhook အလုပ်လုပ်နေတဲ့
> bot** နဲ့ polling run လုပ်ရင် runner က ငြင်းပြီး ရပ်လိုက်ပါတယ်။ production bot
> ရဲ့ delivery ရပ်မသွားစေရန် local စမ်းသပ်မှုအတွက် **စမ်းသပ် bot token** သုံးပါ
> (ဥပမာ `.env` မှာ `TELEGRAM_TOKEN=<test bot token>`); တကယ်ဖျက်ချင်ရင်
> `--remove-webhook` ကို အတိအလင်း ထည့်ပါ။

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

## 🧪 Tests & Quality Assurance

### Backend Tests & Lint
```bash
pytest -q                                               # 401 tests — network မသုံး (100% passing)
pyflakes index.py api/index.py bot_app/ tests/ scripts/ # zero warnings
```

### Frontend Type-Check & Builds
```bash
cd dashboard && npm run build                           # vue-tsc typecheck + vite build
cd mini_app && npm run build                            # vue-tsc typecheck + standalone bundle
```

CI (`.github/workflows/ci.yml`) တွင် parallel pipelines ဖြင့် အလုပ်လုပ်ပါသည်:
1. **Backend Job**: Syntax check → `pyflakes` linting → `pytest` (401 tests) → `vercel.json` validation
2. **Frontend Job**: `dashboard/` (npm ci + build) → `mini_app/` (npm ci + build + standalone bundle)
3. **Deploy Preview**: Backend နှင့် Frontend နှစ်ခုစလုံး Green ဖြစ်မှသာ Vercel Preview Deploy အလိုအလျောက် ဆက်လက် run ပါသည်။

## 🔐 Security Notes

- Secret များကို **ဘယ်တော့မှ code ထဲ မထည့်ပါနှင့်** — env vars သီးသန့်သုံးပါ။
- Git history ထဲ ယခင် commit ဖြင့် ယိုစိမ့်ခဲ့သည့် token/key များကို
  **@BotFather နှင့် Outline Management API တွင် revoke/regenerate** လုပ်ပါ။
- Outline API URLs သည် management credentials ဖြစ်သည် — လျို့ဝှက်ထားရန် လိုအပ်သည်။

## 🩺 Troubleshooting

| လက္ခဏာ | ဖြေရှင်းနည်း |
|---|---|
| **Admin ခလုတ်များ မပေါ်ခြင်း** (`ADMIN_CHAT_IDS` ထည့်ထားပေမယ့်) | Bot ဆီ `/myid` ပို့ပါ → admin ဖြစ်ရင် "deployment ဖတ်ထားတဲ့ admin IDs" ကို ပြပေးသည်။ `(none)` ပြရင် env var က **deployment ထဲ မရောက်သေး** — Vercel → Settings → Environment Variables တွင် `ADMIN_CHAT_IDS` (Production ✅) ရှိမရှိ စစ်ပြီး **Redeploy** လုပ်ပါ။ ကိုယ့် Chat ID က list ထဲ မပါရင် `/myid` က ပြသည့် Chat ID ကို ထည့်ပါ (ကော်မာ/နေရာလွတ်/ကွက်လပ် `['123']` ပါလည်း ဖတ်နိုင်သည်)။ |
| Admin env var တကယ်ရောက်မရောက် အတိအကျ စစ်လိုခြင်း | `GET /diag?key=<sha256(TELEGRAM_TOKEN)[:16]>` → JSON (`admins`, `admin_ids_masked`, `admin_env_sources`, `kv`, `outline_servers`) ပြန်သည်။ Key မမှန်ရင် သာမန် GET လို ပြုမူသည် (info leak မရှိ)။ |
| Inline button များ တုံ့နှေး/မအလုပ်လုပ် | `python scripts/set_webhook.py check` — `callback_query` ပါစေရန် `set`/`reset` |
| Bot လုံးဝ မတုံ့ပြန် | `python scripts/set_webhook.py check` — webhook URL ရှိမရှိ (မရှိရင် `set`) |
| State များ ပျောက်သွားသည် | Vercel တွင် Redis မချိတ်ရသေး (`/tmp` သည် ephemeral) |
| Cron မ run | Vercel Cron → `vercel.json` (`/cron-check`, 23:30 UTC) စစ်ပါ။ လက်ဖြင့်: `curl -H 'User-Agent: vercel-cron/1.0' https://<app>.vercel.app/cron-check` |
| Key ထုတ်မရ | Outline API URL များ / server online ဖြစ်မှု စစ်ပါ |

### Admin access အလုပ်လုပ်ပုံ

- `ADMIN_CHAT_IDS` = **chat id** များ (ဥပမာ `8778394176,6297145771`)။
  Alias အနေဖြင့် `ADMIN_IDS`, `ADMINS`, `ADMIN_CHAT_ID`, `ADMIN_USER_IDS`,
  `ADMIN_ID` ကိုလည်း ဖတ်သည် (အားလုံး ပေါင်းစည်းသည်)။
- Value ကို **call-time** ဖတ်သည် — import-time snapshot မဟုတ်တာမို့
  ပြောင်းလဲမှု အသစ်ကို ချက်ချင်း တွေ့သည် (သို့သော် Vercel env var အသစ်က
  deployment အသစ် လိုအပ်သည်)။
- Admin သည် force-join gate ကို ကျော်သည်၊ wallet က `♾️` ဖြစ်သည်၊
  `📊 Total Data Usage / 🎟️ Gen RD Code / 💸 ငွေနှုတ်ရန် / 📢 Broadcast`
  ခလုတ်များ ပေါ်လာသည်။
- Cold start တိုင်း Vercel logs တွင် ဒီစာလုံးတစ်ကြောင်း ပေါ်သည် (secret မပါ):
  `[config] admins=2 ids=…4176, …5771 env=ADMIN_CHAT_IDS outline_servers=3 kv=on`


