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
  GiftOutline,
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

interface PointsConfig {
  enabled: boolean
  claim_cooldown_h: number
  balance_cap: number
  topup_rate: number
  topup_cap: number
  starter_cost: number
  streak_target_days: number
  streak_reward: number[]     // [low, high]
  on_admin_topup: boolean
  reward_table: number[][]    // [[low, high, weight], ...]
}

const DEFAULT_POINTS: PointsConfig = {
  enabled: true,
  claim_cooldown_h: 4,
  balance_cap: 20000,
  topup_rate: 100,
  topup_cap: 1000,
  starter_cost: 5000,
  streak_target_days: 7,
  streak_reward: [150, 200],
  on_admin_topup: false,
  reward_table: [
    [10, 19, 35], [20, 30, 35], [31, 50, 18],
    [51, 99, 8], [100, 150, 3], [151, 200, 1],
  ],
}

// Reward-table presets so the owner rarely hand-edits weights.
const REWARD_PRESETS: Record<string, number[][]> = {
  Conservative: [[10, 15, 45], [16, 25, 35], [26, 40, 15], [41, 60, 4], [61, 100, 1]],
  Balanced: [[10, 19, 35], [20, 30, 35], [31, 50, 18], [51, 99, 8], [100, 150, 3], [151, 200, 1]],
  Generous: [[20, 40, 30], [41, 70, 30], [71, 120, 25], [121, 180, 10], [181, 250, 5]],
}

const form = ref<{
  servers: OutlineServerConfig[]
  payment_phones: string[]
  required_channel: string
  ocr_api_key: string
  plans: Record<string, PlanConfig>
  points: PointsConfig
}>({
  servers: [],
  payment_phones: [],
  required_channel: '',
  ocr_api_key: '',
  plans: {},
  points: { ...DEFAULT_POINTS },
})

const originalSettings = ref<string>('')

