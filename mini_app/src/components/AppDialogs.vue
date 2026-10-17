<script setup lang="ts">
import { computed } from 'vue'
import DialogShell from './ui/DialogShell.vue'
import DemoQr from './ui/DemoQr.vue'
import SvgIcon from './ui/SvgIcon.vue'
import PurchaseHistory from './rewards/PurchaseHistory.vue'
import LeaderboardCard from './rewards/LeaderboardCard.vue'
import { useMiniApp } from '../composables/useMiniApp'
import { formatNumber, percentUsed } from '../utils/format'
const { state, closeDialog, setTab, showToast, updateKeyUsage } = useMiniApp()
const activeKey = computed(() => {
  const dialog = state.dialog
  return dialog && 'keyId' in dialog ? state.keys.find(key => key.id === dialog.keyId) : undefined
})
const title = computed(() => {
  const d = state.dialog
  if (!d) return ''
  switch (d.kind) {
    case 'usage': return activeKey.value ? `${activeKey.value.plan} Plan · ${activeKey.value.location}` : 'Key details'
    case 'connect': return 'Outline နဲ့ ချိတ်ဆက်ရန်'
    case 'replace': return 'Key အသစ်လဲမလား?'
    case 'key-qr': return 'Key QR Code'
    case 'purchase': return `${d.plan} Plan`
    case 'payment': return `${d.method === 'kbz' ? 'KBZPay' : 'WavePay'} · ${formatNumber(d.amount)} Ks`
    case 'manual-copy': return 'Demo Key'
    case 'profile': return state.user.name
    case 'leaderboard': return 'Leaderboard'
    case 'history': return 'Purchase history'
  }
})
function setUsage(percent: number) { const key = activeKey.value; if (key) { closeDialog(); updateKeyUsage(key.id, key.quota * percent / 100) } }
function finish(kind: 'connect' | 'replace') { closeDialog(); showToast(kind === 'connect' ? 'Outline ချိတ်ဆက်မှုအတွက် live integration လိုအပ်ပါမည်' : 'Demo preview သာဖြစ်ပြီး key ကို မပြောင်းလဲထားပါ', 'info') }
function selectField(event: MouseEvent) { if (event.target instanceof HTMLInputElement) event.target.select() }
</script>
<template>
  <DialogShell :open="state.dialog !== null" :title="title" @close="closeDialog">
    <template v-if="state.dialog?.kind === 'usage' && activeKey">
      <span class="demo-label">ANIMATION PREVIEW · DEMO DATA</span><p>ရေမျက်နှာပြင်နဲ့ usage bar animation ကို စမ်းကြည့်ရန် ရာခိုင်နှုန်းတစ်ခု ရွေးပါ။ တကယ့် VPN data ကို ပြောင်းလဲမည်မဟုတ်ပါ။</p>
      <div class="usage-presets"><button v-for="n in [0, 29, 65, 100]" :key="n" class="usage-preset" :class="{ active: percentUsed(activeKey) === n }" :data-usage-preset="n" :aria-pressed="percentUsed(activeKey) === n" @click="setUsage(n)">{{ n }}%</button></div>
      <p class="small-hint"><SvgIcon name="info" />လက်ရှိအသုံးပြုမှု · {{ formatNumber(activeKey.used) }} / {{ activeKey.quota }} GB</p><button class="soft-btn modal-full-btn" @click="setTab('keys')"><SvgIcon name="key" />Key အားလုံးကြည့်ရန်<SvgIcon name="arrow-right" /></button>
    </template>
    <template v-else-if="state.dialog?.kind === 'connect'"><span class="demo-label">UI PREVIEW<span v-if="activeKey"> · {{ activeKey.plan }} · {{ activeKey.location }}</span></span><p>ရွေးထားသော VPN key ကို Outline app ထဲသို့ import လုပ်ပေးမည့် flow ဖြစ်ပါတယ်။ ဒီ preview မှာ တကယ့် Outline link မချိတ်ထားသေးပါ။</p><div class="modal-actions"><button class="soft-btn" @click="closeDialog">နောက်မှ</button><button class="primary-btn" @click="finish('connect')">Outline ဖွင့်ရန်<SvgIcon name="arrow-up-right" /></button></div></template>
    <template v-else-if="state.dialog?.kind === 'replace'"><span class="demo-label">UI PREVIEW</span><p>လက်ရှိ key ကို ပိတ်ပြီး key အသစ်ထုတ်ပေးမည့် flow ဖြစ်ပါတယ်။ ဒီ preview မှာ တကယ့် key ကို ပြောင်းလဲမည်မဟုတ်ပါ။</p><div class="modal-actions"><button class="soft-btn" @click="closeDialog">မလုပ်တော့ပါ</button><button class="primary-btn" @click="finish('replace')"><SvgIcon name="refresh" />ဆက်လုပ်မည်</button></div></template>
    <template v-else-if="state.dialog?.kind === 'key-qr'"><p>Backend ချိတ်ဆက်ပြီးနောက် အခြားစက်တစ်လုံးနဲ့ scan လုပ်ကာ key ထည့်သွင်းနိုင်ပါမည်။</p><DemoQr /><button class="soft-btn modal-full-btn" @click="closeDialog">ပိတ်ရန်</button></template>
    <template v-else-if="state.dialog?.kind === 'purchase'"><span class="demo-label">UI PREVIEW · Wallet {{ formatNumber(state.walletBalance) }} Ks</span><p>Plan ဈေးနှုန်း မသတ်မှတ်ရသေးသောကြောင့် preview မှာ ဝယ်ယူ၍မရသေးပါ။ Live version တွင် ဈေးနှုန်းနဲ့ wallet balance ကိုပြပြီး အတည်ပြုနိုင်ပါမည်။</p><button class="primary-btn modal-full-btn" @click="closeDialog">နားလည်ပါပြီ</button></template>
    <template v-else-if="state.dialog?.kind === 'payment'"><p>Backend ကထုတ်ပေးမည့် တကယ့် payment QR ကို ဒီနေရာမှာ ပြသပါမည်။ ယခု preview မှာ ငွေပေးချေမှု မပြုလုပ်ပါနှင့်။</p><DemoQr /><p class="text-center">Live version တွင် ငွေလွှဲပြီးနောက် Screenshot ကို upload လုပ်နိုင်ပါမည်။</p><button class="primary-btn modal-full-btn" @click="closeDialog">နားလည်ပါပြီ</button></template>
    <template v-else-if="state.dialog?.kind === 'manual-copy'"><p>Preview မှာ clipboard အသုံးပြုခွင့်မရပါက အောက်ပါ demo key ကို ရွေးပြီး copy လုပ်နိုင်ပါတယ်။</p><input class="manual-key" :value="state.dialog.value" readonly aria-label="Demo key to copy" @click="selectField" /><button class="primary-btn modal-full-btn" @click="closeDialog">ပိတ်ရန်</button></template>
    <template v-else-if="state.dialog?.kind === 'profile'"><div class="identity-card card"><div class="avatar">{{ state.user.initials }}</div><div class="identity-text"><div class="identity-name">VIP Member</div><div class="identity-id">Telegram ID · {{ state.user.id }}</div></div><SvgIcon name="diamond" /></div><p>Account settings ကို live version တွင် စီမံနိုင်ပါမည်။</p><button class="soft-btn modal-full-btn" @click="closeDialog">ပိတ်ရန်</button></template>
    <template v-else-if="state.dialog?.kind === 'leaderboard'"><p>လက်ရှိ demo ranking ဖြစ်ပါတယ်။</p><LeaderboardCard :interactive="false" /><button class="soft-btn modal-full-btn" @click="closeDialog">ပိတ်ရန်</button></template>
    <template v-else-if="state.dialog?.kind === 'history'"><p>လက်ရှိ demo မှတ်တမ်းများ ဖြစ်ပါတယ်။</p><PurchaseHistory :interactive="false" /><button class="soft-btn modal-full-btn" @click="closeDialog">ပိတ်ရန်</button></template>
  </DialogShell>
</template>
