/// <reference path="../src/types/telegram.d.ts" />

import { test, expect } from '@playwright/test'
import type { Page } from '@playwright/test'
import { existsSync, readFileSync } from 'node:fs'
import type { TabId, VpnKey } from '../src/types'

const testKeys: VpnKey[] = [
  { id: 'k1', server: 'Server 1', location: 'Singapore', country: 'SG', plan: 'VIP', quota: 150, used: 94.5, expires: '2026-11-05', left: '19 days left', status: 'expiring', connected: false, key: 'ss://test-1' },
  { id: 'k2', server: 'Server 2', location: 'Tokyo', country: 'JP', plan: 'Basic', quota: 50, used: 14.5, expires: '2026-12-12', left: '56 days left', status: 'active', connected: true, key: 'ss://test-2' },
  { id: 'k4', server: 'Server 4', location: 'Frankfurt', country: 'DE', plan: 'Starter', quota: 25, used: 22, expires: '2026-12-16', left: '60 days left', status: 'active', connected: false, key: 'ss://test-4' },
]

const errors = new WeakMap<Page, string[]>()
const current = (page: Page) => page.locator('.snapshot-card[data-depth="0"]')
const tab = (page: Page, id: TabId) => page.locator(`.nav-item[data-tab="${id}"]`).click()
const settle = (page: Page) => page.waitForTimeout(470)

async function injectTestKeys(page: Page, keys: VpnKey[] = testKeys) {
  await page.evaluate((k) => window.TunnelUI?.setKeys(k), keys)
  await settle(page)
}

test.beforeEach(async ({ page }) => {
  const list: string[] = []
  errors.set(page, list)
  page.on('pageerror', error => list.push(error.message))
  await page.goto('/')
  await expect(page.locator('.overview-view')).toBeVisible()
})

test.afterEach(async ({ page }) => {
  expect(errors.get(page)).toEqual([])
})

test('honest empty state renders when fresh; stacked cards appear when keys are present', async ({ page }) => {
  // 1. Fresh state without keys renders honest empty state & clean 2-button header
  await expect(page.locator('#telegram-name')).toHaveText('Member')
  await expect(page.locator('.top-actions .icon-button')).toHaveCount(2)
  await expect(page.locator('[aria-label="Notifications"]')).toHaveCount(0)
  await expect(page.locator('.snapshot-section .empty-state')).toBeVisible()
  await expect(page.locator('.snapshot-section .empty-state')).toContainText('Active ဖြစ်နေသော Key မရှိသေးပါ')

  // 2. Inject real keys via TunnelUI bridge
  await injectTestKeys(page)
  await expect(page.locator('.snapshot-card')).toHaveCount(3)
  await expect(page.locator('.stack-dot')).toHaveCount(3)
  await expect(current(page)).toHaveAttribute('data-key-id', 'k2')
  await expect(current(page).locator('[data-percent-number]')).toHaveText('29')
  await expect(page.locator('.snapshot-card[data-depth="1"]')).toHaveAttribute('inert', '')
  await expect(page.locator('.snapshot-card[data-depth="1"]')).toHaveCSS('pointer-events', 'none')
  expect(await page.locator('symbol').count()).toBeGreaterThan(25)
})

test('real touch swipes advance vertically, return, and stop at both ends', async ({ page, context }) => {
  await injectTestKeys(page)
  const client = await context.newCDPSession(page)
  async function swipe(dy: number) {
    const box = await page.locator('.snapshot-stage').boundingBox()
    if (!box) throw new Error('Missing stage')
    const x = box.x + 120, y = box.y + 100
    await client.send('Input.dispatchTouchEvent', { type: 'touchStart', touchPoints: [{ x, y }] })
    for (let n = 1; n <= 7; n++) {
      await client.send('Input.dispatchTouchEvent', { type: 'touchMove', touchPoints: [{ x, y: y + dy * n / 7 }] })
    }
    await client.send('Input.dispatchTouchEvent', { type: 'touchEnd', touchPoints: [] })
    await settle(page)
  }
  await swipe(65)
  await expect(page.locator('#snapshot-current')).toHaveText('01')
  await swipe(-65)
  await expect(page.locator('#snapshot-current')).toHaveText('02')
  await swipe(-65)
  await expect(page.locator('#snapshot-current')).toHaveText('03')
  await swipe(-65)
  await expect(page.locator('#snapshot-current')).toHaveText('03')
  await swipe(65)
  await expect(page.locator('#snapshot-current')).toHaveText('02')
  await expect(page.locator('.stack-dot.active')).toHaveAttribute('data-snapshot-index', '1')
})

