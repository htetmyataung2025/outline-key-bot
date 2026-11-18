<script setup lang="ts">
import { nextTick, ref, watch } from 'vue'
import SvgIcon from './SvgIcon.vue'

const props = defineProps<{ open: boolean; title: string }>()
const emit = defineEmits<{ close: [] }>()
const dialog = ref<HTMLElement | null>(null)
let previousFocus: HTMLElement | null = null

watch(() => props.open, async open => {
  if (open) {
    previousFocus = document.activeElement instanceof HTMLElement ? document.activeElement : null
    await nextTick()
    dialog.value?.querySelector<HTMLButtonElement>('.modal-close')?.focus({ preventScroll: true })
  } else {
    await nextTick()
    if (previousFocus?.isConnected) previousFocus.focus({ preventScroll: true })
  }
}, { flush: 'sync' })

function onBackdropClick(event: MouseEvent) {
  // Backdrop taps must NOT dismiss the dialog (explicit close via X only),
  // but keyboard focus must stay inside the dialog so the focus trap holds.
  if (event.target === event.currentTarget) {
    dialog.value?.querySelector<HTMLButtonElement>('.modal-close')?.focus({ preventScroll: true })
  }
}

function onKeydown(event: KeyboardEvent) {
  if (event.key === 'Escape') {
    event.preventDefault()
    emit('close')
  }
  if (event.key !== 'Tab') return
  const focusable = dialog.value?.querySelectorAll<HTMLElement>('button:not(:disabled),input:not(:disabled),[tabindex="0"]')
  const first = focusable?.[0]
  const last = focusable?.[focusable.length - 1]
  if (event.shiftKey && document.activeElement === first) {
    event.preventDefault()
    last?.focus()
  } else if (!event.shiftKey && document.activeElement === last) {
    event.preventDefault()
    first?.focus()
  }
}
</script>
<template>
  <Transition name="modal-sheet">
    <div v-if="open" id="modal" ref="dialog" class="modal-backdrop show" role="dialog" aria-modal="true" aria-labelledby="modal-title" tabindex="-1" @click="onBackdropClick" @keydown="onKeydown">
      <div class="modal-sheet">
        <div class="modal-grab" aria-hidden="true" />
        <div class="modal-head">
          <h3 id="modal-title">{{ title }}</h3>
          <button class="modal-close" aria-label="Close dialog" @click="emit('close')"><SvgIcon name="close" /></button>
        </div>
        <div id="modal-body" class="modal-body"><slot /></div>
      </div>
    </div>
  </Transition>
</template>
