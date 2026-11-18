# Outline Key Bot Control Center — Memory & Architecture Index

This directory contains the complete technical blueprints, database schemas, API contracts, UI/UX guidelines, and free deployment roadmaps for the **Outline Key Bot Control Center** (Hybrid Web Dashboard & Telegram Mini App).

## 📚 Documentation Index

1. [**00_ARCHITECTURE_OVERVIEW.md**](file:///home/zixuan/Projects/outline-key-bot/memory/00_ARCHITECTURE_OVERVIEW.md)
   - High-level system architecture diagram
   - Full technology stack justification (Vue 3, Naive UI, Python, Supabase, Vercel)
   - Dual-mode (Desktop Web + Mobile Telegram Mini App) behavior
   - Zero-click cryptographic authentication via Telegram `initData`

2. [**01_DATABASE_SCHEMA.md**](file:///home/zixuan/Projects/outline-key-bot/memory/01_DATABASE_SCHEMA.md)
   - Entity-Relationship Diagram (ERD)
   - Complete PostgreSQL DDL migration script for Supabase
   - Tables: `users`, `servers`, `keys`, `orders`, `slips`, `redeem_codes`, `redeem_histories`, `audit_logs`

3. [**02_API_SPECIFICATION.md**](file:///home/zixuan/Projects/outline-key-bot/memory/02_API_SPECIFICATION.md)
   - Telegram WebApp HMAC-SHA256 signature verification code
   - Endpoints for live telemetry overview, key management, slip approvals, redeem code generation, customer balances, and audit trails

4. [**03_UI_UX_SPECIFICATION.md**](file:///home/zixuan/Projects/outline-key-bot/memory/03_UI_UX_SPECIFICATION.md)
   - Design tokens modeled after OpsTranslate dark theme aesthetics
   - Naive UI component hierarchy and theme overrides
   - Responsive breakpoints (Desktop wide data tables vs Mobile card-lists & haptic feedback)

5. [**04_FREE_DEPLOYMENT_ROADMAP.md**](file:///home/zixuan/Projects/outline-key-bot/memory/04_FREE_DEPLOYMENT_ROADMAP.md)
   - Zero-cost ($0/month) deployment guide
   - Supabase project initialization
   - Frontend Vite + Vercel setup
   - Telegram BotFather Menu Button configuration guide

6. [**05_POINTS_SYSTEM_PLAN.md**](file:///home/zixuan/Projects/outline-key-bot/memory/05_POINTS_SYSTEM_PLAN.md)
   - FUTURE PLAN (design locked, not yet built): Points / Daily Reward system
   - Locked economics (5,000 pts = Starter, 20,000 cap, 4h cooldown, reward table)
   - KV data model, integration surface (bot + top-up hook + admin dashboard), concurrency, phased build plan


7. [**2026-09-25_PROGRESS.md**](file:///home/zixuan/Projects/outline-key-bot/memory/2026-09-25_PROGRESS.md)
   - Daily progress log, active execution plan, milestones, and test suite verification

8. [**2026-09-26_PROGRESS.md**](file:///home/zixuan/Projects/outline-key-bot/memory/2026-09-26_PROGRESS.md)
   - Daily progress log (dashboard deploy/promote, webhook fixes, three-bot token cleanup, perf & OCR diagnoses)

9. [**2026-09-27_PROGRESS.md**](file:///home/zixuan/Projects/outline-key-bot/memory/2026-09-27_PROGRESS.md)
   - Incident log: prod webhook re-pointed to site root (405) — local run ruled out, fixed via `scripts/set_webhook.py reset`

10. [**2026-09-28_PROGRESS.md**](file:///home/zixuan/Projects/outline-key-bot/memory/2026-09-28_PROGRESS.md)
   - Settings-configurable Points system (§9) implemented: config resolver + master toggle, strict POST validation, SettingsView "🎁 Loyalty Points" tab, 281 tests passing

11. [**2026-09-29_PROGRESS.md**](file:///home/zixuan/Projects/outline-key-bot/memory/2026-09-29_PROGRESS.md)
   - Full DB purge of @fafafa1721 (7672856636): reusable probe + purge scripts, 8 KV stores cleaned (wallet, purchases, slips, key mapping, profile, audit logs), backup kept gitignored, 332 tests passing

12. [**2026-09-30_PROGRESS.md**](file:///home/zixuan/Projects/outline-key-bot/memory/2026-09-30_PROGRESS.md)
   - Server 4 routing bug fixed: hard-coded ternary chains replaced with `resolve_server_api_url`/`iter_configured_server_urls` (dynamic Settings store source of truth + env-1-2-3 fallback). Key issuance, renew, search, usage report, notifier, and admin/key handlers now address all configured servers. Replace-to buttons in menu.py are generated dynamically. 8 regression tests added; 340 tests passing.

13. [**2026-10-01_PROGRESS.md**](file:///home/zixuan/Projects/outline-key-bot/memory/2026-10-01_PROGRESS.md)
   - "Removed Server 3 still shows in bot" fixed: plan-purchase buttons + monthly revenue report now follow the Settings store (`get_server_display_name` helper), legacy removed-server revenue stays visible via history fallback. 9 regression tests added; 349 tests passing.

14. [**2026-10-02_PROGRESS.md**](file:///home/zixuan/Projects/outline-key-bot/memory/2026-10-02_PROGRESS.md)
   - Dashboard "Purchases History" live view added on branch `feat/purchases-history`: unified `GET /api/admin/purchases` (merges sales_history + user_purchases_data), PurchasesView with summary cards / day-window chips / search / server filter / detail modal / mobile card list + SSE live refresh. 5 new tests; 369 passing; browser-verified locally.

15. [**2026-10-03_PROGRESS.md**](file:///home/zixuan/Projects/outline-key-bot/memory/2026-10-03_PROGRESS.md)
   - Option A (Vercel Fluid usage cut): SSE disabled in production builds (dev keeps push), version-poll 15s→30s, keys/overview probe TTLs 30s→120s, function memory 1766→1024 MB. Projected 225→~50-80 GB-Hrs/month. 381 tests passing.

16. [**2026-10-06_PROGRESS.md**](file:///home/zixuan/Projects/outline-key-bot/memory/2026-10-06_PROGRESS.md)
   - Dead "Main Website" menu button removed: `LANDING_URL` deleted from config, customers now reset to Telegram `MenuButtonDefault()` on `/start` (unpins the dead pill), admin `🎛 Control` button unchanged. New `test_start_sets_default_menu_button_for_customers`; 381 tests passing. Deploy pending (owner step).

17. [**2026-10-17_PROGRESS.md**](file:///home/zixuan/Projects/outline-key-bot/memory/2026-10-17_PROGRESS.md)
   - Customer Telegram Mini App (TMA) Phase 1: Cryptographic HMAC-SHA256 user authentication (`@require_user_api`), `/api/user/*` Blueprint (`bootstrap`, `claim-daily`, `purchase`, `topup-slip`, `replace`, `history`, `leaderboard`), 13 new hermetic tests added. 394/394 tests passing (100% green, zero regressions).

18. [**2026-10-18_PROGRESS.md**](file:///home/zixuan/Projects/outline-key-bot/memory/2026-10-18_PROGRESS.md)
   - Customer Telegram Mini App Hardcoded Data Elimination & Real Data Synchronization: Completely removed all mock/demo purchases, fake leaderboard users, and mock state defaults. Wired live backend formatting, honest Burmese empty states ("ဝယ်ယူမှုမှတ်တမ်း မရှိသေးပါ", "ဦးဆောင်သူစာရင်း မရှိသေးပါ"), and 1-click Outline App direct launching with automatic key import. 399/399 tests passing (100% green).

19. [**2026-11-03_PROGRESS.md**](file:///home/zixuan/Projects/outline-key-bot/memory/2026-11-03_PROGRESS.md)
   - Quality Assurance & Codebase Stabilization: Cleaned all Python lint (`pyflakes`) warnings in `bot_app`, `tests`, and `scripts`. Modernized Mini App Playwright test assertions (`mini_app/tests/mini-app.spec.ts`) to match live empty states and real-data APIs. Enhanced GitHub Actions CI with a parallel `frontend` job (Dashboard & Mini App typecheck/build). Synchronized `README.md` to reflect 401 tests and hybrid architecture. 401/401 backend tests passing (100% green).

20. [**2026-11-11_PROGRESS.md**](file:///home/zixuan/Projects/outline-key-bot/memory/2026-11-11_PROGRESS.md)
   - Customer Telegram Mini App Complete Audit & 7-Issue Resolution: Fixed 1-click purchase response contract (`remaining_balance`, `key_details`, manual 5-device plan workflow, bonus server-1 rule), real-time Outline usage (`used` GB) + `persistent_keys_registry` fallback, dynamic plan quota labels (`Unlimited Data`), actionable admin inline buttons on key replacement requests, Starter Plan points redemption (`POST /api/user/redeem-points`), promo/gift code redemption (`POST /api/user/redeem-code`), unified `/app/*` Vercel hosting in `vercel.json`, and Upstash token cleanup. 406/406 backend tests and 13/13 Playwright E2E tests passing.

21. [**2026-11-12_PROGRESS.md**](file:///home/zixuan/Projects/outline-key-bot/memory/2026-11-12_PROGRESS.md)
   - Customer Mini App Step 1–5 Stabilization (branch `feat/miniapp-stabilization`): Added database-free Local Sandbox mode (`LOCAL_SANDBOX=1` & `scripts/run_local_sandbox.py`), fixed iOS/Telegram WebView input auto-zoom (`font-size: 16px`), pure Numpad (`inputmode="numeric" pattern="[0-9]*"`), and bottom-nav auto-hide on focus, replaced fake QR placeholder in `ShopView.vue` with live KBZPay/WavePay phone copy card, removed default SSE/polling overhead, fixed manual refresh throttling, added 1-click direct Top-Up slip submission, cleaned `KeyCard` to a 3-button layout, removed the fake header notification bell, wired smooth section scrolling (`navigateTo`), and synced dynamic `MY_PAYMENT_PHONES` + customer Telegram chat receipt/replace notifications. 408/408 backend tests and 13/13 Playwright E2E tests passing.

22. [**2026-11-17_PROGRESS.md**](file:///home/zixuan/Projects/outline-key-bot/memory/2026-11-17_PROGRESS.md)
   - Customer Mini App UI/UX Bug Fixes (4 owner-reported issues): stable Custom-amount layout (no auto-scroll, smooth expand transition), bottom tab bar stays visible on input focus (visualViewport keyboard guard), dialogs close only via explicit `X` (backdrop taps no longer dismiss), Rewards screen typography bumped (7–11px → 10–14px). 409/409 backend tests and 13/13 Playwright E2E tests passing.

23. [**2026-11-18_PROGRESS.md**](file:///home/zixuan/Projects/outline-key-bot/memory/2026-11-18_PROGRESS.md)
   - Local Dev Database Isolation (`LOCAL_STATE_DIR` → `.local_sandbox/`), 7 Production Plans + Admin Dashboard sync, 2-row scrollable Shop Plans grid, bounded chronological/filterable Purchase History & Top-50 Leaderboard modals, and Multi-VPN "Available VPN" deep-link auto-import (`Outline`, `V2Box`, `INCY`). 416/416 backend tests and 15/15 Playwright E2E tests passing.




