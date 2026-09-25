<script setup lang="ts">
import { ref, onMounted } from 'vue'
import {
  fetchSettings,
  updateSettings,
  testOutlineServer,
  triggerHaptic,
  triggerHapticNotification,
} from '@/api'
import {
  NCard,
  NInput,
  NButton,
  NTag,
  NInputNumber,
  NSpin,
  NTabs,
  NTabPane,
  NPopconfirm,
  NSwitch,
  useMessage,
} from 'naive-ui'
import {
  SaveOutline,
  RefreshOutline,
  CheckmarkCircleOutline,
  CloseCircleOutline,
  AddOutline,
  TrashOutline,
  WifiOutline,
  CloudDoneOutline,
} from '@vicons/ionicons5'

const message = useMessage()

const loading = ref(false)
const saving = ref(false)
const testingServerId = ref<number | null>(null)
const serverTestResults = ref<Record<number, { success: boolean; latency_ms?: number; keys_count?: number; error?: string }>>({})

interface OutlineServerConfig {
  id: number
  name: string
  api_url: string
}

interface PlanConfig {
  name: string
  price: number
  months: number
  data: string
  bytes: number
  manual?: boolean
}

const form = ref<{
  servers: OutlineServerConfig[]
  payment_phones: string[]
  required_channel: string
  ocr_api_key: string
  plans: Record<string, PlanConfig>
}>({
  servers: [],
  payment_phones: [],
  required_channel: '',
  ocr_api_key: '',
  plans: {},
})

const originalSettings = ref<string>('')

async function loadData() {
  loading.value = true
  try {
    const data = await fetchSettings()
    form.value = {
      servers: data.servers || [],
      payment_phones: data.payment_phones || [],
      required_channel: data.required_channel || '',
      ocr_api_key: data.ocr_api_key || '',
      plans: data.plans || {},
    }
    originalSettings.value = JSON.stringify(form.value)
  } catch (err: any) {
    message.error(err?.response?.data?.error || 'Failed to load system settings')
  } finally {
    loading.value = false
  }
}

async function handleSave() {
  saving.value = true
  triggerHaptic('medium')
  try {
    const res = await updateSettings({
      servers: form.value.servers,
      payment_phones: form.value.payment_phones.filter((p) => p.trim().length > 0),
      required_channel: form.value.required_channel.trim(),
      ocr_api_key: form.value.ocr_api_key.trim(),
      plans: form.value.plans,
    })

    if (res.success && res.settings) {
      form.value = {
        servers: res.settings.servers || [],
        payment_phones: res.settings.payment_phones || [],
        required_channel: res.settings.required_channel || '',
        ocr_api_key: res.settings.ocr_api_key || '',
        plans: res.settings.plans || {},
      }
      originalSettings.value = JSON.stringify(form.value)
      triggerHapticNotification('success')
      message.success('Settings updated and synced to Supabase successfully!')
    }
  } catch (err: any) {
    triggerHapticNotification('error')
    message.error(err?.response?.data?.error || 'Failed to update settings')
  } finally {
    saving.value = false
  }
}

function handleReset() {
  if (originalSettings.value) {
    form.value = JSON.parse(originalSettings.value)
    message.info('Changes reverted to last saved state.')
  }
}

// Server management
function addServer() {
  const nextId = form.value.servers.length > 0
    ? Math.max(...form.value.servers.map((s) => s.id)) + 1
    : 1
  form.value.servers.push({
    id: nextId,
    name: `Server ${nextId}`,
    api_url: '',
  })
}

function removeServer(index: number) {
  form.value.servers.splice(index, 1)
}

async function runTestServer(server: OutlineServerConfig) {
  if (!server.api_url) {
    message.warning('Please enter an Outline API URL first')
    return
  }
  testingServerId.value = server.id
  serverTestResults.value[server.id] = undefined as any
  try {
    const res = await testOutlineServer(server.api_url)
    serverTestResults.value[server.id] = res
    if (res.success) {
      message.success(`${server.name}: Online (${res.latency_ms}ms, ${res.keys_count} keys)`)
    } else {
      message.error(`${server.name}: ${res.error || 'Connection failed'}`)
    }
  } catch (err: any) {
    serverTestResults.value[server.id] = {
      success: false,
      error: err?.message || 'Request failed',
    }
    message.error(`Test failed: ${err.message}`)
  } finally {
    testingServerId.value = null
  }
}

// Payment phone management
function addPhone() {
  form.value.payment_phones.push('')
}

function removePhone(index: number) {
  form.value.payment_phones.splice(index, 1)
}

