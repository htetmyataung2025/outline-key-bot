<script setup lang="ts">
import { ref, onMounted } from 'vue'
import {
  fetchKeys,
  createKey,
  extendKey,
  triggerHaptic,
  triggerHapticNotification,
} from '@/api'
import {
  NCard,
  NInput,
  NSelect,
  NButton,
  NTag,
  NModal,
  NForm,
  NFormItem,
  NInputNumber,
  NSpin,
  useMessage,
} from 'naive-ui'
import {
  AddOutline,
  SearchOutline,
  CopyOutline,
  CalendarOutline,
} from '@vicons/ionicons5'

const message = useMessage()

const loading = ref(false)
const keysList = ref<any[]>([])
const totalKeys = ref(0)

const searchQuery = ref('')
const selectedServer = ref<string>('')

// Create modal
const showCreateModal = ref(false)
const createLoading = ref(false)
const createForm = ref({
  server_id: '1',
  name: '',
  data_limit_gb: 50,
  valid_days: 30,
  assign_to_user_id: '',
})

const serverOptions = [
  { label: 'All Servers', value: '' },
  { label: 'Server 1 (SG-1)', value: '1' },
  { label: 'Server 2 (SG-2)', value: '2' },
  { label: 'Server 3 (VIP)', value: '3' },
]


async function loadKeys() {
  loading.value = true
  try {
    const res = await fetchKeys({
      server_id: selectedServer.value || undefined,
      search: searchQuery.value || undefined,
    })
    keysList.value = res.items || []
    totalKeys.value = res.total || 0
  } catch (err: any) {
    message.error(err?.response?.data?.error || 'Failed to load access keys')
  } finally {
    loading.value = false
  }
}

async function handleExtend(row: any) {
  triggerHaptic('medium')
  try {
    const res = await extendKey(row.key_id, 30)
    if (res.success) {
      triggerHapticNotification('success')
      message.success(`Extended key ${row.key_id} to ${res.new_expire_date}`)
      await loadKeys()
    }
  } catch (err: any) {
    triggerHapticNotification('error')
    message.error(err?.response?.data?.error || 'Failed to extend key')
  }
}

function copyKeyUrl(url: string) {
  triggerHaptic('light')
  navigator.clipboard.writeText(url)
  message.info('Key access URL copied to clipboard!')
}

async function handleCreateKey() {
  if (!createForm.value.name) {
    message.warning('Key name is required')
    return
  }
  createLoading.value = true
  try {
    const res = await createKey({
      server_id: createForm.value.server_id,
      name: createForm.value.name,
      data_limit_gb: createForm.value.data_limit_gb,
      valid_days: createForm.value.valid_days,
      assign_to_user_id: createForm.value.assign_to_user_id || undefined,
    })
    if (res.success) {
      triggerHapticNotification('success')
      message.success('New Outline key successfully provisioned!')
      showCreateModal.value = false
      createForm.value.name = ''
      await loadKeys()
    }
  } catch (err: any) {
    triggerHapticNotification('error')
    message.error(err?.response?.data?.error || 'Failed to create key')
  } finally {
    createLoading.value = false
  }
}

onMounted(() => {
  loadKeys()
})
</script>

