import { onMounted, onScopeDispose, watch } from 'vue'
import type { MiniApp } from './useMiniApp'

/** Optional host bridge; importing the app never loads a remote Telegram SDK. */
export function useTelegram(app: MiniApp) {
  let swipesManaged = false
  let mounted = false
  const previousBridge = window.TunnelUI
  function syncSwipes() {
    if (!mounted) return
    const webApp = window.Telegram?.WebApp
    if (!webApp) return
    try {
      if (app.state.tab === 'overview' && app.activeKeys.value.length > 1) {
        if (!swipesManaged && webApp.isVerticalSwipesEnabled !== false && webApp.disableVerticalSwipes) { webApp.disableVerticalSwipes(); swipesManaged = true }
      } else if (swipesManaged && webApp.enableVerticalSwipes) { webApp.enableVerticalSwipes(); swipesManaged = false }
    } catch { /* Older SDKs: the browser gestures still work normally. */ }
  }
  const onUsage = (event: WindowEventMap['tunnel:usage']) => { if (event.detail) app.updateKeyUsage(event.detail.id, event.detail.usedGB) }
  watch([() => app.state.tab, () => app.activeKeys.value.length], syncSwipes, { flush: 'post' })
  onMounted(() => {
    mounted = true
    // Display ONLY. A real backend MUST validate Telegram initData for auth.
    const user = window.Telegram?.WebApp?.initDataUnsafe?.user
    if (user) app.setUser(user)
    window.TunnelUI = { updateKeyUsage: app.updateKeyUsage, setUser: app.setUser, setKeys: app.setKeys }
    window.addEventListener('tunnel:usage', onUsage)
    syncSwipes()
  })
  onScopeDispose(() => {
    window.removeEventListener('tunnel:usage', onUsage)
    if (swipesManaged) window.Telegram?.WebApp?.enableVerticalSwipes?.()
    if (previousBridge) window.TunnelUI = previousBridge; else delete window.TunnelUI
  })
}
