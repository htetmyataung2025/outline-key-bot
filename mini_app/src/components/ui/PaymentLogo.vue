<script setup lang="ts">
import type { PaymentMethod } from '../../types'

defineProps<{
  method: PaymentMethod
}>()
</script>

<template>
  <!-- KBZPay -->
  <svg v-if="method === 'kbz'" class="method-logo-svg" viewBox="0 0 40 40" aria-hidden="true">
    <defs>
      <linearGradient id="kbz-grad" x1="0" y1="0" x2="1" y2="1">
        <stop offset="0%" stop-color="#0b63d6" />
        <stop offset="100%" stop-color="#003f9e" />
      </linearGradient>
    </defs>
    <rect width="40" height="40" rx="11" fill="url(#kbz-grad)" />
    <path d="M11 10.5h4.2v8.2l7-8.2h5.1l-7.4 8.5 7.8 10.5h-5.2l-5.7-7.9-1.6 1.8v6.1H11V10.5z" fill="#fff" />
    <circle cx="30.5" cy="11.5" r="2.6" fill="#4cc3ff" />
  </svg>

  <!-- WavePay -->
  <svg v-else-if="method === 'wave'" class="method-logo-svg" viewBox="0 0 40 40" aria-hidden="true">
    <defs>
      <linearGradient id="wave-grad" x1="0" y1="0" x2="1" y2="1">
        <stop offset="0%" stop-color="#ffd52e" />
        <stop offset="100%" stop-color="#f7b500" />
      </linearGradient>
    </defs>
    <rect width="40" height="40" rx="11" fill="url(#wave-grad)" />
    <path d="M8.5 13.5l4.4 13.5h3.5l3.6-9 3.6 9h3.5l4.4-13.5h-4l-2.4 8.4-3.4-8.4h-3.4l-3.4 8.4-2.4-8.4h-4z" fill="#172033" />
    <path d="M9.5 29.8c3.6-1.4 7-1.4 10.5 0s6.9 1.4 10.5 0" fill="none" stroke="#0088cc" stroke-width="2" stroke-linecap="round" />
  </svg>

  <!-- AYA Pay -->
  <svg v-else-if="method === 'aya'" class="method-logo-svg" viewBox="0 0 40 40" aria-hidden="true">
    <defs>
      <linearGradient id="aya-grad" x1="0" y1="0" x2="1" y2="1">
        <stop offset="0%" stop-color="#e3222a" />
        <stop offset="100%" stop-color="#a80e16" />
      </linearGradient>
    </defs>
    <rect width="40" height="40" rx="11" fill="url(#aya-grad)" />
    <path d="M20 9.5L10.5 29h4.6l1.8-4h6.2l1.8 4h4.6L20 9.5zm-1.6 11.8l1.6-3.9 1.6 3.9h-3.2z" fill="#fff" />
  </svg>

  <!-- uab pay -->
  <svg v-else-if="method === 'uab'" class="method-logo-svg" viewBox="0 0 40 40" aria-hidden="true">
    <defs>
      <linearGradient id="uab-grad" x1="0" y1="0" x2="1" y2="1">
        <stop offset="0%" stop-color="#00b050" />
        <stop offset="100%" stop-color="#007e3a" />
      </linearGradient>
    </defs>
    <rect width="40" height="40" rx="11" fill="url(#uab-grad)" />
    <text x="20" y="24.5" text-anchor="middle" fill="#ffffff" font-family="system-ui, -apple-system, sans-serif" font-size="13.5" font-weight="900" letter-spacing="-0.4">uab</text>
  </svg>

  <!-- CB Pay -->
  <svg v-else class="method-logo-svg" viewBox="0 0 40 40" aria-hidden="true">
    <defs>
      <linearGradient id="cb-grad" x1="0" y1="0" x2="1" y2="1">
        <stop offset="0%" stop-color="#00a0e3" />
        <stop offset="100%" stop-color="#005ca9" />
      </linearGradient>
    </defs>
    <rect width="40" height="40" rx="11" fill="url(#cb-grad)" />
    <text x="20" y="24.5" text-anchor="middle" fill="#ffffff" font-family="system-ui, -apple-system, sans-serif" font-size="14" font-weight="900" letter-spacing="-0.5">CB</text>
  </svg>
</template>