<template>
  <div class="keys-view">
    <div class="view-header">
      <div>
        <h1 class="page-title">Outline Access Keys</h1>
        <p class="page-subtitle">Manage, extend, and provision VPN credentials across servers</p>
      </div>
      <NButton type="primary" size="medium" @click="showCreateModal = true">
        <template #icon>
          <AddOutline />
        </template>
        Provision Key
      </NButton>
    </div>

    <!-- Filters Bar -->
    <NCard class="filter-card">
      <div class="filters-row">
        <NInput
          v-model:value="searchQuery"
          placeholder="Search by key name, chat ID, key ID..."
          clearable
          class="search-input"
          @update:value="loadKeys"
        >
          <template #prefix>
            <SearchOutline />
          </template>
        </NInput>

        <NSelect
          v-model:value="selectedServer"
          :options="serverOptions"
          placeholder="Filter by Server"
          class="server-select"
          @update:value="loadKeys"
        />
      </div>
    </NCard>

    <!-- Keys List / Table -->
    <NSpin :show="loading">
      <div class="keys-list-wrap">
        <div v-for="k in keysList" :key="k.key_id" class="key-card">
          <div class="key-main">
            <div class="key-identity">
              <span class="key-name">{{ k.name }}</span>
              <div class="key-tags">
                <NTag size="small" type="info" round>Server {{ k.server }}</NTag>
                <NTag size="small" type="default" round class="font-mono">ID: {{ k.key_id }}</NTag>
                <NTag v-if="k.chat_id" size="small" type="success" round class="font-mono">
                  UID: {{ k.chat_id }}
                </NTag>
              </div>
            </div>

            <div class="key-expiry">
              <CalendarOutline class="cal-icon" />
              <span class="expiry-label">Expires:</span>
              <span class="expiry-val font-mono">{{ k.expire_date || 'N/A' }}</span>
            </div>
          </div>

          <div class="key-actions">
            <NButton
              v-if="k.access_url"
              size="small"
              secondary
              @click="copyKeyUrl(k.access_url)"
            >
              <template #icon>
                <CopyOutline />
              </template>
              Copy Link
            </NButton>

            <NButton
              size="small"
              type="primary"
              secondary
              @click="handleExtend(k)"
            >
              +30 Days Extend
            </NButton>
          </div>
        </div>
      </div>
    </NSpin>

    <!-- Create Key Modal -->
    <NModal
      v-model:show="showCreateModal"
      preset="card"
      title="Provision Outline Key"
      style="max-width: 480px;"
    >
      <NForm :model="createForm" label-placement="left" label-width="120">
        <NFormItem label="Target Server">
          <NSelect
            v-model:value="createForm.server_id"
            :options="[
              { label: 'Server 1 (SG-1)', value: '1' },
              { label: 'Server 2 (SG-2)', value: '2' },
              { label: 'Server 3 (VIP)', value: '3' },
            ]"
          />
        </NFormItem>

        <NFormItem label="Key Label / Name">
          <NInput v-model:value="createForm.name" placeholder="e.g. VIP Customer John" />
        </NFormItem>

        <NFormItem label="Data Limit (GB)">
          <NInputNumber v-model:value="createForm.data_limit_gb" :min="0" :max="1000" />
        </NFormItem>

        <NFormItem label="Validity (Days)">
          <NInputNumber v-model:value="createForm.valid_days" :min="1" :max="365" />
        </NFormItem>

        <NFormItem label="Assign Chat ID">
          <NInput v-model:value="createForm.assign_to_user_id" placeholder="Optional Telegram Chat ID" />
        </NFormItem>

        <div style="display: flex; justify-content: flex-end; gap: 10px; margin-top: 16px;">
          <NButton @click="showCreateModal = false">Cancel</NButton>
          <NButton type="primary" :loading="createLoading" @click="handleCreateKey">
            Generate Key
          </NButton>
        </div>
      </NForm>
    </NModal>
  </div>
</template>

<style scoped>
.keys-view {
  padding: 24px;
}

.view-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 20px;
  flex-wrap: wrap;
  gap: 16px;
}

.page-title {
  margin: 0;
  font-size: 22px;
  font-weight: 700;
  color: #f8fafc;
}

.page-subtitle {
  margin: 4px 0 0 0;
  font-size: 13px;
  color: #94a3b8;
}

.filter-card {
  margin-bottom: 20px;
  background: #0f172a;
}

.filters-row {
  display: flex;
  gap: 16px;
  flex-wrap: wrap;
}

.search-input {
  flex: 2;
  min-width: 220px;
}

.server-select {
  flex: 1;
  min-width: 180px;
}

.keys-list-wrap {
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.key-card {
  background: #1e293b;
  border: 1px solid #334155;
  border-radius: 10px;
  padding: 16px;
  display: flex;
  justify-content: space-between;
  align-items: center;
  flex-wrap: wrap;
  gap: 16px;
}

.key-main {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.key-identity {
  display: flex;
  align-items: center;
  gap: 12px;
  flex-wrap: wrap;
}

.key-name {
  font-size: 15px;
  font-weight: 600;
  color: #f8fafc;
}

.key-tags {
  display: flex;
  gap: 6px;
}

.key-expiry {
  display: flex;
  align-items: center;
  gap: 6px;
  font-size: 12px;
}

.cal-icon {
  width: 14px;
  height: 14px;
  color: #94a3b8;
}

.expiry-label {
  color: #94a3b8;
}

.expiry-val {
  color: #10b981;
  font-weight: 600;
}

.key-actions {
  display: flex;
  gap: 8px;
  align-items: center;
}

.font-mono {
  font-family: 'JetBrains Mono', monospace;
}
</style>