test('dots, keyboard and wheel select the same key; connect button opens Available VPN dialog', async ({ page }) => {
  await injectTestKeys(page)
  const stage = page.locator('.snapshot-stage')
  await stage.focus()
  await page.keyboard.press('ArrowUp')
  await settle(page)
  await expect(current(page)).toHaveAttribute('data-key-id', 'k1')
  await page.keyboard.press('End')
  await settle(page)
  await expect(page.locator('#snapshot-current')).toHaveText('03')
  await page.keyboard.press('Home')
  await settle(page)
  await stage.hover()
  await page.mouse.wheel(0, 60)
  await settle(page)
  await expect(page.locator('#snapshot-current')).toHaveText('02')
  await page.locator('[data-snapshot-index="0"]').click()
  await settle(page)
  await expect(current(page).locator('[data-action="connect"]')).toContainText('Available VPN')
  await current(page).locator('[data-action="connect"]').click()
  await expect(page.locator('#modal-title')).toContainText('ကိုယ်နဲ့ အဆင်ပြေတဲ့ VPN')
  await page.keyboard.press('Escape')
})

test('reactive usage bridge updates liquid gauge and Key Usage modal shows real metrics', async ({ page }) => {
  await injectTestKeys(page)
  const gauge = current(page).locator('.liquid-gauge')
  await expect(current(page).locator('[data-percent-number]')).toHaveText('29')
  await expect(current(page).locator('[data-used-number]')).toHaveText('14.5 GB')

  // 1. Reactive usage bridge tests
  expect(await page.evaluate(() => window.TunnelUI?.updateKeyUsage('k2', 20))).toBe(true)
  await expect(gauge).toHaveAttribute('aria-valuenow', '40')
  await page.evaluate(() => window.dispatchEvent(new CustomEvent('tunnel:usage', { detail: { id: 'k2', usedGB: 25 } })))
  await expect(gauge).toHaveAttribute('aria-valuenow', '50')
  expect(await page.evaluate(() => window.TunnelUI?.updateKeyUsage('missing', 20))).toBe(false)
  await page.evaluate(() => window.TunnelUI?.updateKeyUsage('k2', 999))
  await expect(gauge).toHaveAttribute('aria-valuenow', '100')

  // 2. Open Key Usage Details dialog (real read-only diagnostics)
  await current(page).locator('[data-action="key-preview"]').click()
  await expect(page.locator('#modal')).toBeVisible()
  await expect(page.locator('#modal')).toContainText('စုစုပေါင်း Data')
  await expect(page.locator('#modal')).toContainText('အသုံးပြုပြီး')
  await expect(page.locator('#modal')).toContainText('လက်ကျန် Data')
  await expect(page.locator('#modal')).toContainText('သက်တမ်း')
  await page.keyboard.press('Escape')
})

test('dialog traps focus, makes the background inert, closes on Escape and restores focus', async ({ page }) => {
  await injectTestKeys(page)
  const trigger = current(page).locator('[data-action="key-preview"]')
  await trigger.click()
  await expect(page.locator('#modal')).toBeVisible()
  await expect(page.locator('.modal-close')).toBeFocused()
  await expect(page.locator('#screen-content')).toHaveAttribute('inert', '')
  // Tapping empty backdrop space must NOT dismiss the dialog — only explicit close (X / Escape)
  await page.locator('#modal').click({ position: { x: 6, y: 6 } })
  await expect(page.locator('#modal')).toBeVisible()
  await page.keyboard.press('Shift+Tab')
  await expect(page.locator('#modal .modal-full-btn')).toBeFocused()
  await page.keyboard.press('Tab')
  await expect(page.locator('.modal-close')).toBeFocused()
  await page.keyboard.press('Escape')
  await expect(page.locator('#modal')).toHaveCount(0)
  await expect(trigger).toBeFocused()
})

