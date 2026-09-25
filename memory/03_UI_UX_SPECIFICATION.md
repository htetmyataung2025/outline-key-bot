# Vue 3 + Naive UI Design & Layout Specification

## 1. Visual Identity & Theme Tokens
Modeled after the **OpsTranslate Control Center** dark-themed operational aesthetics:

| Token Name | Color Code | Description |
|---|---|---|
| **Background Darkest** | `#0b1120` | Root application background |
| **Surface Dark** | `#0f172a` | Sidebar, header, modal backgrounds |
| **Card Surface** | `#1e293b` | Elevated cards, stat boxes, table headers |
| **Border Subtle** | `#334155` | Dividers and input container borders |
| **Primary Accent (Emerald)** | `#10b981` | Action buttons, active badges, trend lines |
| **Primary Glow** | `rgba(16, 185, 129, 0.15)` | Active navigation tabs, stat icons background |
| **Warning / Pending** | `#f59e0b` | Pending slip count, approaching data limit |
| **Danger / Error** | `#ef4444` | Server offline, revoke key, reject slip |
| **Text Primary** | `#f8fafc` | Main headings, key values |
| **Text Secondary** | `#94a3b8` | Subtitles, helper text, labels |

### Naive UI Theme Configuration:
```typescript
import { GlobalThemeOverrides, darkTheme } from 'naive-ui'

export const themeOverrides: GlobalThemeOverrides = {
  common: {
    primaryColor: '#10b981',
    primaryColorHover: '#34d399',
    primaryColorPressed: '#059669',
    primaryColorSuppl: '#10b981',
    bodyColor: '#0b1120',
    cardColor: '#1e293b',
    textColorBase: '#f8fafc',
    borderRadius: '8px',
  },
  Card: {
    borderColor: '#334155',
  },
  DataTable: {
    headerColor: '#1e293b',
    headerTextColor: '#94a3b8',
    borderColor: '#334155',
  }
}
```

---

## 2. Page & Component Structure

```
src/
├── assets/                  # CSS tokens, svg icons
├── components/
│   ├── layout/
│   │   ├── AppHeader.vue    # Clock (Yangon Time), Live status pill, Quick refresh
│   │   ├── AppSidebar.vue   # OpsTranslate-style navigation icons & titles
│   │   └── MobileNav.vue    # Bottom drawer navigation for Telegram Mini App
│   ├── overview/
│   │   ├── ServerCard.vue   # Outline server latency, status, bandwidth
│   │   ├── StatCard.vue     # Total keys, active users, revenue KPI cards
│   │   └── TrafficChart.vue # Chart.js / ECharts line graph of transfer history
│   ├── keys/
│   │   ├── KeyTable.vue     # NDataTable with usage progress bars & tags
│   │   └── KeyCreateModal.vue # Modal for manual key dispatch
│   ├── slips/
│   │   ├── SlipCard.vue     # Image lightbox, OCR badge, Approve/Reject
│   │   └── SlipQueue.vue    # Grid of pending payments
│   └── redeems/
│       ├── BatchGenModal.vue # Step wizard (amount -> mode -> days -> count)
│       └── RedeemTable.vue  # Active redeem codes table
└── views/
    ├── OverviewView.vue
    ├── KeysView.vue
    ├── SlipsView.vue
    ├── CustomersView.vue
    └── AuditLogsView.vue
```

---

## 3. Responsive Adaptations (Desktop vs Telegram Mini App)

### 3.1 Desktop (`window.innerWidth >= 1024px`)
- **Navigation**: Fixed left sidebar (width: 240px) with icons and text badges.
- **Data Display**: Full `n-data-table` with sortable columns, multi-select, and pagination.
- **Modals**: Centered floating dialogs (`n-modal`) with backdrop blur.

### 3.2 Mobile / Telegram Mini App (`window.innerWidth < 1024px`)
- **Navigation**:
  - Top header displays compact logo + Yangon time.
  - Left sidebar collapses into a slide-over drawer or bottom tab bar (`n-tabs`).
- **Data Display**:
  - `n-data-table` switches to responsive card-list view (`SlipCard`, `KeyCard`) for easy thumb navigation on mobile phones.
- **Telegram Native Controls**:
  - Integrates `window.Telegram.WebApp.BackButton` to navigate back between views.
  - Integrates `window.Telegram.WebApp.HapticFeedback.impactOccurred('medium')` on button taps.
  - Automatically matches Telegram client color theme.