function normalizePoints(raw: any): PointsConfig {
  const p = raw && typeof raw === 'object' ? raw : {}
  const band = Array.isArray(p.streak_reward) && p.streak_reward.length === 2
    ? [Number(p.streak_reward[0]), Number(p.streak_reward[1])]
    : [...DEFAULT_POINTS.streak_reward]
  const table = Array.isArray(p.reward_table) && p.reward_table.length
    ? p.reward_table.map((r: any) => [Number(r[0]), Number(r[1]), Number(r[2])])
    : DEFAULT_POINTS.reward_table.map((r) => [...r])
  return {
    enabled: p.enabled !== undefined ? !!p.enabled : DEFAULT_POINTS.enabled,
    claim_cooldown_h: Number(p.claim_cooldown_h ?? DEFAULT_POINTS.claim_cooldown_h),
    balance_cap: Number(p.balance_cap ?? DEFAULT_POINTS.balance_cap),
    topup_rate: Number(p.topup_rate ?? DEFAULT_POINTS.topup_rate),
    topup_cap: Number(p.topup_cap ?? DEFAULT_POINTS.topup_cap),
    starter_cost: Number(p.starter_cost ?? DEFAULT_POINTS.starter_cost),
    streak_target_days: Number(p.streak_target_days ?? DEFAULT_POINTS.streak_target_days),
    streak_reward: band,
    on_admin_topup: !!p.on_admin_topup,
    reward_table: table,
  }
}

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
      points: normalizePoints(data.points),
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
      points: form.value.points,
    })

    if (res.success && res.settings) {
      form.value = {
        servers: res.settings.servers || [],
        payment_phones: res.settings.payment_phones || [],
        required_channel: res.settings.required_channel || '',
        ocr_api_key: res.settings.ocr_api_key || '',
        plans: res.settings.plans || {},
        points: normalizePoints(res.settings.points),
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

// Loyalty Points — reward table management
function addRewardRow() {
  form.value.points.reward_table.push([10, 20, 10])
}

function removeRewardRow(index: number) {
  form.value.points.reward_table.splice(index, 1)
}

function applyPreset(name: string) {
  const preset = REWARD_PRESETS[name]
  if (preset) {
    form.value.points.reward_table = preset.map((r) => [...r])
    message.info(`${name} reward table applied. Save to confirm.`)
  }
}

function isPresetActive(name: string): boolean {
  const preset = REWARD_PRESETS[name]
  return !!preset && JSON.stringify(preset) === JSON.stringify(form.value.points.reward_table)
}

function totalWeight(): number {
  return form.value.points.reward_table.reduce((sum, r) => sum + (Number(r[2]) || 0), 0)
}

function rowChancePct(weight: number): string {
  const total = totalWeight()
  if (total <= 0) return '0%'
  return `${((Number(weight) / total) * 100).toFixed(1)}%`
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

          <!-- TAB 5: LOYALTY POINTS -->
          <NTabPane name="points" tab="🎁 Loyalty Points">
            <div class="tab-content">
              <div class="section-desc-row">
                <span>Tune the Daily Reward / Points economy. Changes apply live — no redeploy.</span>
              </div>

              <!-- Master switch + admin top-up -->
              <NCard size="small" class="settings-card points-card points-master-card">
                <div class="points-master-row">
                  <div class="master-text">
                    <div class="master-title">
                      <span class="master-icon-tile">
                        <GiftOutline class="master-icon" />
                      </span>
                      Points System
                    </div>
                    <span class="item-hint">
                      Turn the whole Daily Reward system on or off. When off, the reward button
                      is hidden and top-ups grant no points — stored balances are preserved.
                    </span>
                  </div>
                  <div class="switch-toggle-wrap">
                    <span class="switch-status-label" :class="{ 'is-manual': form.points.enabled }">
                      {{ form.points.enabled ? 'Enabled' : 'Disabled' }}
                    </span>
                    <NSwitch v-model:value="form.points.enabled" />
                  </div>
                </div>

                <div class="field-switch-row">
                  <span class="field-label">
                    Admin manual top-ups grant points
                    <span class="item-hint">Default OFF — admin comps are not customer payments.</span>
                  </span>
                  <div class="switch-toggle-wrap">
                    <span class="switch-status-label" :class="{ 'is-manual': form.points.on_admin_topup }">
                      {{ form.points.on_admin_topup ? 'Yes' : 'No' }}
                    </span>
                    <NSwitch v-model:value="form.points.on_admin_topup" size="small" />
                  </div>
                </div>
              </NCard>

              <div class="points-layout">
                <!-- Economy numbers -->
                <NCard size="small" class="settings-card points-card">
                  <div class="card-section-title">Economy Rules</div>

                  <div class="points-group">
                    <div class="group-label">Claims &amp; Balance</div>
                    <div class="points-grid">
                      <div class="field-col">
                        <label class="field-label">Claim cooldown (hours)</label>
                        <NInputNumber v-model:value="form.points.claim_cooldown_h" size="small" :min="1" :max="24" />
                      </div>
                      <div class="field-col">
                        <label class="field-label">Balance cap (points)</label>
                        <NInputNumber v-model:value="form.points.balance_cap" size="small" :min="1" :step="1000" />
                      </div>
                    </div>
                  </div>

                  <div class="points-group">
                    <div class="group-label">Top-up Earning</div>
                    <div class="points-grid">
                      <div class="field-col">
                        <label class="field-label">Top-up rate (Ks per point)</label>
                        <NInputNumber v-model:value="form.points.topup_rate" size="small" :min="1" :step="10" />
                      </div>
                      <div class="field-col">
                        <label class="field-label">Top-up point cap</label>
                        <NInputNumber v-model:value="form.points.topup_cap" size="small" :min="0" :step="100" />
                      </div>
                    </div>
                  </div>

                  <div class="points-group">
                    <div class="group-label">Redemption &amp; Streak</div>
                    <div class="points-grid">
                      <div class="field-col">
                        <label class="field-label">Starter cost (points)</label>
                        <NInputNumber
                          v-model:value="form.points.starter_cost"
                          size="small"
                          :min="1"
                          :max="form.points.balance_cap"
                          :step="500"
                        />
                      </div>
                      <div class="field-col">
                        <label class="field-label">Streak target (days)</label>
                        <NInputNumber v-model:value="form.points.streak_target_days" size="small" :min="1" :max="30" />
                      </div>
                      <div class="field-col">
                        <label class="field-label">Streak reward — low</label>
                        <NInputNumber v-model:value="form.points.streak_reward[0]" size="small" :min="1" :max="form.points.balance_cap" />
                      </div>
                      <div class="field-col">
                        <label class="field-label">Streak reward — high</label>
                        <NInputNumber v-model:value="form.points.streak_reward[1]" size="small" :min="1" :max="form.points.balance_cap" />
                      </div>
                    </div>
                  </div>
                </NCard>

                <!-- Reward table -->
                <NCard size="small" class="settings-card points-card reward-table-card">
                  <div class="reward-header">
                    <div>
                      <div class="card-section-title">Claim reward table</div>
                      <span class="item-hint">
                        Each row is a range and its weight. Higher weight = more likely.
                        Total weight: <b class="total-weight">{{ totalWeight() }}</b>
                      </span>
                    </div>
                    <div class="preset-buttons">
                      <NButton
                        v-for="name in Object.keys(REWARD_PRESETS)"
                        :key="name"
                        size="tiny"
                        :type="isPresetActive(name) ? 'primary' : 'default'"
                        :secondary="isPresetActive(name)"
                        :quaternary="!isPresetActive(name)"
                        @click="applyPreset(name)"
                      >
                        {{ name }}
                      </NButton>
                    </div>
                  </div>

                  <div class="reward-rows">
                    <div class="reward-row reward-row-head">
                      <span>Low</span>
                      <span>High</span>
                      <span>Weight</span>
                      <span class="chance-head">Chance</span>
                      <span></span>
                    </div>
                    <div
                      v-for="(row, idx) in form.points.reward_table"
                      :key="idx"
                      class="reward-row"
                    >
                      <NInputNumber v-model:value="row[0]" size="tiny" :min="1" :max="form.points.balance_cap" />
                      <NInputNumber v-model:value="row[1]" size="tiny" :min="1" :max="form.points.balance_cap" />
                      <NInputNumber v-model:value="row[2]" size="tiny" :min="1" />
                      <div class="chance-cell">
                        <span class="chance-pct">{{ rowChancePct(row[2]) }}</span>
                        <div class="chance-bar">
                          <div class="chance-fill" :style="{ width: rowChancePct(row[2]) }" />
                        </div>
                      </div>
                      <NButton quaternary circle size="tiny" type="error" @click="removeRewardRow(idx)">
                        <template #icon>
                          <TrashOutline />
                        </template>
                      </NButton>
                    </div>
                  </div>

                  <NButton size="tiny" type="primary" dashed @click="addRewardRow" class="add-row-btn">
                    <template #icon>
                      <AddOutline />
                    </template>
                    Add Range
                  </NButton>
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
  color: var(--text-1);
}

.cloud-badge {
  font-size: 11px;
  font-weight: 600;
}

.page-subtitle {
  margin: 4px 0 0 0;
  font-size: 13px;
  color: var(--text-3);
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
  color: var(--text-3);
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
  background: var(--surface);
  border: 1px solid var(--border);
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
  color: var(--accent);
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
  color: var(--text-3);
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
  color: var(--accent);
}

.res-error {
  display: flex;
  align-items: center;
  gap: 4px;
  color: var(--danger);
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
  color: var(--text-3);
  width: 20px;
}

.phone-input {
  flex: 1;
}

.empty-hint {
  font-size: 12px;
  color: var(--text-4);
  font-style: italic;
}

/* Settings Card */
.settings-card {
  background: var(--surface);
  border: 1px solid var(--border);
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
  color: var(--text-1);
  display: flex;
  flex-direction: column;
  gap: 2px;
}

.item-hint {
  font-size: 11px;
  font-weight: 400;
  color: var(--text-3);
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
  background: var(--surface);
  border: 1px solid var(--border);
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
  flex-shrink: 0;
  white-space: nowrap;
}

.switch-status-label {
  font-size: 11px;
  font-weight: 600;
  color: var(--text-4);
  transition: color 0.15s ease;
}

.switch-status-label.is-manual {
  color: var(--accent);
}

@media (max-width: 768px) {
  .servers-grid,
  .plans-grid {
    grid-template-columns: 1fr;
  }
}

/* Loyalty Points */
.points-card {
  max-width: none;
}

.points-master-row {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 24px;
  padding-bottom: 14px;
  border-bottom: 1px solid var(--border-subtle);
  margin-bottom: 14px;
}

.master-text {
  display: flex;
  flex-direction: column;
  gap: 4px;
  min-width: 0;
}

.master-title {
  display: flex;
  align-items: center;
  gap: 10px;
  font-size: 14px;
  font-weight: 700;
  color: var(--text-1);
}

.master-icon-tile {
  width: 34px;
  height: 34px;
  flex-shrink: 0;
  border-radius: 9px;
  display: flex;
  align-items: center;
  justify-content: center;
  background: rgba(245, 158, 11, 0.12);
  border: 1px solid rgba(245, 158, 11, 0.28);
}

.master-icon {
  width: 18px;
  height: 18px;
  color: var(--warn);
}

/* Two-column body: Economy Rules | Claim Reward Table */
.points-layout {
  display: grid;
  grid-template-columns: minmax(0, 1fr) minmax(0, 1.15fr);
  gap: 16px;
  align-items: start;
}

.card-section-title {
  font-size: 13px;
  font-weight: 700;
  color: var(--text-1);
  margin-bottom: 12px;
}

.points-group + .points-group {
  margin-top: 16px;
}

.group-label {
  font-size: 10px;
  font-weight: 700;
  letter-spacing: 0.08em;
  text-transform: uppercase;
  color: var(--text-4);
  margin-bottom: 8px;
}

.points-grid {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 12px;
}

.reward-header {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 12px;
  flex-wrap: wrap;
  margin-bottom: 14px;
}

.total-weight {
  color: var(--text-2);
}

.preset-buttons {
  display: inline-flex;
  align-items: center;
  gap: 2px;
  padding: 3px;
  background: var(--surface-2);
  border: 1px solid var(--border);
  border-radius: 8px;
}

.reward-rows {
  display: flex;
  flex-direction: column;
  gap: 6px;
}

.reward-row {
  display: grid;
  grid-template-columns: minmax(0, 1fr) minmax(0, 1fr) minmax(0, 1fr) minmax(0, 92px) 28px;
  gap: 8px;
  align-items: center;
}

.reward-row-head {
  font-size: 11px;
  color: var(--text-3);
  font-weight: 600;
  padding: 0 2px 2px;
}

.reward-row-head .chance-head {
  text-align: right;
}

.chance-cell {
  display: flex;
  flex-direction: column;
  align-items: flex-end;
  gap: 4px;
  min-width: 0;
}

.chance-pct {
  font-size: 11px;
  color: var(--accent);
  font-weight: 600;
  font-variant-numeric: tabular-nums;
}

.chance-bar {
  width: 100%;
  height: 3px;
  border-radius: 2px;
  background: var(--fill-subtle);
  overflow: hidden;
}

.chance-fill {
  height: 100%;
  border-radius: 2px;
  background: var(--accent);
  transition: width 0.2s ease;
}

.add-row-btn {
  margin-top: 14px;
}

@media (max-width: 1100px) {
  .points-layout {
    grid-template-columns: 1fr;
  }
}

@media (max-width: 768px) {
  .points-grid {
    grid-template-columns: 1fr;
  }

  .reward-row {
    grid-template-columns: repeat(3, minmax(0, 1fr)) 56px 24px;
    gap: 6px;
  }
}
</style>