test('all key filters and replace action dialog work in KeysView', async ({ page }) => {
  await injectTestKeys(page)
  await tab(page, 'keys')
  await expect(page.locator('.key-card')).toHaveCount(3)
  await expect(page.locator('.key-card').first().locator('.key-action')).toHaveCount(3)
  for (const [filter, count] of [['active', 2], ['expiring', 1], ['all', 3]] as const) {
    await page.locator(`[data-filter="${filter}"]`).click()
    await expect(page.locator('.key-card')).toHaveCount(count)
  }
  await page.locator('.key-card [data-action="replace"]').first().click()
  await expect(page.locator('#modal-title')).toContainText('Key')
  await page.keyboard.press('Escape')
})

test('custom top-up, payment method and receipt survive tab switches; min amount guarded', async ({ page }) => {
  await tab(page, 'shop')
  await expect(page.locator('#wallet-topup-card')).toBeVisible()
  await expect(page.locator('[data-action="direct-submit-topup"]')).toHaveCount(0)
  await page.locator('.plan-card[data-plan="VIP"]').click()
  await expect(page.locator('.plan-card.selected')).toHaveAttribute('data-plan', 'VIP')
  await page.locator('[data-amount="custom"]').click()
  const customFontSize = await page.locator('#custom-amount').evaluate(el => parseFloat(getComputedStyle(el).fontSize))
  expect(customFontSize).toBeGreaterThanOrEqual(16)
  await expect(page.locator('#custom-amount')).toHaveAttribute('inputmode', 'numeric')
  await expect(page.locator('#custom-amount')).toHaveAttribute('pattern', '[0-9]*')
  await expect(page.locator('.bottom-nav')).toBeVisible()
  await page.locator('#custom-amount').fill('abc၃၄၅၆!')
  await expect(page.locator('#custom-amount')).toHaveValue('3456')
  for (const method of ['kbz', 'wave', 'aya', 'uab', 'cb']) {
    await expect(page.locator(`[data-method="${method}"]`)).toBeVisible()
  }
  await page.locator('[data-method="aya"]').click()
  await expect(page.locator('[data-method="aya"]')).toHaveAttribute('aria-pressed', 'true')
  await page.locator('[data-method="wave"]').click()
  await page.locator('#receipt-file').setInputFiles({
    name: 'receipt.png',
    mimeType: 'image/png',
    buffer: Buffer.from('iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+jK1sAAAAASUVORK5CYII=', 'base64'),
  })
  await expect(page.locator('.upload-text strong')).toHaveText('receipt.png')
  await expect(page.locator('[data-action="direct-submit-topup"]')).toBeVisible()
  await page.locator('[data-action="show-payment"]').click()
  await expect(page.locator('#modal-title')).toHaveText('WavePay · 3,456 Ks')
  await page.keyboard.press('Escape')
  await tab(page, 'overview')
  await tab(page, 'shop')
  await expect(page.locator('#custom-amount')).toHaveValue('3456')
  await expect(page.locator('.upload-text strong')).toHaveText('receipt.png')
  await expect(page.locator('[data-method="wave"]')).toHaveAttribute('aria-pressed', 'true')
  await expect.poll(() => page.locator('.uploaded-preview').evaluate(node => (node as HTMLImageElement).naturalWidth)).toBe(1)
  await page.locator('#custom-amount').fill('499')
  await page.locator('[data-action="show-payment"]').click()
  await expect(page.locator('#modal')).toHaveCount(0)
  await expect(page.locator('#toast')).toContainText('500 Ks')
})