// Plan management
function getPlanGb(plan: PlanConfig): number {
  if (!plan.bytes || plan.bytes <= 0) return 0
  return Math.round(plan.bytes / (1000 * 1000 * 1000))
}

function setPlanGb(plan: PlanConfig, gb: number | null) {
  const val = gb || 0
  plan.bytes = val * 1000 * 1000 * 1000
  plan.data = val > 0 ? `${val} GB` : 'Unlimited Data'
}

function addPlan() {
  const key = `custom_${Date.now().toString().slice(-4)}`
  form.value.plans[key] = {
    name: 'Custom VIP Plan',
    months: 1,
    price: 5000,
    data: '50 GB',
    bytes: 50 * 1000 * 1000 * 1000,
    manual: false,
  }
}

function removePlan(key: string) {
  delete form.value.plans[key]
}

onMounted(() => {
  loadData()
})
</script>

<template>
  <div class="settings-view">
    <!-- Header -->
    <div class="page-header">
      <div>
        <div class="title-row">
          <h2 class="page-title">System Settings</h2>
          <NTag size="small" type="success" :bordered="false" class="cloud-badge">
            <template #icon>
              <CloudDoneOutline style="width: 14px; height: 14px" />
            </template>
            Supabase Synced
          </NTag>
        </div>
        <p class="page-subtitle">
          Dynamic config management. Changes apply in real-time to the bot without redeploying.
        </p>
      </div>
      <div class="header-actions">
        <NButton quaternary size="small" @click="handleReset" :disabled="saving">
          <template #icon>
            <RefreshOutline />
          </template>
          Revert
        </NButton>
        <NButton type="primary" size="small" :loading="saving" @click="handleSave">
          <template #icon>
            <SaveOutline />
          </template>
          Save Changes
        </NButton>
      </div>
    </div>

    <NSpin :show="loading">
      <div class="tabs-wrapper">
        <NTabs type="line" animated default-value="servers">
          <!-- TAB 1: OUTLINE SERVERS -->
          <NTabPane name="servers" tab="🌐 Outline Servers">
            <div class="tab-content">
              <div class="section-desc-row">
                <span>Manage Outline VPN Server API URLs. Test connectivity before saving.</span>
                <NButton size="tiny" type="primary" dashed @click="addServer">
                  <template #icon>
                    <AddOutline />
                  </template>
                  Add Server
                </NButton>
              </div>

              <div class="servers-grid">
                <NCard
                  v-for="(server, idx) in form.servers"
                  :key="server.id"
                  size="small"
                  class="server-card"
                >
                  <div class="server-card-header">
                    <div class="server-num-badge">#{{ server.id }}</div>
                    <NInput
                      v-model:value="server.name"
                      placeholder="Server Label (e.g. SG-1 High Speed)"
                      size="small"
                      class="server-name-input"
                    />
                    <NPopconfirm @positive-click="removeServer(idx)">
                      <template #trigger>
                        <NButton quaternary circle size="tiny" type="error">
                          <template #icon>
                            <TrashOutline />
                          </template>
                        </NButton>
                      </template>
                      Delete {{ server.name }}?
                    </NPopconfirm>
                  </div>

                  <div class="server-field">
                    <label class="field-label">Outline API URL</label>
                    <NInput
                      v-model:value="server.api_url"
                      placeholder="https://123.45.67.89:PORT/SECRET_PATH"
                      size="small"
                      type="password"
                      show-password-on="click"
                    />
                  </div>

                  <div class="server-footer">
                    <NButton
                      size="tiny"
                      secondary
                      :loading="testingServerId === server.id"
                      @click="runTestServer(server)"
                    >
                      <template #icon>
                        <WifiOutline />
                      </template>
                      Test Connection
                    </NButton>

                    <div v-if="serverTestResults[server.id]" class="test-result">
                      <span v-if="serverTestResults[server.id].success" class="res-success">
                        <CheckmarkCircleOutline class="status-icon" />
                        {{ serverTestResults[server.id].latency_ms }}ms · {{ serverTestResults[server.id].keys_count }} keys
                      </span>
                      <span v-else class="res-error">
                        <CloseCircleOutline class="status-icon" />
                        {{ serverTestResults[server.id].error }}
                      </span>
                    </div>
                  </div>
                </NCard>
              </div>
            </div>
          </NTabPane>

          <!-- TAB 2: PAYMENT PHONES -->
          <NTabPane name="payments" tab="💳 Payment Accounts">
            <div class="tab-content">
              <div class="section-desc-row">
                <span>Phone numbers displayed to users for KPay and WavePay manual slip payments.</span>
                <NButton size="tiny" type="primary" dashed @click="addPhone">
                  <template #icon>
                    <AddOutline />
                  </template>
                  Add Phone
                </NButton>
              </div>

              <div class="phones-list">
                <div
                  v-for="(_, idx) in form.payment_phones"
                  :key="idx"
                  class="phone-row"
                >
                  <div class="phone-index">{{ idx + 1 }}.</div>
                  <NInput
                    v-model:value="form.payment_phones[idx]"
                    placeholder="09..."
                    size="small"
                    class="phone-input"
                  />
                  <NButton
                    quaternary
                    circle
                    size="tiny"
                    type="error"
                    @click="removePhone(idx)"
                  >
                    <template #icon>
                      <TrashOutline />
                    </template>
                  </NButton>
                </div>

                <div v-if="form.payment_phones.length === 0" class="empty-hint">
                  No payment numbers configured. Add at least one phone number.
                </div>
              </div>
            </div>
          </NTabPane>

          <!-- TAB 3: CHANNEL & OCR -->
          <NTabPane name="channel_ocr" tab="📢 Channel & OCR">
            <div class="tab-content">
              <NCard size="small" class="settings-card">
                <div class="setting-item">
                  <label class="item-title">
                    Required Telegram Channel
                    <span class="item-hint">Users must join this channel before buying or claiming VPN keys.</span>
                  </label>
                  <NInput
                    v-model:value="form.required_channel"
                    placeholder="@channel_username"
                    size="small"
                  />
                </div>

                <div class="setting-item mt-4">
                  <label class="item-title">
                    OCR.space API Key
                    <span class="item-hint">Used for automatic payment slip screenshot text extraction.</span>
                  </label>
                  <NInput
                    v-model:value="form.ocr_api_key"
                    placeholder="K88888888888888"
                    size="small"
                    type="password"
                    show-password-on="click"
                  />
                </div>
              </NCard>
            </div>
          </NTabPane>

          <!-- TAB 4: VPN PLANS -->
          <NTabPane name="plans" tab="🛍️ VPN Plans & Pricing">
            <div class="tab-content">
              <div class="section-desc-row">
                <span>Configure pricing, duration, and data quotas for each VPN plan.</span>
                <NButton size="tiny" type="primary" dashed @click="addPlan">
                  <template #icon>
                    <AddOutline />
                  </template>
                  Add Plan
                </NButton>
              </div>

              <div class="plans-grid">
                <NCard
                  v-for="(plan, key) in form.plans"
                  :key="key"
                  size="small"
                  class="plan-card"
                >
                  <div class="plan-card-header">
                    <NTag size="small" type="info" :bordered="false">{{ key }}</NTag>
                    <NPopconfirm @positive-click="removePlan(key as string)">
                      <template #trigger>
                        <NButton quaternary circle size="tiny" type="error">
                          <template #icon>
                            <TrashOutline />
                          </template>
                        </NButton>
                      </template>
                      Delete plan {{ key }}?
                    </NPopconfirm>
                  </div>

                  <div class="plan-fields">
                    <div class="field-col">
                      <label class="field-label">Plan Title</label>
                      <NInput v-model:value="plan.name" size="small" placeholder="1 Month (30 Days)" />
                    </div>

                    <div class="field-row-two">
                      <div class="field-col">
                        <label class="field-label">Price (MMK)</label>
                        <NInputNumber v-model:value="plan.price" size="small" :min="0" :step="500" />
                      </div>
                      <div class="field-col">
                        <label class="field-label">Duration (Months)</label>
                        <NInputNumber v-model:value="plan.months" size="small" :min="1" />
                      </div>
                    </div>

                    <div class="field-row-two">
                      <div class="field-col">
                        <label class="field-label">Data Quota (GB, 0=Unlimited)</label>
                        <NInputNumber
                          :value="getPlanGb(plan)"
                          @update:value="(v) => setPlanGb(plan, v)"
                          size="small"
                          :min="0"
                        />
                      </div>
                      <div class="field-col">
                        <label class="field-label">Data Display Text</label>
                        <NInput v-model:value="plan.data" size="small" placeholder="50 GB / Unlimited" />
                      </div>
                    </div>

                    <div class="field-switch-row">
                      <span class="field-label">Fulfillment Mode</span>
                      <div class="switch-toggle-wrap">
                        <span class="switch-status-label" :class="{ 'is-manual': plan.manual }">
                          {{ plan.manual ? 'Manual Review' : 'Auto Issue' }}
                        </span>
                        <NSwitch v-model:value="plan.manual" size="small" />
                      </div>
                    </div>
                  </div>
                </NCard>
              </div>
            </div>
          </NTabPane>
        </NTabs>
      </div>
    </NSpin>
  </div>
