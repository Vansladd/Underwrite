const STATUS_LABELS: Record<string, string> = {
  received: 'Received',
  auto_approved: 'Auto-approved',
  referred: 'Referred',
  declined: 'Declined',
  quoted: 'Quoted',
  failed: 'Failed',
}

const SECTOR_LABELS: Record<string, string> = {
  saas: 'SaaS',
  fintech: 'fintech',
  healthtech: 'healthtech',
  ecommerce: 'ecommerce',
  ai_ml: 'AI/ML',
  marketplace: 'marketplace',
  crypto: 'crypto',
  other: 'other',
}

export function statusLabel(status: string): string {
  return STATUS_LABELS[status] ?? status
}

export function sectorLabel(sector: string | null): string | null {
  if (!sector) return null
  return SECTOR_LABELS[sector] ?? sector
}

// Whole pounds — indicative premiums round to £10, so no decimals. Em-dash when unpriced.
export function formatPremium(pence: number | null): string {
  if (pence == null) return '—'
  return `£${Math.round(pence / 100).toLocaleString('en-GB')}`
}

// Compact scale for the row meta: £4.2m, £750k.
export function compactPounds(pence: number | null): string | null {
  if (pence == null) return null
  const pounds = pence / 100
  if (pounds >= 1_000_000) return `£${(pounds / 1_000_000).toFixed(1).replace(/\.0$/, '')}m`
  if (pounds >= 1_000) return `£${Math.round(pounds / 1_000)}k`
  return `£${Math.round(pounds)}`
}

export function limitLabel(limitPounds: number | null): string | null {
  if (limitPounds == null) return null
  if (limitPounds >= 1_000_000) return `£${limitPounds / 1_000_000}m limit`
  return `£${Math.round(limitPounds / 1_000)}k limit`
}

export function relativeTime(iso: string): string {
  const diffMs = Date.now() - new Date(iso).getTime()
  const minutes = Math.max(0, Math.floor(diffMs / 60_000))
  if (minutes < 60) return `${minutes}m`
  const hours = Math.floor(minutes / 60)
  if (hours < 24) return `${hours}h`
  return `${Math.floor(hours / 24)}d`
}
