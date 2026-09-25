import { ref } from 'vue'

const isCollapsed = ref(localStorage.getItem('sidebar_collapsed') === 'true')

export function useSidebar() {
  function toggle() {
    isCollapsed.value = !isCollapsed.value
    localStorage.setItem('sidebar_collapsed', String(isCollapsed.value))
  }

  function setCollapsed(value: boolean) {
    isCollapsed.value = value
    localStorage.setItem('sidebar_collapsed', String(value))
  }

  return {
    isCollapsed,
    toggle,
    setCollapsed,
  }
}