</template>

<style scoped>
.settings-view {
  max-width: 1200px;
  margin: 0 auto;
  padding: 24px;
  display: flex;
  flex-direction: column;
  gap: 20px;
}

@media (max-width: 767px) {
  .settings-view {
    padding: 14px 12px;
  }
}

.page-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  flex-wrap: wrap;
  gap: 12px;
}

.title-row {
  display: flex;
  align-items: center;
  gap: 10px;
}

.page-title {
  margin: 0;
  font-size: 22px;
  font-weight: 700;
  color: #f8fafc;
}

.cloud-badge {
  font-size: 11px;
  font-weight: 600;
}

.page-subtitle {
  margin: 4px 0 0 0;
  font-size: 13px;
  color: #94a3b8;
}

.header-actions {
  display: flex;
  align-items: center;
  gap: 8px;
}

.tabs-wrapper {
  background: transparent;
  padding: 0;
}

.tab-content {
  padding-top: 16px;
  display: flex;
  flex-direction: column;
  gap: 16px;
}

.section-desc-row {
  display: flex;
  align-items: center;
  justify-content: space-between;
  font-size: 12px;
  color: #94a3b8;
  gap: 8px;
  flex-wrap: wrap;
}

/* Servers */
.servers-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(320px, 1fr));
  gap: 12px;
}

