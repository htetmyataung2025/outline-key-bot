import { onMounted, onScopeDispose, ref } from 'vue'

export function useReducedMotion() {
  const reduced = ref(false)
  let media: MediaQueryList | undefined
  const update = () => { reduced.value = media?.matches ?? false }
  onMounted(() => { media = matchMedia('(prefers-reduced-motion: reduce)'); update(); media.addEventListener('change', update) })
  onScopeDispose(() => media?.removeEventListener('change', update))
  return reduced
}
