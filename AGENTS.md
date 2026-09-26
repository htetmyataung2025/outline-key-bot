# AGENTS.md — Outline Key Bot & Control Center Guidelines

This document provides mandatory operational instructions, development standards, architectural constraints, and session-continuity protocols for all AI agents working on the **Outline Key Bot & Control Center** repository.

---

## 1. Project Overview & Architecture Principles

- **Project Core**: Outline VPN Key Bot + Hybrid Admin Control Center (Desktop Web + Mobile Telegram Mini App).
- **Target Cost**: **100% Free Tier ($0/month)**.
  - **Frontend**: Vue 3 + Vite + Naive UI (hosted on Vercel / Cloudflare Pages).
  - **Backend**: Python (Flask / FastAPI - Vercel Serverless Function).
  - **Database**: Supabase PostgreSQL (500 MB free tier).
  - **Cache & Rate-limiting**: Upstash Redis (free tier) with fallback to file storage in local dev/tests.
- **Vercel Routing Caveat**:
  - `vercel.json` rewrites requests to `/api/index.py`. Route handlers must be path-aware and support both webhook POST events, cron checks, and `/api/admin/*` REST calls cleanly.

---

## 2. Mandatory Rules for All Agents

### 🔒 Rule 1: Security First
- Never expose Admin functionality without authentication.
- **Telegram Mini App (TMA)**: Authenticate requests using `X-Telegram-Init-Data` header validated via cryptographic **HMAC-SHA256** using the `TELEGRAM_TOKEN`.
- **Admin Verification**: Ensure the parsed user ID is explicitly present in `ADMIN_CHAT_IDS`. Non-admin IDs must be rejected with `403 Forbidden`.
- **Desktop Fallback**: Require an Admin Bearer Token / Secret PIN for browser access.
- Never commit `.env` or sensitive secrets to Git.

### 🧪 Rule 2: Test Automation & Quality Standards
- Any new backend endpoint, authentication logic, or service MUST have corresponding unit/integration tests in [tests/](file:///home/zixuan/Projects/outline-key-bot/tests).
- Run tests using `.venv/bin/pytest` (or `pytest`).
- **Zero Network Calls in Tests**:
  - Mock Telegram Bot API calls (`mock_bot` fixture).
  - Mock Outline Server API HTTP calls.
  - Redirect all state file paths to temporary isolated directories (`isolated_state` fixture).
- **Regression Zero**: All existing tests (currently 68/68 passing) plus new tests must pass before completing any task.

### 📁 Rule 3: Clean, Professional File Structure
- Keep `bot_app` modular:
  - `bot_app/handlers/` - Telegram chat command & callback handlers.
  - `bot_app/services/` - Business logic (billing, OCR, outline client, slip verification, admin telemetry).
  - `bot_app/routes/` or `bot_app/routes_admin.py` - Flask/FastAPI REST API endpoints.
  - `bot_app/helpers/` - Reusable utility guards, crypto validators, and text formatters.
  - `bot_app/storage/` - Storage interfaces (Redis, Supabase, local files).
- Keep Dashboard clean in `dashboard/`:
  - Vue 3 + Naive UI components following the OpsTranslate dark theme design tokens (`#0b1120`, `#1e293b`, `#10b981`).

---

## 3. Session Continuity & Memory Protocol

> [!IMPORTANT]
> **CRITICAL RULE FOR ALL FUTURE SESSIONS:**
> To prevent lost context and repeated work, every agent MUST execute the following protocol:

1. **At the start of every session**:
   - Read this file (`AGENTS.md`).
   - Read [memory/README.md](file:///home/zixuan/Projects/outline-key-bot/memory/README.md) and the latest `memory/<YYYY-MM-DD>_PROGRESS.md` to immediately know:
     - What was completed previously.
     - What the current active task is.
     - What remains to be done next.
2. **During the session**:
   - Follow the design specifications in `memory/00_ARCHITECTURE_OVERVIEW.md` through `memory/04_FREE_DEPLOYMENT_ROADMAP.md`.
3. **At the end of every session / milestone**:
   - Create or update `memory/<YYYY-MM-DD>_PROGRESS.md` with:
     - Date & Timestamp.
     - Completed tasks (with links to modified files).
     - Test run results (number of passing tests).
     - Known issues or pending decisions.
     - Next prioritized action items.
   - Update `memory/README.md` index if new documentation files were added.

---

## 4. Coding & Communication Standards
- Write clean, type-annotated, linted Python and TypeScript.
- Provide clickable file links (`file:///...`) when referencing files.
- Communicate with the user in courteous, clear, and professional Burmese (မြန်မာဘာသာ).
