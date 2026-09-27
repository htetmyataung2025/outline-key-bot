/**
 * Display formatting for audit actors.
 *
 * Entries recorded before the Admin ID + password login (and its mandatory
 * X-Admin-ID header) can carry placeholder identities; map those to honest
 * legacy labels instead of showing raw sentinels. Real Telegram admin IDs
 * pass through untouched.
 */
const LEGACY_ACTOR_LABELS: Record<string, string> = {
  desktop_admin: 'Desktop (legacy)',
  admin: 'Unknown (legacy)',
  'Telegram Admin': 'Unknown (legacy)',
}

export function formatAdminId(id?: string | null): string {
  if (!id) return '—'
  return LEGACY_ACTOR_LABELS[id] ?? id
}
