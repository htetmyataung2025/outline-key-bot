<script setup lang="ts">
import SvgIcon from '../ui/SvgIcon.vue'
import { tabs } from '../../data/demo'
import type { TabId } from '../../types'
defineProps<{ active: TabId }>()
const emit = defineEmits<{ select: [tab: TabId] }>()
</script>
<template>
  <section class="intro" aria-label="Design concept introduction">
    <div class="eyebrow"><span class="eyebrow-dot" />Telegram Mini App · UI Concept</div>
    <h1>Member<br /><span>space.</span></h1>
    <p class="intro-copy">VPN account, keys, plans and rewards ကို Telegram ထဲမှာတင် လွယ်လွယ်ကူကူသုံးနိုင်ဖို့ mobile-first concept တစ်ခု ဖန်တီးထားပါတယ်။ Tab တွေကိုနှိပ်ပြီး screen ပြောင်းကြည့်နိုင်ပါတယ်။</p>
    <div class="pill-row"><span class="pill"><SvgIcon name="sparkles" />VIBRANT DARK</span><span class="pill"><SvgIcon name="shapes" />VUE 3 + TYPESCRIPT</span><span class="pill"><SvgIcon name="grid" />TAILWIND CSS</span></div>
    <nav class="tab-index" aria-label="Screen selector"><button v-for="(tab, index) in tabs" :key="tab.id" class="index-item" :class="{ active: active === tab.id }" :data-tab="tab.id" :aria-current="active === tab.id ? 'page' : undefined" @click="emit('select', tab.id)"><span class="index-symbol"><SvgIcon :name="tab.icon" /></span><span class="index-label"><strong>{{ tab.title }}</strong><small>{{ tab.description }}</small></span><span class="index-number">0{{ index + 1 }}</span></button></nav>
    <div class="concept-note"><SvgIcon name="info" /><span><b>UI preview:</b> Plan ဈေးနှုန်း၊ payment QR နဲ့ VPN keys တွေက demo data တွေပါ။ Live payment/VPN backend မချိတ်ထားသေးပါ။</span></div>
  </section>
</template>
