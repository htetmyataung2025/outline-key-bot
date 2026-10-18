import { computed, inject, markRaw, onScopeDispose, provide, reactive, watch } from 'vue'
import type { InjectionKey } from 'vue'
import { demoKeys, demoUser } from '../data/demo'
import { clamp, formatNumber, memberFromUser } from '../utils/format'
import type { AppDialog, KeyFilter, Member, PaymentMethod, PlanName, Receipt, TabId, TelegramUser, Toast, TopUpAmount, VpnKey } from '../types'
import type { IconName } from '../types/icons'

/** A store scoped to one mounted app, not a module-level singleton. */
export function createMiniApp() {
  const state = reactive({
    tab: 'overview' as TabId,
    filter: 'all' as KeyFilter,
    keys: demoKeys.map(key => ({ ...key })),
    selectedKeyId: 'k2' as string | null,
    selectedPlan: 'Basic' as PlanName,
    selectedAmount: 2000 as TopUpAmount,
    customAmount: '',
    paymentMethod: 'kbz' as PaymentMethod,
    walletBalance: 5000,
    points: 120,
    claimedToday: false,
    cooldownHours: 4,
    cooldownRemaining: 0,
    user: memberFromUser(demoUser) as Member,
    receipt: null as Receipt | null,
    dialog: null as AppDialog | null,
    toast: { message: '', icon: 'check-circle', visible: false } as Toast,
  })
  const activeKeys = computed(() => state.keys.filter(key => key.status !== 'expired').sort((a, b) => Number(b.connected) - Number(a.connected)))
  const visibleKeys = computed(() => state.keys.filter(key => state.filter === 'all' || key.status === state.filter))
  const topUpAmount = computed(() => state.selectedAmount === 'custom' ? Number(state.customAmount) : state.selectedAmount)
  const amountLabel = computed(() => state.selectedAmount === 'custom' && !state.customAmount ? 'Custom' : formatNumber(topUpAmount.value))
  let toastTimer: ReturnType<typeof setTimeout> | undefined

  watch(activeKeys, keys => { if (!keys.some(key => key.id === state.selectedKeyId)) state.selectedKeyId = keys[0]?.id ?? null })
  function showToast(message: string, icon: IconName = 'check-circle') {
    clearTimeout(toastTimer)
    state.toast = { message, icon, visible: true }
    toastTimer = setTimeout(() => { state.toast.visible = false }, 3000)
  }
  function setTab(tab: TabId) { state.dialog = null; state.tab = tab; state.filter = 'all' }
  function openDialog(dialog: AppDialog) { state.dialog = dialog }
  function closeDialog() { state.dialog = null }
  function setUser(user: TelegramUser) { state.user = memberFromUser(user) }
  function updateKeyUsage(id: string, usedGB: number): boolean {
    const item = state.keys.find(key => key.id === id)
    if (!item || !Number.isFinite(usedGB)) return false
    item.used = clamp(usedGB, 0, Math.max(0, item.quota))
    return true
  }
  function setKeys(keys: VpnKey[]) {
    if (new Set(keys.map(key => key.id)).size !== keys.length) throw new Error('VPN key IDs must be unique')
    state.keys = keys.map(key => ({ ...key, quota: Math.max(0, key.quota), used: clamp(key.used, 0, Math.max(0, key.quota)) }))
  }
  function claimReward() {
    if (state.claimedToday) {
      showToast(`⏳ နောက် Claim အထိ ${state.cooldownHours} နာရီ စောင့်ပေးပါ`, 'info')
      return
    }
    state.claimedToday = true
    state.cooldownRemaining = state.cooldownHours * 3600
    state.points += 10
    showToast(`Claim အောင်မြင်ပါသည် · +10 Points ရရှိပါပြီ (${state.cooldownHours} နာရီခြား Claim နိုင်ပါသည်)`)
  }
  function selectReceipt(file?: File) {
    if (!file) return
    if (!file.type.startsWith('image/')) { showToast('ပုံဖိုင်ကိုသာ ရွေးပေးပါ', 'info'); return }
    if (file.size > 10 * 1024 * 1024) { showToast('10 MB ထက်ငယ်သော ပုံကို ရွေးပေးပါ', 'info'); return }
    if (state.receipt) URL.revokeObjectURL(state.receipt.url)
    state.receipt = { name: file.name, file: markRaw(file), url: URL.createObjectURL(file) }
    showToast('Screenshot ကို ရွေးပြီးပါပြီ')
  }
  function showPayment(): boolean {
    const amount = topUpAmount.value
    if (!Number.isInteger(amount) || amount < 500 || amount > 10_000_000) {
      showToast('500 Ks မှ 10,000,000 Ks အတွင်း ငွေပမာဏထည့်ပါ', 'info')
      return false
    }
    openDialog({ kind: 'payment', method: state.paymentMethod, amount })
    return true
  }
  async function copyKey(value: string) {
    let copied = false
    try { if (navigator.clipboard?.writeText) { await navigator.clipboard.writeText(value); copied = true } } catch { /* Visible fallback below. */ }
    if (!copied) {
      const focused = document.activeElement instanceof HTMLElement ? document.activeElement : null
      const field = document.createElement('textarea')
      field.value = value; field.readOnly = true; field.style.cssText = 'position:fixed;left:-9999px;top:0'
      document.body.append(field); field.select()
      try { copied = document.execCommand('copy') } catch { copied = false }
      field.remove(); focused?.focus({ preventScroll: true })
    }
    if (copied) showToast('Demo key ကို copy လုပ်ပြီးပါပြီ')
    else openDialog({ kind: 'manual-copy', value })
  }
  onScopeDispose(() => { clearTimeout(toastTimer); if (state.receipt) URL.revokeObjectURL(state.receipt.url) })
  return { state, activeKeys, visibleKeys, topUpAmount, amountLabel, showToast, setTab, openDialog, closeDialog, setUser, updateKeyUsage, setKeys, claimReward, selectReceipt, showPayment, copyKey }
}
export type MiniApp = ReturnType<typeof createMiniApp>
const miniAppKey: InjectionKey<MiniApp> = Symbol('tunnel-mini-app')
export function provideMiniApp() { const app = createMiniApp(); provide(miniAppKey, app); return app }
export function useMiniApp(): MiniApp {
  const app = inject(miniAppKey)
  if (!app) throw new Error('useMiniApp must be called below the app provider')
  return app
}
