import type { TelegramUser, VpnKey } from './index'

export interface TelegramWebApp {
  initData?: string
  initDataUnsafe?: { user?: TelegramUser }
  isVerticalSwipesEnabled?: boolean
  disableVerticalSwipes?: () => void
  enableVerticalSwipes?: () => void
  ready?: () => void
  expand?: () => void
  close?: () => void
  setHeaderColor?: (color: string) => void
  setBackgroundColor?: (color: string) => void
  openLink?: (url: string, options?: { try_instant_view?: boolean }) => void
  openTelegramLink?: (url: string) => void
  HapticFeedback?: {
    impactOccurred?: (style: 'light' | 'medium' | 'heavy' | 'rigid' | 'soft') => void
    notificationOccurred?: (type: 'error' | 'success' | 'warning') => void
    selectionChanged?: () => void
  }
}
export interface TunnelBridge {
  updateKeyUsage: (id: string, usedGB: number) => boolean
  setUser: (user: TelegramUser) => void
  setKeys: (keys: VpnKey[]) => void
}
declare global {
  interface Window {
    Telegram?: { WebApp?: TelegramWebApp }
    TunnelUI?: TunnelBridge
  }
  interface WindowEventMap {
    'tunnel:usage': CustomEvent<{ id: string; usedGB: number }>
  }
}
