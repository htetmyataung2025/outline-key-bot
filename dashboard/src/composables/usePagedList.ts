import { computed, ref, watch, type Ref } from 'vue'

/**
 * Client-side pagination for a bounded list (record tabs, detail panels).
 *
 * Resets to page 1 whenever the list's length changes (fresh data after a
 * reload, a different customer, ...) so the pager can never sit on an empty
 * trailing page.
 */
export function usePagedList<T = any>(source: Ref<T[]> | (() => T[]), pageSize = 10) {
  const page = ref(1)
  const items = computed(() => (typeof source === 'function' ? source() : source.value))
  const count = computed(() => items.value.length)
  const paged = computed(() => items.value.slice((page.value - 1) * pageSize, page.value * pageSize))
  const rangeStart = computed(() => (count.value === 0 ? 0 : (page.value - 1) * pageSize + 1))
  const rangeEnd = computed(() => Math.min(page.value * pageSize, count.value))

  watch(count, () => {
    page.value = 1
  })

  return { page, pageSize, paged, count, rangeStart, rangeEnd }
}
