// Deterministic avatar helpers for customers (no Telegram profile photo is
// available, so we derive a stable initial + gradient from the chat_id/name).

const GRADIENTS = [
  ['#10b981', '#059669'],
  ['#3b82f6', '#2563eb'],
  ['#8b5cf6', '#6d28d9'],
  ['#f59e0b', '#d97706'],
  ['#ec4899', '#be185d'],
  ['#14b8a6', '#0d9488'],
  ['#f43f5e', '#e11d48'],
  ['#6366f1', '#4f46e5'],
]

function hashString(input: string): number {
  let h = 0
  for (let i = 0; i < input.length; i++) {
    h = (h << 5) - h + input.charCodeAt(i)
    h |= 0
  }
  return Math.abs(h)
}

export function avatarInitial(name: string, chatId: string | number): string {
  const n = (name || '').trim()
  if (n) return n.charAt(0).toUpperCase()
  const id = String(chatId || '')
  return id ? id.charAt(0) : '#'
}

export function avatarGradient(chatId: string | number): string {
  const [a, b] = GRADIENTS[hashString(String(chatId || '0')) % GRADIENTS.length]
  return `linear-gradient(135deg, ${a}, ${b})`
}

export function displayName(fullName: string, username: string, chatId: string | number): string {
  return (fullName || '').trim() || (username ? `@${username}` : '') || `User ${chatId}`
}
