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

