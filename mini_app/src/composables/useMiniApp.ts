import { computed, inject, markRaw, onMounted, onScopeDispose, provide, reactive, watch } from 'vue'
import type { InjectionKey } from 'vue'
import { plans as defaultPlans } from '../data/demo'
import { clamp, formatNumber, memberFromUser } from '../utils/format'
import { api } from '../services/api'
import type {
  AppDialog,
  KeyFilter,
  LeaderboardMe,
  LeaderboardRow,
  Member,
  PaymentMethod,
  PaymentMethodInfo,
  Plan,
  PlanName,
  PurchaseRecord,
  Receipt,
  ServerOption,
  SlipRecord,
  TabId,
  TelegramUser,
  Toast,
  TopUpAmount,
  VpnAppId,
  VpnKey,
} from '../types'
import type { IconName } from '../types/icons'

function loadCache<T>(key: string): T | null {
  try {
    const raw = localStorage.getItem(key)
    return raw ? JSON.parse(raw) as T : null
  } catch {
    return null
  }
}

function saveCache(key: string, data: any) {
  try {
    localStorage.setItem(key, JSON.stringify(data))
  } catch {
    // sandbox / storage quota ignore
  }
}

/** A store scoped to one mounted app, not a module-level singleton. */
export function createMiniApp() {
  const getSavedTab = (): TabId => {
    try {
      const stored = localStorage.getItem('tma_active_tab') as TabId | null
      if (stored && ['overview', 'keys', 'shop', 'history'].includes(stored)) {
        return stored
      }
    } catch {
      // localStorage may fail in restricted sandboxes
    }
    return 'overview'
  }

  const cachedBootstrap = loadCache<any>('tma_cache_bootstrap_v1')
  const cachedHistory = loadCache<{ purchases: PurchaseRecord[]; slips: SlipRecord[] }>('tma_cache_history_v1')
  const cachedLeaderboard = loadCache<{ period?: string; mode?: string; rows: LeaderboardRow[]; me?: LeaderboardMe | null; total_players?: number }>('tma_cache_leaderboard_v1')
  const hasAuth = api.hasAuth()
  const hasCachedBootstrap = !!cachedBootstrap

  const state = reactive({
    loading: false,
    isInitialLoading: hasAuth && !hasCachedBootstrap,
    isManualRefreshing: false,
    isSyncing: false,
    isHistoryLoading: hasAuth && !cachedHistory,
    isLeaderboardLoading: hasAuth && !cachedLeaderboard,
    isSubmitting: false,
    isClaiming: false,
    tab: getSavedTab(),
    filter: 'all' as KeyFilter,
    keys: (cachedBootstrap?.keys && Array.isArray(cachedBootstrap.keys)) ? (cachedBootstrap.keys as VpnKey[]) : [] as VpnKey[],
    plans: ((cachedBootstrap?.plans && Array.isArray(cachedBootstrap.plans) && cachedBootstrap.plans.length > 0)
      ? cachedBootstrap.plans.map((p: any) => ({
          name: p.name,
          code: p.code,
          quota: typeof p.quota === 'string' ? parseFloat(p.quota) || 50 : p.quota,
          description: p.description,
          icon: (p.symbol === 'zap' ? 'zap' : (p.symbol === 'crown' ? 'crown' : 'leaf')) as IconName,
          price: p.price,
        }))
      : defaultPlans.map(p => ({ ...p }))) as Plan[],
    servers: (cachedBootstrap?.servers && Array.isArray(cachedBootstrap.servers)) ? (cachedBootstrap.servers as ServerOption[]) : [] as ServerOption[],
    selectedServerId: '1',
    paymentMethods: (cachedBootstrap?.payment_methods || {
      kbz: { name: 'KBZPay', account_name: 'Htet Myat Aung', phone: '09699970092', type: 'Direct Transfer / QR' },
      wave: { name: 'WavePay', account_name: 'Htet Myat Aung', phone: '09699970092', type: 'Direct Transfer / QR' },
      aya: { name: 'AYA Pay', account_name: 'Htet Myat Aung', phone: '09699970092', type: 'Direct Transfer / QR' },
      uab: { name: 'uab pay', account_name: 'Htet Myat Aung', phone: '09699970092', type: 'Direct Transfer / QR' },
      cb: { name: 'CB Pay', account_name: 'Htet Myat Aung', phone: '09699970092', type: 'Direct Transfer / QR' },
    }) as Record<string, PaymentMethodInfo>,
    history: cachedHistory || {
      purchases: [] as PurchaseRecord[],
      slips: [] as SlipRecord[],
    },
    leaderboard: cachedLeaderboard || {
      period: '',
      rows: [] as LeaderboardRow[],
      me: null as LeaderboardMe | null,
      total_players: 0,
    },
    selectedKeyId: (cachedBootstrap?.keys && cachedBootstrap.keys[0]?.id) ? cachedBootstrap.keys[0].id : null as string | null,
    selectedPlan: 'Basic' as PlanName,
    selectedAmount: 2000 as TopUpAmount,
    customAmount: '',
    paymentMethod: 'kbz' as PaymentMethod,
    walletBalance: cachedBootstrap?.wallet?.balance ?? 0,
    points: cachedBootstrap?.wallet?.points ?? 0,
    claimedToday: Boolean(cachedBootstrap?.wallet?.claimed_today),
    streakDays: cachedBootstrap?.wallet?.streak_days ?? (cachedBootstrap?.wallet?.claimed_today ? 1 : 0),
    cooldownHours: cachedBootstrap?.wallet?.cooldown_hours || 4,
    cooldownRemaining: cachedBootstrap?.wallet?.cooldown_remaining || 0,
    starterCost: cachedBootstrap?.wallet?.starter_cost ?? 5000,
    hasToppedUp: Boolean(cachedBootstrap?.wallet?.has_topped_up),
    canRedeemPoints: Boolean(cachedBootstrap?.wallet?.can_redeem_points),
    user: (typeof window !== 'undefined' && window.Telegram?.WebApp?.initDataUnsafe?.user)
      ? memberFromUser(window.Telegram.WebApp.initDataUnsafe.user)
      : (cachedBootstrap?.user ? { id: String(cachedBootstrap.user.id), name: cachedBootstrap.user.name, initials: cachedBootstrap.user.initials || 'M' } : { id: '', name: 'Member', initials: 'M' } as Member),
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
    if (state.tab !== tab) {
      window.Telegram?.WebApp?.HapticFeedback?.selectionChanged?.()
    }
    state.dialog = null
    state.tab = tab
    state.filter = 'all'
    try {
      localStorage.setItem('tma_active_tab', tab)
    } catch {
      // ignore in restricted sandboxes
    }
    if (tab === 'history') {
      fetchHistory()
      fetchLeaderboard()
    }
  }

  function navigateTo(tab: TabId, targetId?: string) {
    setTab(tab)
    if (targetId && typeof document !== 'undefined') {
      setTimeout(() => {
        const el = document.getElementById(targetId)
        el?.scrollIntoView({ behavior: 'smooth', block: 'start' })
      }, 200)
    }
  }

  function openDialog(dialog: AppDialog) {
    window.Telegram?.WebApp?.HapticFeedback?.impactOccurred?.('light')
    state.dialog = dialog
  }

  function closeDialog() {
    window.Telegram?.WebApp?.HapticFeedback?.impactOccurred?.('light')
    state.dialog = null
  }
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

  let isBootstrapping = false
  let lastBootstrapTime = 0

  /** Hydrate live state from Backend GET /api/user/bootstrap */
  async function bootstrap(silent = false, force = false): Promise<boolean> {
    if (!api.hasAuth()) return false
    if (isBootstrapping) return false

    const now = Date.now()
    if (!force && silent && now - lastBootstrapTime < 5000) {
      return false
    }

    isBootstrapping = true
    lastBootstrapTime = now
    state.isSyncing = true
    if (!silent) state.loading = true
    try {
      const data = await api.getBootstrap(force)
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
        state.starterCost = data.wallet.starter_cost ?? 5000
        state.hasToppedUp = Boolean(data.wallet.has_topped_up)
        state.canRedeemPoints = Boolean(data.wallet.can_redeem_points)
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
        state.plans = data.plans.map(p => {
          let quotaNum = 50
          const quotaLabel = typeof p.quota === 'string' ? p.quota : `${p.quota} GB`
          if (typeof p.quota === 'number') {
            quotaNum = p.quota
          } else if (typeof p.quota === 'string') {
            const parsed = parseFloat(p.quota)
            quotaNum = isNaN(parsed) ? 0 : parsed
          }
          return {
            name: p.name,
            code: p.code,
            quota: quotaNum,
            quotaLabel: quotaLabel,
            manual: Boolean(p.manual),
            months: p.months || 1,
            description: p.description,
            icon: (p.symbol === 'zap' ? 'zap' : (p.symbol === 'crown' ? 'crown' : 'leaf')) as IconName,
            price: p.price,
          }
        })
        if (!state.plans.some(p => p.name === state.selectedPlan)) {
          state.selectedPlan = state.plans.find(p => p.code === 'basic' || p.name.toLowerCase().startsWith('basic'))?.name || state.plans[0]!.name
        }
      }
      saveCache('tma_cache_bootstrap_v1', data)
      state.isInitialLoading = false
      return true
    } catch (err: any) {
      console.warn('Bootstrap failed, retaining local state:', err)
      return false
    } finally {
      state.isSyncing = false
      if (!silent) state.loading = false
      state.isInitialLoading = false
      isBootstrapping = false
    }
  }

  /** Explicit pull-to-refresh or refresh button click */
  async function refresh(): Promise<boolean> {
    if (state.isManualRefreshing) return false
    state.isManualRefreshing = true
    window.Telegram?.WebApp?.HapticFeedback?.impactOccurred?.('light')
    const startedAt = Date.now()

    try {
      const ok = await bootstrap(true, true)
      if (state.tab === 'history') {
        await Promise.all([fetchHistory(true), fetchLeaderboard(true)])
      }
      if (ok) {
        window.Telegram?.WebApp?.HapticFeedback?.notificationOccurred?.('success')
        showToast('အချက်အလက်များ အသစ်ရယူပြီးပါပြီ')
      }
      return ok
    } finally {
      const elapsed = Date.now() - startedAt
      const remainingSpin = Math.max(0, 350 - elapsed)
      setTimeout(() => {
        state.isManualRefreshing = false
      }, remainingSpin)
    }
  }

  function syncBootstrapCache() {
    const prev = loadCache<any>('tma_cache_bootstrap_v1') || {}
    saveCache('tma_cache_bootstrap_v1', {
      ...prev,
      user: {
        id: state.user.id,
        name: state.user.name,
        initials: state.user.initials,
      },
      wallet: {
        ...(prev.wallet || {}),
        balance: state.walletBalance,
        points: state.points,
        claimed_today: state.claimedToday,
        streak_days: state.streakDays,
        cooldown_hours: state.cooldownHours,
        cooldown_remaining: state.cooldownRemaining,
        starter_cost: state.starterCost,
        has_topped_up: state.hasToppedUp,
        can_redeem_points: state.canRedeemPoints,
      },
      keys: state.keys,
      servers: state.servers,
      payment_methods: state.paymentMethods,
    })
  }

  /** Daily loyalty points reward claim with deliberate suspense reveal */
  async function claimReward() {
    if (state.isClaiming) return
    if (state.claimedToday) {
      const rem = cooldownFormatted.value
      showToast(rem ? `⏳ နောက် Claim ရရှိရန် ${rem} ကျန်ပါသေးသည်` : '⏳ Cooldown ပြည့်မှ ထပ်မံ Claim နိုင်ပါမည်', 'clock')
      return
    }

    const prefersReduced = typeof window !== 'undefined' && window.matchMedia?.('(prefers-reduced-motion: reduce)').matches
    const suspenseMs = prefersReduced ? 150 : 1050
    const pause = (ms: number) => new Promise<void>(resolve => setTimeout(resolve, ms))

    state.isClaiming = true
    window.Telegram?.WebApp?.HapticFeedback?.impactOccurred?.('medium')
    state.dialog = { kind: 'claim-reward', status: 'loading' }

    if (!api.hasAuth()) {
      await pause(suspenseMs)
      const awarded = Math.floor(Math.random() * 20) + 10
      state.claimedToday = true
      state.streakDays = (state.streakDays || 0) + 1
      state.cooldownRemaining = state.cooldownHours * 3600
      state.points += awarded
      startCountdown()
      syncBootstrapCache()
      window.Telegram?.WebApp?.HapticFeedback?.notificationOccurred?.('success')
      if (state.dialog?.kind === 'claim-reward') {
        state.dialog = {
          kind: 'claim-reward',
          status: 'success',
          awarded,
          newBalance: state.points,
          streakDays: state.streakDays,
          isStreakBonus: state.streakDays % 7 === 0,
          cooldownHours: state.cooldownHours,
          message: `🎉 +${awarded} Points ရရှိပါသည်!`,
        }
      } else {
        showToast(`Daily Claim · +${awarded} Points ရရှိပါပြီ`)
      }
      state.isClaiming = false
      return
    }

    state.isSubmitting = true
    try {
      const [res] = await Promise.all([api.claimReward(), pause(suspenseMs)])
      state.claimedToday = true
      state.points = res.new_balance
      state.streakDays = res.streak_days ?? ((state.streakDays || 0) + 1)
      state.cooldownRemaining = res.next_in_s
      state.cooldownHours = res.cooldown_hours
      startCountdown()
      syncBootstrapCache()
      window.Telegram?.WebApp?.HapticFeedback?.notificationOccurred?.('success')
      if (state.dialog?.kind === 'claim-reward') {
        state.dialog = {
          kind: 'claim-reward',
          status: 'success',
          awarded: res.awarded,
          newBalance: res.new_balance,
          streakDays: state.streakDays,
          isStreakBonus: res.is_streak_bonus,
          cooldownHours: res.cooldown_hours,
          message: res.message,
        }
      } else {
        showToast(res.message || `+${res.awarded} Points ရရှိပါသည်!`)
      }
    } catch (err: any) {
      if (state.dialog?.kind === 'claim-reward') {
        state.dialog = null
      }
      window.Telegram?.WebApp?.HapticFeedback?.notificationOccurred?.('error')
      showToast(err.message || 'Claim ပြုလုပ်၍မရသေးပါ', 'info')
    } finally {
      state.isSubmitting = false
      state.isClaiming = false
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

      state.walletBalance = res.remaining_balance ?? res.new_balance ?? state.walletBalance
      if (res.key_details) {
        state.keys.unshift(res.key_details)
        state.selectedKeyId = res.key_details.id
      }
      syncBootstrapCache()
      closeDialog()
      window.Telegram?.WebApp?.HapticFeedback?.notificationOccurred?.('success')
      showToast(res.message || 'Plan ဝယ်ယူမှု အောင်မြင်ပါသည်!')
      if (res.key_details?.id) {
        openDialog({ kind: 'connect', keyId: res.key_details.id })
      }
      fetchHistory(true)
    } catch (err: any) {
      window.Telegram?.WebApp?.HapticFeedback?.notificationOccurred?.('error')
      showToast(err.message || 'ဝယ်ယူမှု မအောင်မြင်ပါ', 'info')
    } finally {
      state.isSubmitting = false
    }
  }

  /** Redeem Starter plan with loyalty points */
  async function redeemPoints() {
    if (!api.hasAuth()) {
      showToast('Demo preview တွင် Points ဖြင့် လဲယူ၍ မရသေးပါ', 'info')
      return
    }

    state.isSubmitting = true
    try {
      const res = await api.redeemPoints()
      state.points = res.new_points
      if (res.key_details) {
        state.keys.unshift(res.key_details)
        state.selectedKeyId = res.key_details.id
      }
      syncBootstrapCache()
      window.Telegram?.WebApp?.HapticFeedback?.notificationOccurred?.('success')
      showToast(res.message || 'Starter Plan လဲယူမှု အောင်မြင်ပါသည်!')
      if (res.key_details?.id) {
        openDialog({ kind: 'connect', keyId: res.key_details.id })
      }
      fetchHistory(true)
    } catch (err: any) {
      window.Telegram?.WebApp?.HapticFeedback?.notificationOccurred?.('error')
      showToast(err.message || 'Points ဖြင့် လဲယူမှု မအောင်မြင်ပါ', 'info')
    } finally {
      state.isSubmitting = false
    }
  }

  /** Redeem promo / gift wallet balance code */
  async function redeemCode(code: string): Promise<boolean> {
    const trimmed = (code || '').trim()
    if (!trimmed) {
      showToast('Redeem Code ထည့်သွင်းပေးပါ', 'info')
      return false
    }

    if (!api.hasAuth()) {
      showToast('Demo preview တွင် Redeem Code အသုံးပြု၍ မရသေးပါ', 'info')
      return false
    }

    state.isSubmitting = true
    try {
      const res = await api.redeemCode(trimmed)
      state.walletBalance = res.new_balance
      syncBootstrapCache()
      window.Telegram?.WebApp?.HapticFeedback?.notificationOccurred?.('success')
      showToast(res.message || `+${res.awarded_amount} MMK လက်ကျန်ငွေ ရရှိပါသည်!`)
      bootstrap(true, true)
      return true
    } catch (err: any) {
      window.Telegram?.WebApp?.HapticFeedback?.notificationOccurred?.('error')
      showToast(err.message || 'Redeem Code အသုံးပြု၍ မရပါ', 'info')
      return false
    } finally {
      state.isSubmitting = false
    }
  }

  function selectReceipt(file?: File) {
    if (!file) return
    if (!file.type.startsWith('image/')) { showToast('ပုံဖိုင်ကိုသာ ရွေးပေးပါ', 'info'); return }
    if (file.size > 10 * 1024 * 1024) { showToast('10 MB ထက်ငယ်သော ပုံကို ရွေးပေးပါ', 'info'); return }
    if (state.receipt) URL.revokeObjectURL(state.receipt.url)
    window.Telegram?.WebApp?.HapticFeedback?.impactOccurred?.('light')
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
      state.history.slips = [
        {
          slip_id: res.slip_id || 'NEW',
          amount: res.amount ?? amount,
          method: (res.method || state.paymentMethod).toUpperCase(),
          status: (res.status || 'PENDING').toUpperCase(),
          submitted_at: res.submitted_at || 'ယခုလေးတင်',
        },
        ...(state.history.slips || []),
      ]
      window.Telegram?.WebApp?.HapticFeedback?.notificationOccurred?.('success')
      showToast(res.message || 'ငွေလွှဲပြေစာ ပေးပို့ပြီးပါပြီ။ မကြာမီ စစ်ဆေးအတည်ပြုပေးပါမည်။')
      fetchHistory(true)
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
  async function fetchHistory(force = false) {
    if (!api.hasAuth()) return
    if (force || (!state.history.purchases.length && !state.history.slips.length)) {
      state.isHistoryLoading = true
    }
    try {
      const data = await api.getHistory()
      state.history = data
      saveCache('tma_cache_history_v1', data)
    } catch (err) {
      console.warn('Failed to fetch history:', err)
    } finally {
      state.isHistoryLoading = false
    }
  }

  /** Fetch live points leaderboard */
  async function fetchLeaderboard(force = false) {
    if (!api.hasAuth()) return
    if (force || !state.leaderboard.rows.length) {
      state.isLeaderboardLoading = true
    }
    try {
      const data = await api.getLeaderboard()
      state.leaderboard = data
      saveCache('tma_cache_leaderboard_v1', data)
    } catch (err) {
      console.warn('Failed to fetch leaderboard:', err)
    } finally {
      state.isLeaderboardLoading = false
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

  async function tryCopyText(value: string): Promise<boolean> {
    let copied = false
    try { if (navigator.clipboard?.writeText) { await navigator.clipboard.writeText(value); copied = true } } catch { /* Fallback below. */ }
    if (!copied && typeof document !== 'undefined') {
      const focused = document.activeElement instanceof HTMLElement ? document.activeElement : null
      const field = document.createElement('textarea')
      field.value = value; field.readOnly = true; field.style.cssText = 'position:fixed;left:-9999px;top:0'
      document.body.append(field); field.select()
      try { copied = document.execCommand('copy') } catch { copied = false }
      field.remove(); focused?.focus({ preventScroll: true })
    }
    return copied
  }

  async function copyKey(value: string) {
    const copied = await tryCopyText(value)
    if (copied) {
      window.Telegram?.WebApp?.HapticFeedback?.impactOccurred?.('light')
      showToast('VPN Access Key ကို copy လုပ်ပြီးပါပြီ')
    } else {
      openDialog({ kind: 'manual-copy', value })
    }
  }

  function buildVpnSchemeUrl(appId: VpnAppId, accessUrl: string): string {
    switch (appId) {
      case 'v2box':
        return `v2box://install-config?url=${encodeURIComponent(accessUrl)}`
      case 'incy':
        return `incy://add/${accessUrl}`
      case 'outline':
      default:
        return accessUrl
    }
  }

  function openVpnApp(appId: VpnAppId = 'outline', keyStr?: string, goUrl?: string) {
    const selectedKey = keyStr
      ? state.keys.find(k => k.key === keyStr)
      : (state.selectedKeyId ? state.keys.find(k => k.id === state.selectedKeyId) : state.keys[0])
    const rawKey = keyStr || selectedKey?.key || ''
    if (!rawKey) {
      showToast('ချိတ်ဆက်ရန် Key မရှိသေးပါ', 'info')
      return
    }
    const accessUrl = rawKey.startsWith('ss://') ? rawKey : `ss://${rawKey}`
    const resolvedGoUrl = goUrl || selectedKey?.go_url || ''
    const appNames: Record<VpnAppId, string> = {
      outline: 'Outline',
      v2box: 'V2Box',
      incy: 'INCY',
    }
    const appName = appNames[appId] || 'VPN'

    // Copy ss:// key silently as reliable backup for clipboard import
    void tryCopyText(accessUrl)
    window.Telegram?.WebApp?.HapticFeedback?.impactOccurred?.('medium')

    const tgOpenLink = typeof window !== 'undefined' ? window.Telegram?.WebApp?.openLink : undefined
    if (tgOpenLink && resolvedGoUrl) {
      const targetUrl = resolvedGoUrl.startsWith('http')
        ? `${resolvedGoUrl}?app=${encodeURIComponent(appId)}`
        : `${window.location.origin}${resolvedGoUrl}?app=${encodeURIComponent(appId)}`
      try {
        tgOpenLink(targetUrl, { try_instant_view: false })
        showToast(`${appName} ဖြင့် ချိတ်ဆက်ရန် ဖွင့်နေပါသည်`)
        return
      } catch {
        // Fall through to custom scheme below
      }
    }

    const schemeUrl = buildVpnSchemeUrl(appId, accessUrl)
    showToast(`${appName} ဖြင့် ချိတ်ဆက်ရန် ဖွင့်နေပါသည် · Key Copy ကူးပြီးပါပြီ`)
    try {
      window.location.href = schemeUrl
    } catch {
      // Clipboard backup toast already shown
    }
  }

  function openOutline(keyStr?: string) {
    openVpnApp('outline', keyStr)
  }

  let eventSource: EventSource | null = null
  let pollInterval: ReturnType<typeof setInterval> | null = null
  let sseDebounceTimer: ReturnType<typeof setTimeout> | null = null
  let lastKnownVersion = 0

  async function connectLiveSync() {
    if (!api.hasAuth() || typeof window === 'undefined') return

    try {
      const ticket = await api.getSseTicket()
      if (ticket) {
        if (eventSource) eventSource.close()
        const url = api.getEventsUrl(ticket)
        eventSource = new EventSource(url)
        eventSource.onmessage = (event) => {
          try {
            const payload = JSON.parse(event.data)
            if (payload && typeof payload.version === 'number') {
              if (lastKnownVersion > 0 && payload.version > lastKnownVersion) {
                if (sseDebounceTimer) clearTimeout(sseDebounceTimer)
                sseDebounceTimer = setTimeout(() => {
                  bootstrap(true)
                }, 2000)
              }
              lastKnownVersion = payload.version
            }
          } catch {
            // Ignore keep-alive comments
          }
        }
        eventSource.onerror = () => {
          eventSource?.close()
          eventSource = null
        }
      }
    } catch (e) {
      console.warn('Live sync notice:', e)
    }

    if (!pollInterval) {
      pollInterval = setInterval(async () => {
        if (typeof document !== 'undefined' && document.visibilityState === 'visible' && !state.loading && !state.isSubmitting) {
          const v = await api.getVersion()
          if (v > 0 && lastKnownVersion > 0 && v > lastKnownVersion) {
            lastKnownVersion = v
            bootstrap(true)
          } else if (v > 0) {
            lastKnownVersion = v
          }
        }
      }, 15000)
    }
  }

  function handleVisibilityChange() {
    if (typeof document !== 'undefined' && document.visibilityState === 'visible') {
      // Only refresh on tab return if at least 30 seconds have elapsed since last sync
      if (Date.now() - lastBootstrapTime >= 30_000) {
        bootstrap(true)
      }
    }
  }

  /**
   * Keyboard guard: hide the bottom tab bar ONLY while a soft keyboard is
   * actually open (visualViewport shrink + editable focus). Merely focusing an
   * input (e.g. Custom amount / Redeem Code on desktop) keeps the layout stable.
   */
  function handleViewportResize() {
    if (typeof document === 'undefined') return
    const frame = document.querySelector('.app-frame')
    const vv = window.visualViewport
    if (!frame || !vv) return
    const active = document.activeElement
    const editing = active instanceof HTMLInputElement
      ? active.type !== 'file' && !active.readOnly
      : active instanceof HTMLTextAreaElement && !active.readOnly
    const keyboardOpen = window.innerHeight - vv.height > 150
    frame.classList.toggle('kb-open', keyboardOpen && editing)
  }

  onMounted(() => {
    if (state.cooldownRemaining > 0) {
      startCountdown()
    }
    bootstrap(true)
    if (import.meta.env.VITE_SSE_ENABLED === '1') {
      connectLiveSync()
    }
    if (typeof document !== 'undefined') {
      document.addEventListener('visibilitychange', handleVisibilityChange)
      document.addEventListener('focusout', handleViewportResize)
    }
    if (typeof window !== 'undefined' && window.visualViewport) {
      window.visualViewport.addEventListener('resize', handleViewportResize)
    }
    if (state.tab === 'history') {
      fetchHistory()
      fetchLeaderboard()
    }
  })

  onScopeDispose(() => {
    clearTimeout(toastTimer)
    if (countdownTimer) clearInterval(countdownTimer)
    if (sseDebounceTimer) clearTimeout(sseDebounceTimer)
    if (state.receipt) URL.revokeObjectURL(state.receipt.url)
    if (eventSource) eventSource.close()
    if (pollInterval) clearInterval(pollInterval)
    if (typeof document !== 'undefined') {
      document.removeEventListener('visibilitychange', handleVisibilityChange)
      document.removeEventListener('focusout', handleViewportResize)
    }
    if (typeof window !== 'undefined' && window.visualViewport) {
      window.visualViewport.removeEventListener('resize', handleViewportResize)
    }
  })

  return {
    state,
    activeKeys,
    visibleKeys,
    topUpAmount,
    amountLabel,
    showToast,
    setTab,
    navigateTo,
    openDialog,
    closeDialog,
    setUser,
    updateKeyUsage,
    setKeys,
    bootstrap,
    refresh,
    claimReward,
    redeemPoints,
    redeemCode,
    purchasePlan,
    submitTopUp,
    requestKeyReplace,
    fetchHistory,
    fetchLeaderboard,
    selectReceipt,
    showPayment,
    copyKey,
    openVpnApp,
    openOutline,
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
