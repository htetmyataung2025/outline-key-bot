<script setup lang="ts">
import { ref } from 'vue'
import SvgIcon from '../ui/SvgIcon.vue'
import { useMiniApp } from '../../composables/useMiniApp'
const { state, selectReceipt } = useMiniApp()
const fileInput = ref<HTMLInputElement | null>(null)
const dragover = ref(false)
function onChange(event: Event) { const input = event.target as HTMLInputElement; selectReceipt(input.files?.[0]); input.value = '' }
function onDrop(event: DragEvent) { dragover.value = false; selectReceipt(event.dataTransfer?.files[0]) }
function onLeave(event: DragEvent) { if (!(event.currentTarget instanceof Element) || !(event.relatedTarget instanceof Node) || !event.currentTarget.contains(event.relatedTarget)) dragover.value = false }
</script>
<template>
  <label id="receipt-drop" class="upload-area" :class="{ dragover }" for="receipt-file" tabindex="0" role="button" aria-label="Upload payment receipt image" @keydown.enter.prevent="fileInput?.click()" @keydown.space.prevent="fileInput?.click()" @dragover.prevent="dragover = true" @dragleave="onLeave" @drop.prevent="onDrop">
    <span class="upload-icon"><SvgIcon :name="state.receipt ? 'check-circle' : 'upload'" /></span><span class="upload-text"><strong>{{ state.receipt?.name ?? 'ငွေလွှဲ Screenshot တင်ရန်' }}</strong><small>{{ state.receipt ? 'ပုံကိုရွေးထားပါပြီ · ပြောင်းရန်နှိပ်ပါ' : 'ပုံကိုရွေးပါ သို့မဟုတ် ဒီနေရာမှာချပါ · 10 MB အထိ' }}</small></span><img v-if="state.receipt" class="uploaded-preview" :src="state.receipt.url" alt="Selected receipt preview" />
  </label>
  <input id="receipt-file" ref="fileInput" class="file-hidden" type="file" accept="image/*" @change="onChange" />
</template>