test('history and leaderboard render clean honest empty states on fresh account', async ({ page }) => {
  await tab(page, 'history')
  await expect(page.locator('.reward-points')).toContainText('0')
  await expect(page.locator('.history-card .empty-state')).toBeVisible()
  await expect(page.locator('.history-card .empty-state')).toContainText('ဝယ်ယူမှုမှတ်တမ်း မရှိသေးပါ')
  await expect(page.locator('.leaderboard-card .empty-state')).toBeVisible()
  await expect(page.locator('.leaderboard-card .empty-state')).toContainText('ဦးဆောင်သူစာရင်း မရှိသေးပါ')
})

test('valid keys control 0–3 cards, dots and empty state; host names are escaped', async ({ page }) => {
  for (const count of [2, 1, 0, 3]) {
    const valid = testKeys.slice(0, count)
    await page.evaluate(keys => window.TunnelUI?.setKeys(keys), valid)
    await expect(page.locator('.snapshot-card')).toHaveCount(count)
    await expect(page.locator('.stack-dot')).toHaveCount(count > 1 ? count : 0)
    if (count === 0) {
      await expect(page.locator('.snapshot-section .empty-state')).toBeVisible()
    }
  }
  await page.evaluate(() => window.TunnelUI?.setUser({ id: 987654, first_name: '<script>unsafe</script>', last_name: 'Member' }))
  await expect(page.locator('#telegram-name')).toHaveText('<script>unsafe</script> Member')
  await expect(page.locator('#telegram-name script')).toHaveCount(0)
  await expect(page.locator('#telegram-id')).toHaveText('987654')
})

test('all screens fit 11 mobile/tablet/desktop widths without horizontal overflow', async ({ page }) => {
  for (const width of [320, 360, 375, 390, 432, 540, 690, 691, 768, 1024, 1440]) {
    await page.setViewportSize({ width, height: 900 })
    for (const screen of ['overview', 'keys', 'shop', 'history'] as const) {
      await tab(page, screen)
      const dimensions = await page.evaluate(() => {
        const content = document.querySelector<HTMLElement>('#screen-content')!
        return {
          bodyOverflow: document.documentElement.scrollWidth - innerWidth,
          contentOverflow: content.scrollWidth - content.clientWidth,
        }
      })
      expect(dimensions.bodyOverflow, `${width}px ${screen} body`).toBeLessThanOrEqual(1)
      expect(dimensions.contentOverflow, `${width}px ${screen} content`).toBeLessThanOrEqual(1)
    }
  }
})

test('reduced motion removes loops without breaking selection or usage', async ({ page }) => {
  await injectTestKeys(page)
  await page.emulateMedia({ reducedMotion: 'reduce' })
  await expect(current(page).locator('[data-percent-number]')).toHaveText('29')
  await expect(current(page).locator('.wave-front')).toHaveCSS('animation-name', 'none')
  await page.locator('[data-snapshot-index="2"]').click()
  await expect(current(page).locator('[data-percent-number]')).toHaveText('88')
  await expect(page.locator('#snapshot-current')).toHaveText('03')
})

test('optional Telegram identity and native swipe integration are guarded', async ({ page }) => {
  await page.addInitScript(() => {
    window.Telegram = {
      WebApp: {
        initDataUnsafe: { user: { id: 123456, first_name: 'Telegram', last_name: 'User' } },
        isVerticalSwipesEnabled: true,
        disableVerticalSwipes() { this.isVerticalSwipesEnabled = false },
        enableVerticalSwipes() { this.isVerticalSwipesEnabled = true },
      },
    }
  })
  await page.reload()
  await expect(page.locator('#telegram-name')).toHaveText('Telegram User')
  expect(await page.evaluate(() => window.Telegram?.WebApp?.isVerticalSwipesEnabled)).toBe(false)
  await tab(page, 'keys')
  await expect.poll(() => page.evaluate(() => window.Telegram?.WebApp?.isVerticalSwipesEnabled)).toBe(true)
  await tab(page, 'overview')
  await expect.poll(() => page.evaluate(() => window.Telegram?.WebApp?.isVerticalSwipesEnabled)).toBe(false)
})

