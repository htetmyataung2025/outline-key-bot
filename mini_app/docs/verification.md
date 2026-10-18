# Migration verification

Verified on 17 October 2026 with Node 20.20.2, npm 10.8.2, Vue 3.5.44, Vite 7.3.1, TypeScript 5.9.3, Tailwind CSS 4.3.3 and Playwright Chromium 156.

## Results

- `npm run typecheck`: PASS (strict Vue/TypeScript, including tests and configuration).
- `npm run build`: PASS (69 modules, production bundle and standalone compiled-Vue HTML).
- `npm run test:e2e`: **13 passed**, 0 failed, 0 skipped, final run 25.0 seconds.
- No browser `pageerror` in any test.
- Desktop/mobile screenshots reviewed visually against the V2 layout.

## Browser regression coverage

| Check | Result |
| --- | --- |
| Compact Telegram name/ID header, 37 SVG symbols, decorated cards and actual usage | PASS |
| Real touch gestures: up → next, down → previous, both bounds | PASS |
| Dots, Arrow Up/Down, Home/End, wheel and button-origin drag protection | PASS |
| 0/100% liquid endpoints, usage API/event and continuously moving waves with unchanged usage | PASS |
| Dialog focus trap, inert background, Escape and focus restoration | PASS |
| Key filters and per-key connect/QR/replace actions | PASS |
| Custom 3,456 Ks top-up, WavePay choice, receipt retention, range validation and demo checkout | PASS |
| Daily claim grants +10 once and updates wallet/rewards/leaderboard | PASS |
| Dynamic 0/1/2/3 active keys and HTML-safe host identity display | PASS |
| All four screens at 320, 360, 375, 390, 432, 540, 690, 691, 768, 1024, 1440 px; no horizontal overflow | PASS |
| Reduced-motion preference stops loops without breaking values/selection | PASS |
| Optional Telegram identity and native swipe disable/restore mock | PASS |
| Production Vue export in opaque-origin `sandbox="allow-scripts"` iframe, external requests blocked | PASS |

The ZIP includes the test source. Run `npx playwright install --with-deps chromium`, then `npm run build && npm run test:e2e` to reproduce.

## Scope

This verifies the frontend UI demo, not real VPN connectivity, payment processing, persistent rewards, authentication or production Telegram server validation. These require a backend and separate integration testing.
