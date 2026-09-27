# 05 — Points / Daily Reward System (FUTURE PLAN, not yet built)

> Status: **DESIGN LOCKED — implementation started 2026-09-27 (Phase 1).**
> Forward-looking spec agreed with the user. Free-tier feasible: runs entirely
> on Upstash KV (no Supabase needed).
>
> **Decisions resolved 2026-09-27:**
> 1. **Starter Plan is the ONLY redemption product**, but redemption is
>    **repeatable** — any user (who has topped up ≥ 1×) may redeem it again and
>    again while their balance is ≥ 5,000. There is no per-user lifetime limit;
>    the 20,000 cap is the only ceiling on hoarding.
> 2. Admin manual top-ups grant **no points** (`POINTS_ON_ADMIN_TOPUP = False`,
>    locked — not just a default).

## 1. Concept

A gamified loyalty currency ("Points") to drive daily engagement:

- Users earn Points from **two sources**: a **4-hour cooldown claim** (random
  amount) and **every wallet top-up** (approved payment slip).
- Points **never expire**, but the **balance is hard-capped at 20,000** — any
  earnings above the cap are **discarded** ("use it or lose it"), to push
  redemption and prevent unbounded hoarding.
- Points are redeemable for a **Starter Plan (25 GB) at 5,000 points**. Starter
  is the ONLY redemption product, but redemption is **repeatable** (spend 5,000
  → Starter → keep earning → redeem again). More plan tiers may be added later.
- Redemption requires the user to have **topped up at least once ever**
  (anti-Sybil gate) plus the existing REQUIRED_CHANNEL join.

## 2. Locked economics

| Parameter | Value |
|---|---|
| Peg | 5,000 points = Starter Plan (25 GB / 1,000 Ks) → 1 pt ≈ 0.2 Ks |
| Balance cap | **20,000 points** (overflow discarded, not banked) |
| Claim cooldown | **4 hours** from each claim (rolling; ~6/day max, realistically ~5) |
| Claim reward | random **10–200**, never 0; low-weighted (mostly 10–30) |
| Streak guarantee | 7 consecutive days claiming → guaranteed **150–200** on day 7 |
| Top-up reward | `min(1000, floor(amount_ks / 100))` = 1% of top-up, capped at 1,000 (at 100k Ks) |
| Redeem gate | must have topped up ≥ 1× ever + channel join |
| Redemption product | Starter Plan @ 5,000 points — **only product, repeatable** while balance ≥ 5,000 |

### Claim reward distribution (config-adjustable weights)

| Range | Weight | Midpoint |
|---|---|---|
| 10–19 | 35% | 15 |
| 20–30 | 35% | 25 |
| 31–50 | 18% | 40 |
| 51–99 | 8% | 75 |
| 100–150 | 3% | 125 |
| 151–200 | 1% | 175 |

Expected value ≈ **33 points/claim** → ~165/day realistic (5 claims), ~196/day
at a perfect 6. Time to a free Starter (5,000): **~25–30 days** of active daily
claiming, ≈ 33 Ks/day of free value. Sustainable for a $0 reseller (25 GB key
marginal cost ≈ 0 on fixed-cost VPS); anti-Sybil top-up gate blocks farming.

## 3. Data model (Upstash KV, file fallback — same pattern as wallets/slips)

New KV key `points_data` (fallback file `POINTS_FILE = "/tmp/points_data.json"`
added to `bot_app/storage/paths.py`). Shape:

```jsonc
{
  "<chat_id>": {
    "points": 4820,                    // current spendable balance (≤ 20000)
    "last_claim_at": "2026-09-27 14:03:11",  // Myanmar time; cooldown anchor
    "streak_days": 5,                  // consecutive calendar-days with ≥1 claim
    "last_streak_day": "2026-09-27",   // last calendar day counted for streak
    "has_topped_up": true,             // ever completed a real top-up (redeem gate)
    "redeemed_count": 2,               // Starters redeemed so far (analytics; no limit)
    "lifetime_earned": 15230,          // audit/analytics only, uncapped
    "lifetime_claims": 41
  }
}
```

New service module `bot_app/services/points.py` with pure, testable helpers:

- `load_all_points()` / `save_all_points(data)` — KV + file fallback.
- `get_points(chat_id)` — record with safe defaults.
- `claim_cooldown_remaining(rec, now)` — seconds until next claim (0 = ready).
- `roll_claim_reward(streak_days)` — weighted RNG; returns the guaranteed
  150–200 band when this claim completes a 7-day streak, else the table above.
- `credit_points(chat_id, amount, source)` — adds, applies the 20,000 cap
  (returns `granted, discarded`), bumps `lifetime_earned`.
- `try_claim(chat_id, now)` — the atomic claim path (see §5 concurrency);
  returns `{ok, awarded, discarded, new_balance, streak_days, next_in_s}` or a
  cooldown error.
- `topup_points_for(amount_ks)` → `min(1000, amount_ks // 100)`.
- `can_redeem(rec)` — gate: must have topped up ≥ 1× AND balance ≥ 5,000 (no
  lifetime limit — repeatable). `redeem_starter(chat_id)` — deducts 5,000 and
  bumps `redeemed_count`; `refund_starter(chat_id)` re-credits and decrements
  the count if key provisioning later fails.

All money/points are integers; all timestamps use `myanmar_now()`.

## 4. Integration surface — every place that must change

### 4a. Bot / customer side (`bot_app/handlers/`, `keyboards.py`)
- **`keyboards.py::get_main_menu_keyboard`** — add a `🎁 Daily Reward` reply
  button (customer row).
- **`handlers/menu.py::handle_all_messages`** — new text branch for
  `🎁 Daily Reward`: show balance, streak, cooldown countdown, and a
  `🎁 Claim Now` / `🎫 Redeem Starter (5,000)` inline keyboard.
