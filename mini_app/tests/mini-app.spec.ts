import { test, expect } from '@playwright/test'
import type { Page } from '@playwright/test'
import { existsSync, readFileSync } from 'node:fs'
import { demoKeys } from '../src/data/demo'
import type { TabId } from '../src/types'

const errors = new WeakMap<Page, string[]>()
const current = (page: Page) => page.locator('.snapshot-card[data-depth="0"]')
const tab = (page: Page, id: TabId) => page.locator(`.nav-item[data-tab="${id}"]`).click()
const settle = (page: Page) => page.waitForTimeout(470)
test.beforeEach(async ({ page }) => {
  const list: string[] = []; errors.set(page, list)
  page.on('pageerror', error => list.push(error.message))
  await page.goto('/')
  await expect(page.locator('.snapshot-total')).toHaveText('3')
})
test.afterEach(async ({ page }) => { expect(errors.get(page)).toEqual([]) })

test('compact header, SVG icons, decorated stacked cards and real numbers', async ({ page }) => {
  await expect(page.locator('#telegram-name')).toHaveText('Aung Aung')
  await expect(page.locator('#telegram-id')).toHaveText('78429105')
  await expect(page.locator('.identity-card')).toHaveCount(0)
  await expect(page.locator('.snapshot-card')).toHaveCount(3)
  await expect(page.locator('.stack-dot')).toHaveCount(3)
  await expect(current(page)).toHaveAttribute('data-key-id', 'k2')
  await expect(current(page).locator('[data-percent-number]')).toHaveText('29')
  await expect(page.locator('.snapshot-card[data-depth="1"]')).toHaveAttribute('inert', '')
  await expect(page.locator('.snapshot-card[data-depth="1"]')).toHaveCSS('pointer-events', 'none')
  await expect(page.locator('.intro')).toBeHidden()
  expect(await page.locator('symbol').count()).toBe(37)
})

test('real touch swipes advance vertically, return, and stop at both ends', async ({ page, context }) => {
  const client = await context.newCDPSession(page)
  async function swipe(dy: number) {
    const box = await page.locator('.snapshot-stage').boundingBox(); if (!box) throw new Error('Missing stage')
    const x = box.x + 120, y = box.y + 100
    await client.send('Input.dispatchTouchEvent', { type: 'touchStart', touchPoints: [{ x, y }] })
    for (let n = 1; n <= 7; n++) await client.send('Input.dispatchTouchEvent', { type: 'touchMove', touchPoints: [{ x, y: y + dy * n / 7 }] })
    await client.send('Input.dispatchTouchEvent', { type: 'touchEnd', touchPoints: [] })
    await settle(page)
  }
  await swipe(65); await expect(page.locator('#snapshot-current')).toHaveText('01')
  await swipe(-65); await expect(page.locator('#snapshot-current')).toHaveText('02')
  await swipe(-65); await expect(page.locator('#snapshot-current')).toHaveText('03')
  await swipe(-65); await expect(page.locator('#snapshot-current')).toHaveText('03')
  await swipe(65); await expect(page.locator('#snapshot-current')).toHaveText('02')
  await expect(page.locator('.stack-dot.active')).toHaveAttribute('data-snapshot-index', '1')
})

test('dots, keyboard and wheel select the same key; button presses do not swipe', async ({ page }) => {
  const stage = page.locator('.snapshot-stage')
  await stage.focus(); await page.keyboard.press('ArrowUp'); await settle(page)
  await expect(current(page)).toHaveAttribute('data-key-id', 'k1')
  await page.keyboard.press('End'); await settle(page)
  await expect(page.locator('#snapshot-current')).toHaveText('03')
  await page.keyboard.press('Home'); await settle(page)
  await stage.hover(); await page.mouse.wheel(0, 60); await settle(page)
  await expect(page.locator('#snapshot-current')).toHaveText('02')
  await page.locator('[data-snapshot-index="0"]').click(); await settle(page)
  await current(page).locator('[data-action="connect"]').click()
  await expect(page.locator('#modal-title')).toContainText('Outline')
  await expect(page.locator('#snapshot-current')).toHaveText('01')
  await page.keyboard.press('Escape')
})

