import type { GlobalThemeOverrides } from 'naive-ui'

// Naive UI overrides — mirrors the CSS tokens in src/styles/tokens.css.
// Keep these hex values in sync with the :root variables there.
export const themeOverrides: GlobalThemeOverrides = {
  common: {
    primaryColor: '#10b981',
    primaryColorHover: '#34d399',
    primaryColorPressed: '#059669',
    primaryColorSuppl: '#10b981',
    infoColor: '#0ea5e9',
    successColor: '#10b981',
    warningColor: '#f59e0b',
    errorColor: '#ef4444',
    bodyColor: '#080c14',
    cardColor: '#0e1526',
    modalColor: '#0e1526',
    popoverColor: '#0e1526',
    tableColor: '#0e1526',
    textColorBase: '#f8fafc',
    textColor1: '#f8fafc',
    textColor2: '#cbd5e1',
    textColor3: '#94a3b8',
    borderColor: 'rgba(255, 255, 255, 0.08)',
    dividerColor: 'rgba(255, 255, 255, 0.06)',
    borderRadius: '12px',
    fontFamily: "'Inter', system-ui, -apple-system, sans-serif",
    fontFamilyMono: "'JetBrains Mono', monospace",
  },
  Card: {
    borderColor: 'rgba(255, 255, 255, 0.08)',
    color: '#0e1526',
    textColor: '#f8fafc',
    titleTextColor: '#f8fafc',
    borderRadius: '14px',
  },
  DataTable: {
    headerColor: '#0a1120',
    headerTextColor: '#94a3b8',
    borderColor: 'rgba(255, 255, 255, 0.07)',
    thFontWeight: '600',
    tdColorHover: 'rgba(255, 255, 255, 0.03)',
  },
  Button: {
    borderRadiusMedium: '10px',
    fontWeight: '600',
  },
  Tabs: {
    tabTextColorActiveLine: '#10b981',
    tabTextColorHoverLine: '#34d399',
    barColor: '#10b981',
  },
}
