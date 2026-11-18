<script setup lang="ts">
import type { VpnAppId } from '../../types'

defineProps<{
  app: VpnAppId
}>()
</script>

<template>
  <!-- Outline Client (Jigsaw / Outline Foundation) -->
  <svg v-if="app === 'outline'" class="vpn-app-logo-svg" viewBox="0 0 40 40" aria-hidden="true">
    <defs>
      <linearGradient id="vpn-ol-bg" x1="0" y1="0" x2="1" y2="1">
        <stop offset="0%" stop-color="#0b3b29" />
        <stop offset="100%" stop-color="#052217" />
      </linearGradient>
      <linearGradient id="vpn-ol-teal" x1="0" y1="0.5" x2="1" y2="0.5">
        <stop offset="0%" stop-color="#1ca789" />
        <stop offset="100%" stop-color="#61e0be" />
      </linearGradient>
    </defs>
    <rect width="40" height="40" rx="10" fill="url(#vpn-ol-bg)" />
    <rect x="0.75" y="0.75" width="38.5" height="38.5" rx="9.25" fill="none" stroke="#2aefbd" stroke-opacity="0.28" stroke-width="1.2" />
    <!-- Left filled semi-circle + Right hollow C-arc -->
    <path d="M18.6 9.6A10.4 10.4 0 0 0 18.6 30.4Z" fill="url(#vpn-ol-teal)" />
    <path d="M21.4 9.6A10.4 10.4 0 0 1 21.4 30.4V25.9A5.9 5.9 0 0 0 21.4 14.1Z" fill="#ffffff" />
  </svg>

  <!-- V2Box Client (V2 + Isometric 3D Box) -->
  <svg v-else-if="app === 'v2box'" class="vpn-app-logo-svg" viewBox="0 0 40 40" aria-hidden="true">
    <defs>
      <linearGradient id="vpn-v2-bg" x1="0" y1="0" x2="1" y2="1">
        <stop offset="0%" stop-color="#141821" />
        <stop offset="100%" stop-color="#06070b" />
      </linearGradient>
      <linearGradient id="vpn-v2-rim" x1="0" y1="0" x2="1" y2="1">
        <stop offset="0%" stop-color="#7c8598" />
        <stop offset="50%" stop-color="#353b4a" />
        <stop offset="100%" stop-color="#5d6577" />
      </linearGradient>
    </defs>
    <rect width="40" height="40" rx="10" fill="url(#vpn-v2-bg)" />
    <rect x="0.75" y="0.75" width="38.5" height="38.5" rx="9.25" fill="none" stroke="url(#vpn-v2-rim)" stroke-width="1.4" />
    <!-- Stylized V -->
    <path d="M6.8 11.2h3.1l2.1 10.4 6.2-10.4h3.3l-9.2 15.8h-2.9l-1.5-12.7H6.8Z" fill="#ffffff" />
    <!-- Tucked bold 2 -->
    <path d="M16.2 21.6c0-2.4 1.9-3.9 4.5-3.9 2.5 0 4.2 1.3 4.2 3.4 0 1.6-.9 2.6-2.9 3.9l-2 1.3h5.1v2.3h-9v-2l3.8-2.6c1.5-1 2.1-1.6 2.1-2.5 0-.9-.7-1.4-1.6-1.4-1.1 0-1.7.7-1.8 1.8h-2.4Z" fill="#ffffff" />
    <!-- Isometric 3D Cube (Top / Left / Right faces) -->
    <polygon points="30,9.8 34.8,12.5 30,15.2 25.2,12.5" fill="#ffffff" />
    <polygon points="24.8,13.4 29.5,16 29.5,21.2 24.8,18.6" fill="#d9e2f2" />
    <polygon points="35.2,13.4 35.2,18.6 30.5,21.2 30.5,16" fill="#a8b8d6" />
  </svg>

  <!-- INCY Client -->
  <svg v-else class="vpn-app-logo-svg" viewBox="0 0 40 40" aria-hidden="true">
    <defs>
      <linearGradient id="vpn-in-bg" x1="0" y1="0" x2="1" y2="1">
        <stop offset="0%" stop-color="#0a3b1a" />
        <stop offset="100%" stop-color="#031a0a" />
      </linearGradient>
      <linearGradient id="vpn-in-lime" x1="0" y1="0" x2="1" y2="0.4">
        <stop offset="0%" stop-color="#36d16a" />
        <stop offset="100%" stop-color="#b7ea54" />
      </linearGradient>
    </defs>
    <rect width="40" height="40" rx="10" fill="url(#vpn-in-bg)" />
    <rect x="0.8" y="0.8" width="38.4" height="38.4" rx="9.2" fill="none" stroke="url(#vpn-in-lime)" stroke-width="1.5" />
    <text x="20" y="24" text-anchor="middle" fill="url(#vpn-in-lime)" font-family="'Manrope', system-ui, -apple-system, sans-serif" font-size="11.2" font-weight="900" letter-spacing="0.4">INCY</text>
  </svg>
</template>
