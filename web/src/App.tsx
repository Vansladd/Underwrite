import { useMemo, useState } from 'react'

import { Login } from './Login'
import { FilterTabs, type Tab } from './components/FilterTabs'
import { StatusBadge } from './components/StatusBadge'
import { TopBar } from './components/TopBar'
import { type Operator, useMe } from './hooks/useAuth'
import { type Submission, useSubmissions } from './hooks/useSubmissions'
import {
  compactPounds,
  formatPremium,
  limitLabel,
  relativeTime,
  sectorLabel,
  statusLabel,
} from './lib/format'

const STATUS_ORDER = ['referred', 'declined', 'auto_approved', 'quoted', 'received', 'failed']

function metaLine(s: Submission): string {
  return [sectorLabel(s.sector), compactPounds(s.annual_revenue_pence), limitLabel(s.requested_limit), s.company_number]
    .filter(Boolean)
    .join(' · ')
}

function QueueRow({ s }: { s: Submission }) {
  const glyph = s.status === 'referred' ? '▲' : '●'
  return (
    <div className="grid grid-cols-[1fr_130px_120px_80px] items-center gap-4 border-b border-border px-[18px] py-2.5 last:border-b-0 hover:bg-surface-2">
      <div className="min-w-0">
        <div className="truncate font-medium text-ink">{s.company_name ?? 'Untitled submission'}</div>
        {metaLine(s) && <div className="mt-px truncate text-[13px] text-ink-muted">{metaLine(s)}</div>}
        {s.headline && (
          <div className={`tnum mt-1 truncate text-xs hint-${s.status}`}>
            {glyph} {s.headline}
          </div>
        )}
      </div>
      <div>
        <StatusBadge status={s.status} />
      </div>
      <div className="tnum text-right text-sm text-ink">{formatPremium(s.premium_pence)}</div>
      <div className="tnum text-right text-[13px] text-ink-muted">{relativeTime(s.created_at)}</div>
    </div>
  )
}

function SkeletonRow() {
  return (
    <div className="grid grid-cols-[1fr_130px_120px_80px] items-center gap-4 border-b border-border px-[18px] py-3.5 last:border-b-0">
      <div className="space-y-1.5">
        <div className="h-3.5 w-40 rounded bg-surface-2" />
        <div className="h-3 w-56 rounded bg-surface-2" />
      </div>
      <div className="h-5 w-20 rounded-full bg-surface-2" />
      <div className="ml-auto h-3.5 w-14 rounded bg-surface-2" />
      <div className="ml-auto h-3.5 w-8 rounded bg-surface-2" />
    </div>
  )
}

function Queue({ operator }: { operator: Operator }) {
  const { data, isPending, isError } = useSubmissions()
  const [active, setActive] = useState('referred')

  const tabs = useMemo<Tab[]>(() => {
    const rows = data ?? []
    const counts = rows.reduce<Record<string, number>>((acc, r) => {
      acc[r.status] = (acc[r.status] ?? 0) + 1
      return acc
    }, {})
    const statusTabs = STATUS_ORDER.filter((k) => counts[k]).map((k) => ({
      key: k,
      label: statusLabel(k),
      count: counts[k],
    }))
    return [...statusTabs, { key: 'all', label: 'All', count: rows.length }]
  }, [data])

  const activeKey = tabs.some((t) => t.key === active) ? active : 'all'
  const rows = (data ?? []).filter((r) => activeKey === 'all' || r.status === activeKey)

  return (
    <div className="min-h-screen bg-bg text-ink">
      <TopBar operator={operator} />
      <div className="mx-auto max-w-[1100px] px-6 pb-16 pt-8">
        <h1 className="text-[22px] font-semibold tracking-tight">Submissions</h1>
        <p className="mt-0.5 text-[13px] text-ink-muted">
          Tech E&amp;O / Cyber intake · {data?.length ?? 0} in the queue
        </p>

        {data && data.length > 0 && <FilterTabs tabs={tabs} active={activeKey} onChange={setActive} />}

        <div className="mt-5 overflow-hidden rounded-lg border border-border bg-surface">
          <div className="grid grid-cols-[1fr_130px_120px_80px] gap-4 border-b border-border bg-surface-2 px-[18px] py-2.5 text-[11px] font-medium uppercase tracking-[0.06em] text-ink-subtle">
            <div>Submission</div>
            <div>Status</div>
            <div className="text-right">Premium</div>
            <div className="text-right">Received</div>
          </div>

          {isPending &&
            Array.from({ length: 6 }, (_, i) => <SkeletonRow key={i} />)}

          {isError && (
            <p className="px-[18px] py-10 text-center text-sm text-[color:var(--dc-fg)]">
              Could not load submissions. Check the API is running behind <code>/api</code>.
            </p>
          )}

          {data && data.length === 0 && (
            <p className="px-[18px] py-12 text-center text-sm text-ink-muted">
              No submissions yet. Run <code className="tnum">make seed</code> to load the samples.
            </p>
          )}

          {rows.map((s) => (
            <QueueRow key={s.id} s={s} />
          ))}
        </div>
      </div>
    </div>
  )
}

export function App() {
  const { data: operator, isPending, isError } = useMe()

  if (isPending) {
    return (
      <div className="grid min-h-screen place-items-center bg-bg text-sm text-ink-muted">Loading…</div>
    )
  }
  // isError is a transport/server failure, not a 401 (useMe returns null for that) — don't sign a
  // valid session out over a blip; surface it instead.
  if (isError) {
    return (
      <div className="grid min-h-screen place-items-center bg-bg px-6 text-center text-sm text-[color:var(--dc-fg)]">
        Could not reach the server. Refresh to try again.
      </div>
    )
  }
  if (!operator) return <Login />
  return <Queue operator={operator} />
}
