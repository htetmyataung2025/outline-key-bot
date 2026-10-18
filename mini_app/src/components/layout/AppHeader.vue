<script setup lang="ts">
import SvgIcon from '../ui/SvgIcon.vue'
import type { Member } from '../../types'

defineProps<{
  user: Member
  loading?: boolean
  syncing?: boolean
}>()
const emit = defineEmits<{ notifications: []; profile: []; refresh: [] }>()
</script>

<template>
  <header class="app-topbar">
    <div v-if="syncing" class="top-sync-progress" aria-hidden="true" />
    <div class="brand">
      <div id="header-avatar" class="brand-mark header-avatar" aria-hidden="true">{{ user.initials }}</div>
      <div class="header-account">
        <div id="telegram-name" class="brand-name" :title="user.name">{{ user.name }}</div>
        <div class="brand-caption">Telegram ID · <span id="telegram-id">{{ user.id }}</span></div>
      </div>
    </div>
    <div class="top-actions">
      <button
        class="icon-button"
        :class="{ 'is-spinning': loading }"
        aria-label="Refresh data"
        title="Refresh"
        @click="emit('refresh')"
      >
        <SvgIcon name="refresh" />
      </button>
      <button class="icon-button" aria-label="Notifications" @click="emit('notifications')">
        <SvgIcon name="bell" />
        <span class="online-dot" aria-hidden="true" />
      </button>
      <button class="icon-button profile-button" aria-label="Profile" @click="emit('profile')">
        <SvgIcon name="user" />
      </button>
    </div>
  </header>
</template>
