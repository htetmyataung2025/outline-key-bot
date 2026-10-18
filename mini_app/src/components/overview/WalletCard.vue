<script setup lang="ts">
import SvgIcon from '../ui/SvgIcon.vue'
import { useMiniApp } from '../../composables/useMiniApp'
import { formatNumber } from '../../utils/format'

const { state, setTab, claimReward, cooldownFormatted } = useMiniApp()
</script>
<template>
  <section class="wallet-card" aria-label="Wallet balance">
    <svg class="wallet-art" viewBox="0 0 310 255" fill="none" aria-hidden="true"><g stroke="currentColor" stroke-width="1"><ellipse v-for="index in 7" :key="index" cx="180" cy="95" :rx="63 + (index - 1) * 19" :ry="41 + (index - 1) * 16" transform="rotate(-32 180 95)" /></g></svg>
    <div class="wallet-top"><span class="label-small">Wallet Balance</span><span class="wallet-icon"><SvgIcon name="wallet" /></span></div>
    <div class="wallet-amount">
      <template v-if="state.isInitialLoading && state.walletBalance === 0">
        <span class="skeleton-shimmer" style="display: inline-block; width: 110px; height: 28px; border-radius: 6px; vertical-align: middle;"></span>
      </template>
      <template v-else>
        {{ formatNumber(state.walletBalance) }} <span>Ks</span>
      </template>
    </div>
    <div class="wallet-meta">
      <SvgIcon name="sparkles" />Points balance<span class="meta-separator" />
      <template v-if="state.isInitialLoading && state.points === 0">
        <span class="skeleton-shimmer" style="display: inline-block; width: 45px; height: 14px; border-radius: 4px; vertical-align: middle;"></span>
      </template>
      <template v-else>
        <b>{{ state.points }} Pts</b>
      </template>
    </div>
    <div class="wallet-actions">
      <button class="primary-btn" @click="setTab('shop')"><SvgIcon name="plus" />ငွေဖြည့်မည်</button>
      <button
        class="soft-btn"
        data-action="claim"
        :class="{ 'is-cooldown': state.claimedToday }"
        @click="claimReward"
      >
        <SvgIcon :name="state.claimedToday ? 'clock' : 'gift'" />
        {{ state.claimedToday ? (cooldownFormatted || 'Claimed') : 'Daily Claim' }}
      </button>
    </div>
  </section>
</template>