test('compiled standalone Vue preview works in an offline opaque-origin iframe', async ({ page }) => {
  const file = 'artifacts/tunnel-vue-preview.html'
  test.skip(!existsSync(file), 'Run npm run build to generate the standalone preview first')
  const requests: string[] = []
  await page.goto('about:blank')
  await page.route('**/*', route => { requests.push(route.request().url()); void route.abort() })
  await page.setContent('<iframe title="Preview" sandbox="allow-scripts" style="width:390px;height:844px;border:0"></iframe>')
  await page.locator('iframe').evaluate((frame, html) => { (frame as HTMLIFrameElement).srcdoc = html }, readFileSync(file, 'utf8'))
  const frame = page.frameLocator('iframe')
  await expect(frame.locator('.overview-view')).toBeVisible()
  await frame.locator('.nav-item[data-tab="shop"]').click()
  await expect(frame.locator('.plans-grid')).toBeVisible()
  expect(requests).toEqual([])
})

test('daily reward claim displays loading suspense spinner before revealing points', async ({ page }) => {
  await page.route('**/api/user/claim', route =>
    route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({
        success: true,
        awarded: 42,
        new_balance: 42,
        streak_days: 1,
        is_streak_bonus: false,
        next_in_s: 14400,
        cooldown_hours: 4,
        message: '🎉 +42 Points ရရှိပါသည်!',
      }),
    }),
  )
  await page.locator('.wallet-card [data-action="claim"]').click()
  await expect(page.locator('#modal [data-claim-stage="loading"]')).toBeVisible()
  await expect(page.locator('#modal progress.claim-spinner')).toBeVisible()
  await expect(page.locator('#modal [data-claim-stage="success"]')).toBeVisible({ timeout: 5000 })
  await expect(page.locator('#modal .claim-reveal-points')).toContainText('+42 PTS')
  await page.locator('#modal .modal-close').click()
  await expect(page.locator('#modal')).toHaveCount(0)
})