- **New `handlers/points.py`** (or a section in menu.py) — callbacks
  `points_claim` and `points_redeem_starter`; claim shows awarded amount +
  jackpot flair, redeem calls `redeem_starter` then provisions the key.
- **Key provisioning on redeem** — reuse
  `services/outline.py::create_outline_key(..., is_giveaway=True, custom_days=30)`
  for the Starter (25 GB); record it in purchase history so it shows in the
  dashboard, tagged as a points redemption (order_id like `PTS-xxxx`).
- **`handlers/gate.py`** — no change needed (menu button re-reads on `/start`).

### 4b. Top-up hook (single choke point covers Telegram + dashboard)
- **`services/slips.py::review_slip` APPROVE branch** — right after
  `update_user_balance(chat_id, amount)`, call
  `credit_points(chat_id, topup_points_for(amount), "topup")` and set
  `has_topped_up=True`. Because BOTH the Telegram approve button and the
  dashboard `POST /slips/<id>/review` funnel through `review_slip`, this one
  hook covers both paths. Add the awarded points to the customer's approval
  Telegram notice.
- **`routes_admin.py::adjust_customer_balance` (manual admin TOPUP)** —
  LOCKED: **no points** for manual admin credits (they are comps, not customer
  payments) and they do **not** flip `has_topped_up`. Config flag
  `POINTS_ON_ADMIN_TOPUP = False` guards this if we ever revisit it.

### 4c. Admin dashboard (REST + Vue)
- **`routes_admin.py`**
  - `GET /customers` — join `points` into each row (parallel read, like
    `total_topup`); optional column/sort on the Customers page.
  - `GET /customers/<id>` — add `points`, `streak_days`, `has_topped_up`,
    `lifetime_earned`, and a **points ledger** (from audit logs) to the detail
    payload.
  - `POST /customers/<id>/points` — **admin manual grant/deduct** with reason,
    audited (mirrors `/balance`); respects the 20,000 cap; refuses overdraw.
  - Overview (`services/admin_telemetry.py`) — optional KPI: points redeemed
    this month / active claimers (nice-to-have, not required for v1).
- **Vue**
  - `CustomerDetailView.vue` — a "Points" stat + a **Points ledger tab**
    (claims, top-up grants, redemptions, admin adjusts) + a manual
    grant/deduct modal (reuse the balance-adjust modal pattern).
  - `CustomersView.vue` — optional Points column + sort + a stat chip.
  - `api.ts` — `adjustPoints()` + points fields typing.

### 4d. Audit + live-refresh
- New audit actions: `POINTS_CLAIM`, `POINTS_TOPUP`, `POINTS_REDEEM`,
  `POINTS_ADMIN_GRANT`, `POINTS_ADMIN_DEDUCT` via `record_audit_log(...)`.
- Any points write bumps the data-version (through `redis_set`) so the
  dashboard SSE/poll refresh picks it up — same as wallets today.

### 4e. Config (`bot_app/config.py`)
```
POINTS_BALANCE_CAP = 20000
POINTS_CLAIM_COOLDOWN_H = 4
POINTS_TOPUP_RATE = 100          # 1 point per 100 Ks
POINTS_TOPUP_CAP = 1000
POINTS_STARTER_COST = 5000
POINTS_STREAK_TARGET_DAYS = 7
POINTS_REWARD_TABLE = [...]      # (range, weight) rows from §2
POINTS_ON_ADMIN_TOPUP = False
```

## 5. Concurrency (serverless double-claim guard)

Two fast taps can both read the old `last_claim_at` and double-grant. Guard the
claim with a short per-user lock in Upstash: `SET points_lock:<chat_id> 1 NX EX 10`
(needs a tiny `redis_set_nx` helper in `storage/kv.py`); if the lock is not
acquired, reject as "claim in progress". Re-check the cooldown *inside* the lock
before granting, then write and release. In file-fallback/local dev the lock is
best-effort (single process), which is fine for tests.

## 6. Streak logic

On each successful claim, compare `last_streak_day` (calendar day, Myanmar) to
today: same day → unchanged; yesterday → `streak_days += 1`; older/none → reset
to 1. Every time `streak_days` reaches a **multiple of `POINTS_STREAK_TARGET_DAYS`
(7, 14, 21…)**, that claim's reward is drawn from the guaranteed 150–200 band.
Streak never expires the points, only affects that one bonus draw.

## 7. Phased build plan

1. **Core service + storage** (`points.py`, `paths.py`, config) + unit tests
   (cooldown math, weighted RNG bounds, cap/overflow, streak transitions,
   top-up formula). Zero network.
2. **Top-up hook** in `review_slip` + notice text + tests (approve credits
   correct points, flips `has_topped_up`, dashboard path too).
3. **Bot claim + redeem UX** (keyboard, menu branch, callbacks, key
   provisioning on redeem) + handler tests with `mock_bot`.
4. **Admin dashboard** (customer detail points + ledger + manual adjust
   endpoint/modal, list column) + API tests.
5. Overview KPI (optional), docs, deploy, live verify.

## 8. Open decisions

- ~~Redemption repeatable vs once-ever?~~ **RESOLVED: repeatable; Starter is the
  only product, no per-user lifetime limit (20,000 balance cap is the ceiling).**
- ~~Admin manual TOPUP grants points?~~ **RESOLVED: no (`POINTS_ON_ADMIN_TOPUP=False`).**
- **Redeemed Starter validity** — 30 days like a normal Starter. Assumed yes;
  wired into Phase 3 key provisioning (`custom_days=30`).
- Reward-table weights are a starting point; tune after seeing live behavior.