.server-card {
  background: #1e293b;
  border: 1px solid #334155;
  border-radius: 10px;
}

.server-card-header {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 12px;
}

.server-num-badge {
  font-size: 11px;
  font-weight: 700;
  background: rgba(16, 185, 129, 0.15);
  color: #10b981;
  padding: 2px 6px;
  border-radius: 4px;
}

.server-name-input {
  flex: 1;
}

.server-field {
  display: flex;
  flex-direction: column;
  gap: 4px;
  margin-bottom: 12px;
}

.field-label {
  font-size: 11px;
  color: #94a3b8;
  font-weight: 500;
}

.server-footer {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
  flex-wrap: wrap;
  padding-top: 8px;
  border-top: 1px solid rgba(255, 255, 255, 0.04);
}

.test-result {
  font-size: 11px;
}

.res-success {
  display: flex;
  align-items: center;
  gap: 4px;
  color: #10b981;
}

.res-error {
  display: flex;
  align-items: center;
  gap: 4px;
  color: #ef4444;
  max-width: 180px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.status-icon {
  width: 14px;
  height: 14px;
}

/* Payments */
.phones-list {
  display: flex;
  flex-direction: column;
  gap: 8px;
  max-width: 400px;
}

.phone-row {
  display: flex;
  align-items: center;
  gap: 8px;
}

.phone-index {
  font-size: 12px;
  color: #94a3b8;
  width: 20px;
}

.phone-input {
  flex: 1;
}

.empty-hint {
  font-size: 12px;
  color: #64748b;
  font-style: italic;
}

/* Settings Card */
.settings-card {
  background: #1e293b;
  border: 1px solid #334155;
  border-radius: 10px;
  max-width: 640px;
}

.setting-item {
  display: flex;
  flex-direction: column;
  gap: 6px;
}

.item-title {
  font-size: 13px;
  font-weight: 600;
  color: #f1f5f9;
  display: flex;
  flex-direction: column;
  gap: 2px;
}

.item-hint {
  font-size: 11px;
  font-weight: 400;
  color: #94a3b8;
}

.mt-4 {
  margin-top: 16px;
}

/* Plans */
.plans-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(280px, 1fr));
  gap: 12px;
}

.plan-card {
  background: #1e293b;
  border: 1px solid #334155;
  border-radius: 10px;
}

.plan-card-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 12px;
}

.plan-fields {
  display: flex;
  flex-direction: column;
  gap: 10px;
}

.field-col {
  display: flex;
  flex-direction: column;
  gap: 4px;
}

.field-row-two {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 8px;
}

.field-switch-row {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding-top: 8px;
  border-top: 1px solid rgba(255, 255, 255, 0.04);
}

.switch-toggle-wrap {
  display: flex;
  align-items: center;
  gap: 8px;
}

.switch-status-label {
  font-size: 11px;
  font-weight: 600;
  color: #64748b;
  transition: color 0.15s ease;
}

.switch-status-label.is-manual {
  color: #10b981;
}

@media (max-width: 768px) {
  .servers-grid,
  .plans-grid {
    grid-template-columns: 1fr;
  }
}
</style>