test('2-row scrollable plans, bounded 30-item history & leaderboard modals, and Available VPN deep links', async ({ page }) => {
  await page.addInitScript(() => {
    const opened: Array<{ url: string; opts: unknown }> = []
    ;(window as any).__openedLinks = opened
    window.Telegram = {
      WebApp: {
        initData: 'query_id=e2e&user=%7B%22id%22%3A123%7D&auth_date=1700000000&hash=mock',
        initDataUnsafe: { user: { id: 123, first_name: 'Tester', last_name: 'One', username: 'tester_one' } },
        openLink(url: string, opts?: { try_instant_view?: boolean }) {
          opened.push({ url, opts })
        },
      },
    }
  })

  const mockPlans = [
    { code: 'starter', name: 'Starter Plan', quota: '25 GB', price: 1000, description: '25 GB / 1 လစာ', symbol: 'leaf' },
    { code: 'basic', name: 'Basic Plan', quota: '50 GB', price: 2000, description: '50 GB / 1 လစာ', symbol: 'zap' },
    { code: 'standard', name: 'Standard Plan', quota: '75 GB', price: 3000, description: '75 GB / 1 လစာ', symbol: 'zap' },
    { code: 'premium', name: 'Premium Plan', quota: '100 GB', price: 4000, description: '100 GB / 1 လစာ', symbol: 'zap' },
    { code: 'vip', name: 'VIP Plan', quota: '150 GB', price: 5000, description: '150 GB / 1 လစာ', symbol: 'crown' },
    { code: 'pro', name: 'Pro Plan', quota: '200 GB', price: 7000, description: '200 GB / 1 လစာ', symbol: 'crown' },
    { code: 'ultimate', name: 'Ultimate VIP Plan', quota: '500 GB', price: 10000, description: '500 GB / 1 လစာ', symbol: 'crown' },
    { code: 'max', name: 'Max Plan', quota: '1000 GB', price: 18000, description: '1000 GB / 1 လစာ', symbol: 'crown' },
  ]

  await page.route('**/api/user/bootstrap**', route =>
    route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({
        user: { id: '123', name: 'Tester One', username: 'tester_one', initials: 'TO' },
        wallet: { balance: 15000, main_balance: 15000, bonus_balance: 0, points: 70, claimed_today: false, can_claim: true, streak_days: 1, cooldown_remaining: 0, cooldown_hours: 4 },
        keys: [
          { id: 'k1', server: 'Server 1', location: 'Singapore', country: 'SG', plan: 'Starter', quota: 25, used: 2, expires: '2026-12-18', left: '30 days left', status: 'active', connected: true, key: 'ss://dGVzdEAxMjcuMC4wLjE6ODM4OA==#Starter', go_url: '/go/signedtoken123' },
        ],
        plans: mockPlans,
        servers: [{ id: '1', name: 'Server 1', location: 'Singapore', country: 'SG', flag: '🇸🇬' }],
        payment_methods: { kbz: { name: 'KBZPay', account_name: 'Htet Myat Aung', phone: '09699970092', type: 'QR' } },
      }),
    }),
  )

  const purchases = Array.from({ length: 15 }, (_, idx) => ({
    order_id: `#ORD${idx + 1}`,
    plan_name: 'Starter Plan',
    disp_gb: '25 GB',
    price: '1,000 Ks',
    date: `18/11/2026 (0${(idx % 9) + 1}:15 PM)`,
    status: idx % 5 === 0 ? 'Expired' : 'Active',
  }))
  const slips = Array.from({ length: 15 }, (_, idx) => ({
    slip_id: `SLIP${idx + 1}`,
    amount: 2000,
    method: idx % 2 === 0 ? 'WAVE' : 'KBZ',
    status: idx === 0 ? 'APPROVED' : idx === 1 ? 'REJECTED' : 'PENDING',
    submitted_at: `2026-11-18 10:${String(10 + idx).padStart(2, '0')}:00`,
  }))
  await page.route('**/api/user/history', route =>
    route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify({ purchases, slips }) }),
  )

  const rows = Array.from({ length: 30 }, (_, idx) => ({
    rank: idx + 1,
    name: idx === 23 ? 'Tester One' : `Customer #${idx + 1}`,
    points: 1000 - idx * 20,
    is_you: idx === 23,
  }))
  await page.route('**/api/user/leaderboard', route =>
    route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify({ rows, me: { rank: 24, name: 'Tester One', points: 540 }, total_players: 30, mode: '7d' }) }),
  )

  await page.setViewportSize({ width: 390, height: 844 })
  await page.reload()
  await expect(page.locator('.snapshot-card[data-depth="0"] [data-action="connect"]')).toContainText('Available VPN')

  // 1. Open Available VPN modal from Overview & verify V2Box / INCY / Outline open /go/<token>?app=
  await page.locator('.snapshot-card[data-depth="0"] [data-action="connect"]').click()
  await expect(page.locator('#modal-title')).toHaveText('ကိုယ်နဲ့ အဆင်ပြေတဲ့ VPN နဲ့ ချိတ်ဆက်ရန်')
  for (const app of ['outline', 'v2box', 'incy']) {
    await expect(page.locator(`#modal [data-vpn-app="${app}"]`)).toBeVisible()
    await expect(page.locator(`#modal [data-vpn-app="${app}"] .vpn-app-logo-svg`)).toBeVisible()
  }
  await page.locator('#modal [data-vpn-app="v2box"]').click()
  await page.locator('#modal [data-vpn-app="incy"]').click()
  const opened = await page.evaluate(() => (window as any).__openedLinks)
  expect(opened.some((x: any) => String(x.url).endsWith('/go/signedtoken123?app=v2box') && x.opts?.try_instant_view === false)).toBe(true)
  expect(opened.some((x: any) => String(x.url).endsWith('/go/signedtoken123?app=incy') && x.opts?.try_instant_view === false)).toBe(true)
  await page.locator('#modal .modal-close').click()

  // 2. Verify My Keys button also shows Available VPN and opens connect modal
  await tab(page, 'keys')
  await expect(page.locator('.key-card [data-action="connect"]').first()).toContainText('Available VPN')
  await page.locator('.key-card [data-action="connect"]').first().click()
  await expect(page.locator('#modal-title')).toHaveText('ကိုယ်နဲ့ အဆင်ပြေတဲ့ VPN နဲ့ ချိတ်ဆက်ရန်')
  await page.locator('#modal .modal-close').click()

  // 3. Verify 2-row default VPN Plans (6 visible cards, zero scroll trap) + Smooth Expand/Collapse + Wallet Jump + BottomNav Glider
  await tab(page, 'shop')
  const plansGrid = page.locator('.plans-grid').first()
  await expect(plansGrid).toBeVisible()
  await expect(page.locator('.plans-shell .plan-card:visible')).toHaveCount(6)
  await expect(plansGrid).toHaveCSS('overflow-y', 'visible')
  await expect(page.locator('.bottom-nav-track')).toHaveCSS('--active-idx', '2')
  await expect(page.locator('[data-action="toggle-plans"]')).toHaveAttribute('aria-expanded', 'false')

  await page.locator('[data-action="toggle-plans"]').click()
  await expect(page.locator('[data-action="toggle-plans"]')).toHaveAttribute('aria-expanded', 'true')
  await expect(page.locator('.plans-extra-collapse')).toHaveClass(/is-open/)
  await expect(page.locator('.plans-shell .plan-card:visible')).toHaveCount(8)

  await page.locator('[data-action="toggle-plans"]').click()
  await expect(page.locator('[data-action="toggle-plans"]')).toHaveAttribute('aria-expanded', 'false')
  await expect(page.locator('.plans-shell .plan-card:visible')).toHaveCount(6)

  await page.locator('[data-action="jump-topup"]').click()
  await expect(page.locator('#wallet-topup-card')).toBeInViewport()

  // 4. Verify Rewards previews + bounded 30-item History & Leaderboard modals (plus background animation pause)
  await tab(page, 'history')
  await expect(page.locator('.bottom-nav-track')).toHaveCSS('--active-idx', '3')
  await expect(page.locator('.history-card .history-row')).toHaveCount(5)
  await expect(page.locator('.leaderboard-card .leader-row')).toHaveCount(6) // Top 5 + pinned You row

  await page.locator('[data-action="all-history"]').click()
  await expect(page.locator('.app-frame')).toHaveClass(/has-modal/)
  await expect(page.locator('#modal-title')).toHaveText('Purchase history')
  await expect(page.locator('#modal .list-head')).toHaveCount(0)
  await expect(page.locator('#modal .history-row')).toHaveCount(30)
  const historyBox = await page.locator('#modal .modal-sheet').boundingBox()
  expect(historyBox!.height).toBeLessThanOrEqual(844 * 0.88)
  await expect(page.locator('#modal .modal-footer button')).toBeInViewport()
  await page.locator('[data-history-filter="slips"]').click()
  await expect(page.locator('#modal .history-row')).toHaveCount(15)
  await page.locator('[data-history-filter="purchases"]').click()
  await expect(page.locator('#modal .history-row')).toHaveCount(15)
  await page.locator('#modal .modal-close').click()

  await page.locator('[data-action="leaderboard"]').click()
  await expect(page.locator('#modal-title')).toHaveText('Leaderboard')
  await expect(page.locator('#modal .leader-row')).toHaveCount(30)
  await expect(page.locator('#modal .leaderboard-summary-bar')).toContainText('#24')
  const lbBox = await page.locator('#modal .modal-sheet').boundingBox()
  expect(lbBox!.height).toBeLessThanOrEqual(844 * 0.88)
  await expect(page.locator('#modal .modal-footer button')).toBeInViewport()
  await page.locator('#modal .modal-close').click()
})
