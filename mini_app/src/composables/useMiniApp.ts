import { computed, inject, markRaw, onMounted, onScopeDispose, provide, reactive, watch } from 'vue'
import type { InjectionKey } from 'vue'
import { demoKeys, demoUser, plans as defaultPlans } from '../data/demo'
import { clamp, formatNumber, memberFromUser } from '../utils/format'
import { api } from '../services/api'
import type {
  AppDialog,
  KeyFilter,
  LeaderboardRow,
  Member,
  PaymentMethod,
  PaymentMethodInfo,
  PlanName,
  PurchaseRecord,
  Receipt,
  ServerOption,
  SlipRecord,
  TabId,
  TelegramUser,
  Toast,
  TopUpAmount,
  VpnKey,
} from '../types'
import type { IconName } from '../types/icons'

/** A store scoped to one mounted app, not a module-level singleton. */
export function createMiniApp() {
  const state = reactive({
    loading: false,
    isSubmitting: false,
    tab: 'overview' as TabId,
    filter: 'all' as KeyFilter,
    keys: demoKeys.map(key => ({ ...key })),
    plans: defaultPlans.map(p => ({ ...p })),
    servers: [
      { id: '1', name: 'Server 1 (SG-1)', location: 'Singapore', country: 'SG', flag: '🇸🇬' },
      { id: '2', name: 'Server 2 (SG-2)', location: 'Singapore', country: 'SG', flag: '🇸🇬' },
      { id: '3', name: 'Server 3 (VIP)', location: 'Singapore', country: 'SG', flag: '🇸🇬' },
    ] as ServerOption[],
    selectedServerId: '1',
    paymentMethods: {
      kbz: { name: 'KBZPay', account_name: 'Htet Myat Aung', phone: '09699970092', type: 'QR / Direct Transfer' },
      wave: { name: 'WavePay', account_name: 'Htet Myat Aung', phone: '09699970092', type: 'QR / Direct Transfer' },
    } as Record<string, PaymentMethodInfo>,
    history: {
      purchases: [] as PurchaseRecord[],
      slips: [] as SlipRecord[],
    },
    leaderboard: {
      period: '',
      rows: [] as LeaderboardRow[],
    },
    selectedKeyId: 'k2' as string | null,
    selectedPlan: 'Basic' as PlanName,
    selectedAmount: 2000 as TopUpAmount,
    customAmount: '',
    paymentMethod: 'kbz' as PaymentMethod,
    walletBalance: 5000,
    points: 120,
    claimedToday: false,
    streakDays: 0,
    cooldownHours: 4,
    cooldownRemaining: 0,
    user: memberFromUser(demoUser) as Member,
    receipt: null as Receipt | null,
    dialog: null as AppDialog | null,
    toast: { message: '', icon: 'check-circle', visible: false } as Toast,
  })

  let countdownTimer: ReturnType<typeof setInterval> | undefined

  function startCountdown() {
    if (countdownTimer) clearInterval(countdownTimer)
    countdownTimer = setInterval(() => {
      if (state.cooldownRemaining > 0) {
        state.cooldownRemaining--
        if (state.cooldownRemaining <= 0) {
          state.claimedToday = false
          state.cooldownRemaining = 0
        }
      }
    }, 1000)
  }

  const cooldownFormatted = computed(() => {
    const secs = state.cooldownRemaining
    if (secs <= 0) return ''
    const h = Math.floor(secs / 3600)
    const m = Math.floor((secs % 3600) / 60)
    const s = secs % 60
    const pad = (n: number) => n.toString().padStart(2, '0')
    if (h > 0) {
      return `${pad(h)}:${pad(m)}:${pad(s)}`
    }
    return `${pad(m)}:${pad(s)}`
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
    toastTimer = setTimeout(() => { state.toast.visible = false }, 3500)
  }

  function setTab(tab: TabId) {
    state.dialog = null
    state.tab = tab
    state.filter = 'all'
    if (tab === 'history') {
      fetchHistory()
      fetchLeaderboard()
    }
  }

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

  /** Hydrate live state from Backend GET /api/user/bootstrap */
  async function bootstrap(): Promise<boolean> {
    if (!api.hasAuth()) return false
    state.loading = true
    try {
      const data = await api.getBootstrap()
      if (data.user) {
        state.user = {
          id: String(data.user.id),
          name: data.user.name,
          initials: data.user.initials || 'M',
        }
      }
      if (data.wallet) {
        state.walletBalance = data.wallet.balance ?? 0
        state.points = data.wallet.points ?? 0
        state.claimedToday = Boolean(data.wallet.claimed_today)
        state.streakDays = data.wallet.streak_days ?? (state.claimedToday ? 1 : 0)
        state.cooldownHours = data.wallet.cooldown_hours || 4
        state.cooldownRemaining = data.wallet.cooldown_remaining || 0
        if (state.cooldownRemaining > 0) {
          startCountdown()
        }
      }
      if (Array.isArray(data.keys)) {
        state.keys = data.keys
        if (!state.keys.some(k => k.id === state.selectedKeyId)) {
          state.selectedKeyId = state.keys[0]?.id ?? null
        }
      }
      if (Array.isArray(data.servers) && data.servers.length > 0) {
        state.servers = data.servers
        if (!state.servers.some(s => s.id === state.selectedServerId)) {
          state.selectedServerId = state.servers[0]?.id ?? '1'
        }
      }
      if (data.payment_methods) {
        state.paymentMethods = data.payment_methods
      }
      if (Array.isArray(data.plans) && data.plans.length > 0) {
        state.plans = data.plans.map(p => ({
          name: p.name,
          code: p.code,
          quota: typeof p.quota === 'string' ? parseFloat(p.quota) || 50 : p.quota,
          description: p.description,
          icon: (p.symbol === 'zap' ? 'zap' : (p.symbol === 'crown' ? 'crown' : 'leaf')) as IconName,
          price: p.price,
        }))
      }
      return true
    } catch (err: any) {
      console.warn('Bootstrap failed, retaining local state:', err)
      return false
    } finally {
      state.loading = false
    }
  }

  /** Daily loyalty points reward claim */
  async function claimReward() {
    if (state.claimedToday) {
      // Cooldown active: do not fire duplicate requests or spam toasts
      return
    }

    if (!api.hasAuth()) {
      state.claimedToday = true
      state.streakDays = (state.streakDays || 0) + 1
      state.cooldownRemaining = state.cooldownHours * 3600
      state.points += 10
      startCountdown()
      showToast(`Daily Claim · +10 Points ရရှိပါပြီ`)
      return
    }

    state.isSubmitting = true
    try {
      const res = await api.claimReward()
      state.claimedToday = true
      state.points = res.new_balance
      state.streakDays = res.streak_days ?? ((state.streakDays || 0) + 1)
      state.cooldownRemaining = res.next_in_s
      state.cooldownHours = res.cooldown_hours
      startCountdown()
      window.Telegram?.WebApp?.HapticFeedback?.notificationOccurred?.('success')
      showToast(res.message || `+${res.awarded} Points ရရှိပါသည်!`)
    } catch (err: any) {
      window.Telegram?.WebApp?.HapticFeedback?.notificationOccurred?.('error')
      showToast(err.message || 'Claim ပြုလုပ်၍မရသေးပါ', 'info')
    } finally {
      state.isSubmitting = false
    }
  }

  /** 1-Click purchase using wallet balance */
  async function purchasePlan(planName: PlanName, serverId: string = state.selectedServerId) {
    if (!api.hasAuth()) {
      showToast('Demo preview ဖြစ်သောကြောင့် ဝယ်ယူ၍မရသေးပါ', 'info')
      return
    }

    state.isSubmitting = true
    try {
      const targetPlan = state.plans.find(p => p.name === planName)
      const planCode = targetPlan?.code || planName.toLowerCase()
      const res = await api.purchasePlan(planCode, serverId)

      state.walletBalance = res.remaining_balance
      if (res.key_details) {
        state.keys.unshift(res.key_details)
        state.selectedKeyId = res.key_details.id
      }
      closeDialog()
      window.Telegram?.WebApp?.HapticFeedback?.notificationOccurred?.('success')
      showToast(res.message || 'Plan ဝယ်ယူမှု အောင်မြင်ပါသည်!')
      if (res.key_details?.id) {
        openDialog({ kind: 'connect', keyId: res.key_details.id })
      }
    } catch (err: any) {
      window.Telegram?.WebApp?.HapticFeedback?.notificationOccurred?.('error')
      showToast(err.message || 'ဝယ်ယူမှု မအောင်မြင်ပါ', 'info')
    } finally {
      state.isSubmitting = false
    }
  }

  function selectReceipt(file?: File) {
    if (!file) return
    if (!file.type.startsWith('image/')) { showToast('ပုံဖိုင်ကိုသာ ရွေးပေးပါ', 'info'); return }
    if (file.size > 10 * 1024 * 1024) { showToast('10 MB ထက်ငယ်သော ပုံကို ရွေးပေးပါ', 'info'); return }
    if (state.receipt) URL.revokeObjectURL(state.receipt.url)
    state.receipt = { name: file.name, file: markRaw(file), url: URL.createObjectURL(file) }
    showToast('Screenshot ကို ရွေးပြီးပါပြီ')
  }

  /** Submit payment slip receipt for OCR/Admin approval */
  async function submitTopUp(): Promise<boolean> {
    const amount = topUpAmount.value
    if (!Number.isInteger(amount) || amount < 500 || amount > 10_000_000) {
      showToast('500 Ks မှ 10,000,000 Ks အတွင်း ငွေပမာဏထည့်ပါ', 'info')
      return false
    }
    if (!state.receipt?.file) {
      showToast('ငွေလွှဲ Screenshot ပုံ ရွေးပေးပါ', 'info')
      return false
    }

    if (!api.hasAuth()) {
      showToast('Demo preview သာဖြစ်ပြီး upload မလုပ်နိုင်ပါ', 'info')
      return false
    }

    state.isSubmitting = true
    try {
      const res = await api.uploadSlip(state.receipt.file, amount, state.paymentMethod)
      state.receipt = null
      closeDialog()
      window.Telegram?.WebApp?.HapticFeedback?.notificationOccurred?.('success')
      showToast(res.message || 'ငွေလွှဲပြေစာ ပေးပို့ပြီးပါပြီ။ မကြာမီ စစ်ဆေးအတည်ပြုပေးပါမည်။')
      fetchHistory()
      return true
    } catch (err: any) {
      window.Telegram?.WebApp?.HapticFeedback?.notificationOccurred?.('error')
      showToast(err.message || 'Upload မအောင်မြင်ပါ', 'info')
      return false
    } finally {
      state.isSubmitting = false
    }
  }

  /** Queue a replacement request for an active key */
  async function requestKeyReplace(keyId: string) {
    if (!api.hasAuth()) {
      closeDialog()
      showToast('Demo preview သာဖြစ်ပြီး key ကို မပြောင်းလဲထားပါ', 'info')
      return
    }

    state.isSubmitting = true
    try {
      const res = await api.replaceKey(keyId)
      closeDialog()
      window.Telegram?.WebApp?.HapticFeedback?.notificationOccurred?.('success')
      showToast(res.message || 'Key အသစ်လဲလှယ်ရန် တင်ပြပြီးပါပြီ')
      bootstrap()
    } catch (err: any) {
      window.Telegram?.WebApp?.HapticFeedback?.notificationOccurred?.('error')
      showToast(err.message || 'Key လဲလှယ်မှု မအောင်မြင်ပါ', 'info')
    } finally {
      state.isSubmitting = false
    }
  }

  /** Fetch live purchase & slip history */
  async function fetchHistory() {
    if (!api.hasAuth()) return
    try {
      state.history = await api.getHistory()
    } catch (err) {
      console.warn('Failed to fetch history:', err)
    }
  }

  /** Fetch live points leaderboard */
  async function fetchLeaderboard() {
    if (!api.hasAuth()) return
    try {
      state.leaderboard = await api.getLeaderboard()
    } catch (err) {
      console.warn('Failed to fetch leaderboard:', err)
    }
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
    if (copied) {
      window.Telegram?.WebApp?.HapticFeedback?.impactOccurred?.('light')
      showToast('Outline Access Key ကို copy လုပ်ပြီးပါပြီ')
    } else {
      openDialog({ kind: 'manual-copy', value })
    }
  }

  onMounted(() => {
    bootstrap()
  })

  onScopeDispose(() => {
    clearTimeout(toastTimer)
    if (countdownTimer) clearInterval(countdownTimer)
    if (state.receipt) URL.revokeObjectURL(state.receipt.url)
  })

  return {
    state,
    activeKeys,
    visibleKeys,
    topUpAmount,
    amountLabel,
    showToast,
    setTab,
    openDialog,
    closeDialog,
    setUser,
    updateKeyUsage,
    setKeys,
    bootstrap,
    claimReward,
    purchasePlan,
    submitTopUp,
    requestKeyReplace,
    fetchHistory,
    fetchLeaderboard,
    selectReceipt,
    showPayment,
    copyKey,
    cooldownFormatted,
  }
}

export type MiniApp = ReturnType<typeof createMiniApp>
const miniAppKey: InjectionKey<MiniApp> = Symbol('tunnel-mini-app')
export function provideMiniApp() { const app = createMiniApp(); provide(miniAppKey, app); return app }
export function useMiniApp(): MiniApp {
  const app = inject(miniAppKey)
  if (!app) throw new Error('useMiniApp must be called below the app provider')
  return app
}