test('0/100% liquid endpoints, reactive usage bridge and continuous honest animations', async ({ page }) => {
  const gauge = current(page).locator('.liquid-gauge')
  await expect(current(page).locator('[data-percent-number]')).toHaveText('29')
  const before = await current(page).locator('.wave-front').evaluate(node => getComputedStyle(node).transform)
  await page.waitForTimeout(250)
  expect(await current(page).locator('.wave-front').evaluate(node => getComputedStyle(node).transform)).not.toBe(before)
  await expect(current(page).locator('[data-used-number]')).toHaveText('14.5 GB')
  for (const [n, offset] of [[100, '-12%'], [0, '112%']] as const) {
    await current(page).locator('[data-action="key-preview"]').click()
    await page.locator(`[data-usage-preset="${n}"]`).click()
    await expect(gauge).toHaveAttribute('aria-valuenow', String(n))
    await expect(current(page).locator('[data-percent-number]')).toHaveText(String(n))
    expect(await gauge.evaluate(node => (node as HTMLElement).style.getPropertyValue('--liquid-offset'))).toBe(offset)
    await expect(current(page).locator('[data-usage-fill]')).toHaveAttribute('data-target', String(n))
  }
  expect(await page.evaluate(() => window.TunnelUI?.updateKeyUsage('k2', 20))).toBe(true)
  await expect(gauge).toHaveAttribute('aria-valuenow', '40')
  await page.evaluate(() => window.dispatchEvent(new CustomEvent('tunnel:usage', { detail: { id: 'k2', usedGB: 25 } })))
  await expect(gauge).toHaveAttribute('aria-valuenow', '50')
  expect(await page.evaluate(() => window.TunnelUI?.updateKeyUsage('missing', 20))).toBe(false)
  await page.evaluate(() => window.TunnelUI?.updateKeyUsage('k2', 999))
  await expect(gauge).toHaveAttribute('aria-valuenow', '100')
})

test('dialog traps focus, makes the background inert, closes on Escape and restores focus', async ({ page }) => {
  const trigger = current(page).locator('[data-action="key-preview"]')
  await trigger.click()
  await expect(page.locator('#modal')).toBeVisible()
  await expect(page.locator('.modal-close')).toBeFocused()
  await expect(page.locator('#screen-content')).toHaveAttribute('inert', '')
  await page.keyboard.press('Shift+Tab')
  await expect(page.locator('#modal .modal-full-btn')).toBeFocused()
  await page.keyboard.press('Tab'); await expect(page.locator('.modal-close')).toBeFocused()
  await page.keyboard.press('Escape')
  await expect(page.locator('#modal')).toHaveCount(0)
  await expect(trigger).toBeFocused()
})

test('all four key filters and per-key actions work', async ({ page }) => {
  await tab(page, 'keys')
  await expect(page.locator('.key-card')).toHaveCount(4)
  for (const [filter, count] of [['active', 2], ['expiring', 1], ['expired', 1], ['all', 4]] as const) {
    await page.locator(`[data-filter="${filter}"]`).click(); await expect(page.locator('.key-card')).toHaveCount(count)
  }
  await page.locator('.key-card [data-action="show-qr"]').first().click()
  await expect(page.locator('.modal-qr-note')).toContainText('Demo preview')
  await page.keyboard.press('Escape')
  await page.locator('.key-card [data-action="replace"]').first().click()
  await expect(page.locator('#modal-title')).toContainText('Key')
})

