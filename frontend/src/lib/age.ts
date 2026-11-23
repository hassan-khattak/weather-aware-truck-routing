/** "45 min ago", "2 h ago", "3 days ago": how old a timestamp is. */
export function relativeAge(iso: string, nowMs: number): string {
  const minutes = Math.max(Math.round((nowMs - Date.parse(iso)) / 60000), 0)
  if (minutes < 1) return 'just now'
  if (minutes < 60) return `${minutes} min ago`
  const hours = Math.round(minutes / 60)
  if (hours < 48) return `${hours} h ago`
  return `${Math.round(hours / 24)} days ago`
}
