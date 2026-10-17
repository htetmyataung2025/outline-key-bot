# TUNNEL — Vue 3 Mini App

မူလ V2 design နဲ့ interactions ကို **Vue 3 Composition API + Vite + TypeScript + Tailwind CSS v4** ဖြင့် ပြန်ရေးထားသော frontend project ဖြစ်ပါတယ်။ Legacy HTML ကို iframe နဲ့ထည့်ထားခြင်း၊ `innerHTML` နဲ့ screen rendering လုပ်ထားခြင်းမဟုတ်ပါ။ UI အားလုံး Vue Single-File Components ဖြစ်ပါတယ်။

> **UI demo only.** No live VPN, authentication, payment processing, or backend. Do not transfer money using this preview. Prices are intentionally unset; QR icons are illustrative and not scannable. Demo state resets on reload. Receipt images remain in browser memory only; no file is uploaded to a server.

## Run

Use **Node.js 20.19+ or 22.12+** (tested with Node 20.20.2) and npm.

```bash
npm ci
npm run dev
```

Open the URL printed by Vite (default port **3000**). The development server binds to `0.0.0.0` for the Arena live preview. See the security note below before exposing a development server outside a trusted environment.

```bash
npm run typecheck    # strict Vue + TypeScript checks
npm run build        # typecheck, production bundle, offline HTML preview
npm run preview      # serve the production dist/ directory
```

### Offline / single-file preview

`npm run build` also creates `artifacts/tunnel-vue-preview.html`. This file contains the **actual compiled Vue application**, styles, SVG symbols, and both fonts; no CDN or remote SDK is needed. You can open it directly in a modern browser or in an `allow-scripts` sandboxed preview.

The source ZIP includes a prebuilt copy in `preview/`. This is a convenient preview, not a substitute for the component source.

### Browser tests

```bash
npx playwright install --with-deps chromium
npm run build
npm run test:e2e
```

Playwright starts a temporary Vite test server on port 4174 and stops it when tests finish. To reuse a running local server:

```bash
TEST_BASE_URL=http://127.0.0.1:3000 npm run test:e2e
```

Tests cover real touch gestures, keyboard/wheel/dots, 0/100% liquid levels, live usage updates, filters, modal accessibility, receipt retention, payment validation, once-only reward claiming, dynamic 0–3 key states, reduced motion, Telegram SDK mocks, 11 responsive widths, and the offline sandboxed Vue build.

## Project structure

```text
src/
  App.vue                    App provider, screen switching, accessible shell
  main.ts                    Vue application entry point
  style.css                  Tailwind theme/@apply + custom art and animations
  assets/fonts/              Local Manrope + Noto Sans Myanmar WOFF2
  components/
    layout/                  Compact header, bottom navigation, desktop intro
    overview/                Wallet, vertical key stack, liquid gauge, shortcuts
    keys/                    Reusable per-key card
    shop/                    Plan card and receipt uploader
    rewards/                 Check-in, purchase history, leaderboard
    ui/                      SVG icon system, usage bar, dialog, toast, headings
    AppDialogs.vue           Typed dialog content and actions
  composables/
    useMiniApp.ts            App-scoped provided/injected reactive state
    useKeyStack.ts           Vertical pointer/wheel/keyboard interaction + WAAPI
    useReducedMotion.ts      Reactive media query with lifecycle cleanup
    useTelegram.ts           Optional display/usage bridge + native swipe guard
  data/demo.ts               Demo keys, plan definitions and gauge palettes
  types/                     Models, dialog union, icon names, host declarations
  utils/format.ts            Percentage, numbers and member display helpers
scripts/make-standalone.mjs   Packages Vite output into one offline HTML file
tests/mini-app.spec.ts        Playwright interaction and responsive regressions
licenses/                    Original font OFL notices
```

## Design and implementation notes

- Genuine `<script setup lang="ts">` Composition API with typed props/emits, computed values, lifecycle cleanup, `defineModel`, and app-scoped `provide`/`inject`. No global singleton store, router, or extra state dependency is needed for these four tabs.
- **Tailwind CSS v4** is integrated through `@tailwindcss/vite`. Layout, sizing, typography, spacing and responsive geometry use Tailwind utilities via `@apply`; gradients, glass, wave shapes, decorative rings and keyframes remain custom CSS where appropriate. This preserves V2 instead of replacing it with a generic utility-only design.
- Four tabs: Overview, My Keys, Shop & Top-Up, History & Rewards.
- Vertical swipes: **up → next, down → previous**, bounded at both ends. Under-cards, selected dot, count and announcements stay synchronized. Buttons do not trigger a drag. Wheel, Arrow Up/Down, Home/End and dot buttons also work.
- Gauge level is derived from actual usage. **0% is empty, 100% is full**. Readout/level transitions and continuously moving waves/bars do not invent usage numbers. Inactive slides pause loops and are `inert`/`aria-hidden`.
- Modals trap focus, inert the background, restore focus and support Escape. The reduced-motion preference stops looping effects and skips stack/number transitions.
- Receipts: image MIME type, up to 10 MB; local file selection/drop, browser-memory preview, retention across tab changes, URL revocation on replacement/app teardown.
- Top-up validation: integer **500–10,000,000 Ks**. Daily claim grants **+10 points once per app session**, not persistent real rewards.
- No automatic Telegram SDK/CDN fetch. If a host already provides `window.Telegram.WebApp`, its name/ID is displayed and supported native vertical swipes are managed only while the multi-key Overview is active. **`initDataUnsafe` display values are not authentication.**

## Host / backend integration boundary

An optional display/demo bridge is installed while the app is mounted:

```ts
window.TunnelUI?.updateKeyUsage('k2', 25) // GB; clamped to the key quota
window.dispatchEvent(new CustomEvent('tunnel:usage', {
  detail: { id: 'k2', usedGB: 40 },
}))
window.TunnelUI?.setUser({ id: 12345678, first_name: 'Aung', last_name: 'Aung' })
// window.TunnelUI?.setKeys(yourTypedVpnKeyArray)
```

`updateKeyUsage` returns false for an unknown key/non-finite usage. `setKeys` requires unique IDs. UI state and this bridge are not trusted authorization mechanisms.

For production, validate Telegram **initData on a server**, authenticate key ownership, fetch real plan prices/usage, generate payment QRs on the backend, verify payment webhooks/receipts and issue VPN keys server-side. Never embed VPN-provider tokens/payment secrets in `VITE_*` variables or client source.

`vite.config.ts` allows preview hosts in this sandbox. For public deployment, serve `dist/` using your production HTTPS host instead of exposing the Vite development server; restrict development `allowedHosts` to trusted domains outside Arena. The relative Vite `base: './'` also supports subdirectory hosting.

Fonts are bundled locally under the SIL Open Font License. Their original notices are in `licenses/` and are included in the standalone export.