test('custom top-up, payment method and receipt survive tab switches; demo cannot charge', async ({ page }) => {
  await tab(page, 'shop')
  await page.locator('.plan-card[data-plan="VIP"]').click()
  await expect(page.locator('.plan-card.selected')).toHaveAttribute('data-plan', 'VIP')
  await page.locator('[data-amount="custom"]').click()
  await page.locator('#custom-amount').fill('3456')
  await page.locator('[data-method="wave"]').click()
  await page.locator('#receipt-file').setInputFiles({ name: 'receipt.png', mimeType: 'image/png', buffer: Buffer.from('iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+jK1sAAAAASUVORK5CYII=', 'base64') })
  await expect(page.locator('.upload-text strong')).toHaveText('receipt.png')
  await page.locator('[data-action="show-payment"]').click()
  await expect(page.locator('#modal-title')).toHaveText('WavePay · 3,456 Ks')
  await page.keyboard.press('Escape')
  await tab(page, 'overview'); await tab(page, 'shop')
  await expect(page.locator('#custom-amount')).toHaveValue('3456')
  await expect(page.locator('.upload-text strong')).toHaveText('receipt.png')
  await expect(page.locator('[data-method="wave"]')).toHaveAttribute('aria-pressed', 'true')
  await expect.poll(() => page.locator('.uploaded-preview').evaluate(node => (node as HTMLImageElement).naturalWidth)).toBe(1)
  await page.locator('#custom-amount').fill('499')
  await page.locator('[data-action="show-payment"]').click()
  await expect(page.locator('#modal')).toHaveCount(0)
  await expect(page.locator('#toast')).toContainText('500 Ks')
  await page.locator('[data-action="purchase-plan"]').click()
  await expect(page.locator('#modal-title')).toHaveText('VIP Plan')
  await expect(page.locator('#modal-body')).toContainText('မသတ်မှတ်ရသေး')
})

test('daily reward is once-only and reflected across views', async ({ page }) => {
  await page.locator('.wallet-actions [data-action="claim"]').click()
  await page.locator('.wallet-actions [data-action="claim"]').click()
  await expect(page.locator('.wallet-meta')).toContainText('130 Pts')
  await tab(page, 'history')
  await expect(page.locator('.reward-points')).toContainText('130')
  await expect(page.locator('.reward-banner [data-action="claim"]')).toBeDisabled()
  await expect(page.locator('.leader-row.you .leader-score')).toHaveText('130 pts')
  await page.locator('[data-action="all-history"]').click()
  await expect(page.locator('#modal-title')).toHaveText('Purchase history')
  await page.keyboard.press('Escape')
  await page.locator('[data-action="leaderboard"]').click()
  await expect(page.locator('#modal-title')).toHaveText('Leaderboard')
})

test('valid keys control 0–3 cards, dots and empty state; host names are escaped', async ({ page }) => {
  for (const count of [2, 1, 0, 3]) {
    const valid = demoKeys.filter(key => key.status !== 'expired').slice(0, count)
    await page.evaluate(keys => window.TunnelUI?.setKeys(keys), valid)
    await expect(page.locator('.snapshot-card')).toHaveCount(count)
    await expect(page.locator('.stack-dot')).toHaveCount(count > 1 ? count : 0)
    if (count === 0) await expect(page.locator('.snapshot-section .empty-state')).toBeVisible()
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
        return { bodyOverflow: document.documentElement.scrollWidth - innerWidth, contentOverflow: content.scrollWidth - content.clientWidth }
      })
      expect(dimensions.bodyOverflow, `${width}px ${screen} body`).toBeLessThanOrEqual(1)
      expect(dimensions.contentOverflow, `${width}px ${screen} content`).toBeLessThanOrEqual(1)
    }
  }
})

test('reduced motion removes loops without breaking selection or usage', async ({ page }) => {
  await page.emulateMedia({ reducedMotion: 'reduce' })
  await expect(current(page).locator('[data-percent-number]')).toHaveText('29')
  await expect(current(page).locator('.wave-front')).toHaveCSS('animation-name', 'none')
  await page.locator('[data-snapshot-index="2"]').click()
  await expect(current(page).locator('[data-percent-number]')).toHaveText('88')
  await expect(page.locator('#snapshot-current')).toHaveText('03')
})

test('optional Telegram identity and native swipe integration are guarded', async ({ page }) => {
  await page.addInitScript(() => {
    window.Telegram = { WebApp: {
      initDataUnsafe: { user: { id: 123456, first_name: 'Telegram', last_name: 'User' } },
      isVerticalSwipesEnabled: true,
      disableVerticalSwipes() { this.isVerticalSwipesEnabled = false },
      enableVerticalSwipes() { this.isVerticalSwipesEnabled = true },
    } }
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
  await expect(frame.locator('[data-depth="0"] [data-percent-number]')).toHaveText('29')
  await frame.locator('[data-snapshot-index="2"]').click(); await settle(page)
  await expect(frame.locator('#snapshot-current')).toHaveText('03')
  await frame.locator('.nav-item[data-tab="shop"]').click()
  await expect(frame.locator('.plans-grid')).toBeVisible()
  expect(requests).toEqual([])
})
