# Free Deployment & Setup Roadmap ($0/Month)

## 1. Prerequisites Checklist
- [ ] GitHub Account (for repository & automatic deployment)
- [ ] Supabase Account (Free Tier: 500 MB PostgreSQL)
- [ ] Vercel Account (Free Hobby Tier: Serverless & Static hosting)
- [ ] Telegram Bot Token (from @BotFather)

---

## 2. Step-by-Step Implementation Roadmap

### Step 1: Database Setup (Supabase)
1. Go to [supabase.com](https://supabase.com) and create a new project (e.g. `outline-key-control`).
2. Open the **SQL Editor** in the Supabase Dashboard.
3. Paste and run the DDL migration script from [`01_DATABASE_SCHEMA.md`](file:///home/zixuan/Projects/outline-key-bot/memory/01_DATABASE_SCHEMA.md).
4. Copy the following credentials from **Project Settings > API**:
   - `SUPABASE_URL`
   - `SUPABASE_KEY` (service_role or anon key)
   - Connection string (PostgreSQL URI)

---

### Step 2: Backend API Implementation
1. Add FastAPI/Flask REST endpoints to handle `/api/admin/*` routes.
2. Implement Telegram `initData` signature validation middleware.
3. Connect bot order/key delivery events to record directly into the Supabase database.
4. Deploy the backend to Vercel (or configure within the existing `api/index.py`).

---

### Step 3: Frontend Build (Vue 3 + Naive UI)
1. Initialize Vite project:
   ```bash
   npm create vite@latest dashboard -- --template vue-ts
   cd dashboard
   npm install naive-ui vicons chart.js vue-chartjs pinia axios @vueuse/core
   ```
2. Implement components and dark theme overrides following [`03_UI_UX_SPECIFICATION.md`](file:///home/zixuan/Projects/outline-key-bot/memory/03_UI_UX_SPECIFICATION.md).
3. Connect API calls to backend endpoints.
4. Add the Telegram WebApp script to `index.html`:
   ```html
   <script src="https://telegram.org/js/telegram-web-app.js"></script>
   ```
5. Deploy Frontend to Vercel:
   ```bash
   vercel --prod
   ```
   *(Resulting in a public URL such as `https://outline-admin.vercel.app`)*

---

### Step 4: Telegram Mini App Integration (@BotFather)
To make the dashboard open inside Telegram with 1 tap:

1. Open Telegram and message **@BotFather**.
2. Send command: `/mybots` -> Select your bot.
3. Select **Bot Settings** -> **Menu Button** -> **Configure menu button**.
4. Set the URL to your deployed frontend:
   ```text
   https://outline-admin.vercel.app
   ```
5. Set the Button Title:
   ```text
   Control Center
   ```
*(Now, an "Open" or "Control Center" button will appear next to the message input box in Telegram!)*

---

## 3. Environment Variables Reference

| Variable Name | Example Value | Description |
|---|---|---|
| `TELEGRAM_TOKEN` | `1234567890:AAEa...` | Bot token for webhook & TMA HMAC verification |
| `ADMIN_CHAT_IDS` | `8778394176,6297145771` | Authorized Telegram IDs allowed to access dashboard |
| `SUPABASE_URL` | `https://xyz.supabase.co` | Supabase project API URL |
| `SUPABASE_KEY` | `eyJh...` | Supabase service_role or secret API key |
| `OUTLINE_API_URL_1` | `https://ip:port/secret` | Server 1 management API endpoint |
| `OUTLINE_API_URL_2` | `https://ip:port/secret` | Server 2 management API endpoint |
| `OUTLINE_API_URL_3` | `https://ip:port/secret` | Server 3 management API endpoint |
| `ADMIN_SECRET_KEY` | `random_32_char_hex` | Fallback secret for desktop browser login |
