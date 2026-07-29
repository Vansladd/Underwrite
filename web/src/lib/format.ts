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

const DATA_VOLUME_LABELS: Record<string, string> = {
  under_10k: 'Under 10,000',
  '10k_100k': '10,000 – 100,000',
  '100k_1m': '100,000 – 1 million',
  over_1m: 'Over 1 million',
}

const INPUT_MODE_LABELS: Record<string, string> = {
  form: 'web form',
  paste: 'pasted broker email',
  pdf_upload: 'uploaded PDF',
}

// Mirrors the backend _FIELD_LABELS the queue headline uses. See api/.../routes/submissions.py.
const FIELD_LABELS: Record<string, string> = {
  annual_revenue_gbp: 'Annual revenue',
  years_trading: 'Years trading',
  prior_claims_count: 'Prior claims',
  requested_limit_gbp: 'Requested limit',
  data_records_held: 'Data volume',
  sector: 'Sector',
  company_name: 'Company name',
}

const FACTOR_LABELS: Record<string, string> = {
  LIMIT: 'Limit',
  REVENUE_BAND: 'Revenue band',
  SECTOR: 'Sector',
  DATA_VOLUME: 'Data volume',
  CLAIMS_HISTORY: 'Claims history',
  MONTHS_TRADING: 'Months trading',
}

export function statusLabel(status: string): string {
  return STATUS_LABELS[status] ?? status
}

export function inputModeLabel(mode: string): string {
  return INPUT_MODE_LABELS[mode] ?? mode
}

export function factorLabel(code: string): string {
  return FACTOR_LABELS[code] ?? code
}

export function fieldLabel(field: string): string {
  return FIELD_LABELS[field] ?? field
}

const EVENT_LABELS: Record<string, string> = {
  submission_received: 'Received',
  extraction_completed: 'Extracted',
  extraction_failed: 'Extraction failed',
  enrichment_completed: 'Companies House checked',
  enrichment_failed: 'Companies House lookup failed',
  rating_completed: 'Rated',
  rating_failed: 'Rating failed',
  submission_approved: 'Approved',
  submission_declined: 'Declined',
  quote_generated: 'Quote generated',
  quote_expired: 'Quote expired',
}

export function eventLabel(eventType: string): string {
  return EVENT_LABELS[eventType] ?? eventType.replace(/_/g, ' ')
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

// Exact whole pounds. Factor pence arrive as ExactDecimal strings; the ladder rounds to £1.
export function poundsFromPence(pence: string | number | null): string {
  if (pence == null) return '—'
  const n = typeof pence === 'string' ? Number(pence) : pence
  if (Number.isNaN(n)) return '—'
  return formatPremium(n)
}

// Mirrors api normalise_company_number: leading alpha prefix, digits zero-padded to 8.
export function normaliseCompanyNumber(raw: string): string {
  const cleaned = raw.replace(/\s+/g, '').toUpperCase()
  const prefix = cleaned.match(/^[A-Z]*/)?.[0] ?? ''
  const digits = cleaned.slice(prefix.length)
  return prefix + digits.padStart(8 - prefix.length, '0')
}

// months → "5 yrs trading", the extracted side of the incorporation row.
export function yearsTradingLabel(months: number | null): string | null {
  if (months == null) return null
  const years = Math.floor(months / 12)
  if (years < 1) return `${months} mo trading`
  return `${years} yr${years === 1 ? '' : 's'} trading`
}

// Compact scale for the row meta: £4.2m, £750k.
export function compactPounds(pence: number | null): string | null {
  if (pence == null) return null
  const pounds = pence / 100
  if (pounds >= 1_000_000) return `£${(pounds / 1_000_000).toFixed(1).replace(/\.0$/, '')}m`
  if (pounds >= 1_000) return `£${Math.round(pounds / 1_000)}k`
  return `£${Math.round(pounds)}`
}

export function dataVolumeLabel(volume: string): string {
  return DATA_VOLUME_LABELS[volume] ?? volume
}

// The limit as it is written on the policy, for the apply form's select.
export function poundsLabel(pounds: number): string {
  return `£${pounds.toLocaleString('en-GB')}`
}

export function limitLabel(limitPounds: number | null): string | null {
  if (limitPounds == null) return null
  if (limitPounds >= 1_000_000) return `£${limitPounds / 1_000_000}m limit`
  return `£${Math.round(limitPounds / 1_000)}k limit`
}

const MONTHS = [
  'January',
  'February',
  'March',
  'April',
  'May',
  'June',
  'July',
  'August',
  'September',
  'October',
  'November',
  'December',
]

// Formatted from the parts, never via `new Date`: a date-only string parses as UTC midnight, so
// toLocaleDateString renders the day before anywhere west of UTC — a quote expiring a day early.
export function calendarDate(iso: string): string {
  const [year, month, day] = iso.slice(0, 10).split('-').map(Number)
  return `${day} ${MONTHS[month - 1]} ${year}`
}

// An expired quote is not a live offer, so it must never read as one. UW-053.
export function validityLabel(quote: { status: string; valid_until: string }): string {
  const when = calendarDate(quote.valid_until)
  return quote.status === 'expired' ? `expired ${when}` : `valid until ${when}`
}

export function relativeTime(iso: string): string {
  const diffMs = Date.now() - new Date(iso).getTime()
  const minutes = Math.max(0, Math.floor(diffMs / 60_000))
  if (minutes < 60) return `${minutes}m`
  const hours = Math.floor(minutes / 60)
  if (hours < 24) return `${hours}h`
  return `${Math.floor(hours / 24)}d`
}
