import { useCallback, useEffect, useRef, useState } from 'react'

import {
  type SubmissionDetail,
  useApproveSubmission,
  useDeclineSubmission,
  useRenderQuote,
  useSubmission,
} from '../hooks/useSubmissions'
import {
  eventLabel,
  factorLabel,
  fieldLabel,
  inputModeLabel,
  normaliseCompanyNumber,
  poundsFromPence,
  relativeTime,
  sectorLabel,
  yearsTradingLabel,
} from '../lib/format'
import { StatusBadge } from './StatusBadge'

const NAME_MATCH_THRESHOLD = 0.85

type Extraction = NonNullable<SubmissionDetail['extraction']>
type Enrichment = NonNullable<SubmissionDetail['enrichment']>
type Rating = NonNullable<SubmissionDetail['rating']>
type Quote = NonNullable<SubmissionDetail['quote']>
type AuditEvent = NonNullable<SubmissionDetail['audit_events']>[number]
type Reason = Rating['refer_reasons'][number]

function CompareRow({
  field,
  extracted,
  official,
  flagged,
}: {
  field: string
  extracted: string
  official: string
  flagged?: boolean
}) {
  return (
    <div className="grid grid-cols-[130px_1fr_28px_1fr] items-center gap-2.5 border-b border-border px-3.5 py-2.5 last:border-b-0">
      <div className="text-[13px] text-ink-muted">{field}</div>
      <div className={`text-[13px] ${flagged ? 'font-medium text-[color:var(--dc-fg)]' : 'text-ink'}`}>
        {extracted}
      </div>
      <div
        className={`grid place-items-center text-[13px] ${flagged ? 'text-[color:var(--dc-fg)]' : 'text-[color:var(--ap-fg)]'}`}
      >
        {flagged ? '▲' : '✓'}
      </div>
      <div className="tnum text-xs text-ink">{official}</div>
    </div>
  )
}

function Callout({ children }: { children: React.ReactNode }) {
  return (
    <div className="mt-2.5 flex gap-2 rounded-md bg-[color:var(--dc-bg)] px-3 py-2.5 text-[13px] text-[color:var(--dc-fg)]">
      <span aria-hidden>▲</span>
      <span>{children}</span>
    </div>
  )
}

function Comparison({ extraction, enrichment }: { extraction: Extraction; enrichment: Enrichment }) {
  if (!enrichment.ch_found) {
    return (
      <Callout>
        No matching company was found at Companies House for{' '}
        <span className="tnum">{extraction.company_name ?? 'this submission'}</span>. The insured could
        not be verified against the register.
      </Callout>
    )
  }

  const score = enrichment.ch_name_match_score
  const nameFlagged = score != null && score < NAME_MATCH_THRESHOLD
  const numberMismatch =
    extraction.company_number != null &&
    enrichment.ch_company_number != null &&
    normaliseCompanyNumber(extraction.company_number) !==
      normaliseCompanyNumber(enrichment.ch_company_number)

  return (
    <>
      <div className="overflow-hidden rounded-lg border border-border">
        <div className="grid grid-cols-[130px_1fr_28px_1fr] gap-2.5 border-b border-border bg-surface-2 px-3.5 py-2.5 text-[11px] uppercase tracking-[0.05em] text-ink-subtle">
          <div>Field</div>
          <div>Extracted</div>
          <div />
          <div>Companies House</div>
        </div>
        <CompareRow
          field="Company name"
          extracted={extraction.company_name ?? '—'}
          official={enrichment.ch_company_name ?? '—'}
          flagged={nameFlagged}
        />
        <CompareRow
          field="Company number"
          extracted={extraction.company_number ?? '—'}
          official={enrichment.ch_company_number ?? '—'}
          flagged={numberMismatch}
        />
        <CompareRow field="Status" extracted="—" official={enrichment.ch_company_status ?? '—'} />
        <CompareRow
          field="Incorporated"
          extracted={yearsTradingLabel(extraction.months_trading) ?? '—'}
          official={enrichment.ch_date_of_creation ?? '—'}
        />
        <CompareRow
          field="SIC"
          extracted="—"
          official={enrichment.sic_codes.length ? enrichment.sic_codes.join(', ') : '—'}
        />
      </div>

      {nameFlagged && (
        <Callout>
          Submitted name matches the Companies House record at only{' '}
          <span className="tnum font-medium">{Math.round((score as number) * 100)}%</span>, below the 85%
          threshold. Verify the insured before binding.
        </Callout>
      )}
      {enrichment.discrepancies.map((sentence) => (
        <Callout key={sentence}>{sentence}</Callout>
      ))}
    </>
  )
}

function FactorLadder({ rating }: { rating: Rating }) {
  const final = rating.annual_premium_pence ?? rating.indicative_premium_pence
  return (
    <div className="overflow-hidden rounded-lg border border-border">
      <div className="grid grid-cols-[1fr_88px_60px_92px] gap-2 border-b border-border bg-surface-2 px-3.5 py-2 text-[11px] uppercase tracking-[0.05em] text-ink-subtle">
        <div>Factor</div>
        <div>Band</div>
        <div className="text-right">×</div>
        <div className="text-right">Running</div>
      </div>
      <div className="grid grid-cols-[1fr_88px_60px_92px] items-center gap-2 border-b border-border px-3.5 py-2 text-[13px]">
        <div className="text-ink">Base rate</div>
        <div />
        <div />
        <div className="tnum text-right text-ink">{poundsFromPence(rating.base_premium_pence)}</div>
      </div>
      {rating.factors.map((f) => (
        <div
          key={f.code}
          className="grid grid-cols-[1fr_88px_60px_92px] items-center gap-2 border-b border-border px-3.5 py-2 text-[13px]"
        >
          <div className="text-ink">{factorLabel(f.code)}</div>
          <div className="text-xs text-ink-muted">{f.band_label}</div>
          <div className="tnum text-right text-[color:var(--accent-text)]">{f.multiplier}</div>
          <div className="tnum text-right text-ink">{poundsFromPence(f.premium_after_pence)}</div>
        </div>
      ))}
      <div className="grid grid-cols-[1fr_88px_60px_92px] items-center gap-2 border-t border-border bg-surface-2 px-3.5 py-2.5 font-semibold">
        <div className="text-ink">Indicative premium</div>
        <div />
        <div />
        <div className="tnum text-right text-[15px] text-ink">{poundsFromPence(final)}</div>
      </div>
    </div>
  )
}

function Reasons({ reasons, tone }: { reasons: Reason[]; tone: 'refer' | 'decline' }) {
  const chip =
    tone === 'decline'
      ? 'bg-[color:var(--dc-bg)] text-[color:var(--dc-fg)]'
      : 'bg-[color:var(--rf-bg)] text-[color:var(--rf-fg)]'
  return (
    <div className="flex flex-col gap-1.5">
      {reasons.map((r, i) => (
        <div key={`${r.code}-${i}`} className="flex items-baseline gap-2 text-[13px]">
          <span className={`tnum whitespace-nowrap rounded px-1.5 py-px text-[11px] ${chip}`}>
            {r.code}
          </span>
          <span className="text-ink">{r.message}</span>
        </div>
      ))}
    </div>
  )
}

function Section({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <section className="mt-6 first:mt-1">
      <h3 className="mb-2.5 text-xs font-medium uppercase tracking-[0.06em] text-ink-subtle">{title}</h3>
      {children}
    </section>
  )
}

function MissingInfo({ fields }: { fields: string[] }) {
  return (
    <div className="flex flex-col gap-1.5">
      {fields.map((f) => (
        <div key={f} className="flex items-baseline gap-2 text-[13px]">
          <span className="whitespace-nowrap rounded bg-[color:var(--rf-bg)] px-1.5 py-px text-[11px] text-[color:var(--rf-fg)]">
            NEEDS INFO
          </span>
          <span className="text-ink">{fieldLabel(f)} was not stated in the submission.</span>
        </div>
      ))}
    </div>
  )
}

function Actions({ s }: { s: SubmissionDetail }) {
  const approve = useApproveSubmission(s.id)
  const decline = useDeclineSubmission(s.id)
  const [reasoning, setReasoning] = useState(false)
  const [reason, setReason] = useState('')
  const canApprove = s.rating?.annual_premium_pence != null
  const busy = approve.isPending || decline.isPending
  const errorText = (approve.error ?? decline.error)?.message

  return (
    <div className="mt-4">
      {reasoning ? (
        <>
          <textarea
            autoFocus
            rows={2}
            value={reason}
            onChange={(e) => setReason(e.target.value)}
            placeholder="Why is this being declined?"
            className="w-full rounded-md border border-border-strong bg-surface px-3 py-2 text-[13px] text-ink placeholder:text-ink-subtle"
          />
          <div className="mt-2 flex gap-2">
            <button
              type="button"
              disabled={!reason.trim() || busy}
              onClick={() => decline.mutate(reason.trim())}
              className="rounded-md bg-[color:var(--dc-fg)] px-3.5 py-2 text-[13px] font-medium text-on-accent disabled:cursor-not-allowed disabled:opacity-45"
            >
              {decline.isPending ? 'Declining…' : 'Confirm decline'}
            </button>
            <button
              type="button"
              disabled={busy}
              onClick={() => {
                setReasoning(false)
                setReason('')
              }}
              className="rounded-md border border-border-strong bg-surface px-3.5 py-2 text-[13px] font-medium text-ink"
            >
              Cancel
            </button>
          </div>
        </>
      ) : (
        <div className="flex gap-2">
          <button
            type="button"
            disabled={!canApprove || busy}
            title={canApprove ? undefined : 'No premium to bind — request the missing details first.'}
            onClick={() => approve.mutate()}
            className="rounded-md bg-accent px-3.5 py-2 text-[13px] font-medium text-on-accent hover:bg-accent-hover disabled:cursor-not-allowed disabled:opacity-45"
          >
            {approve.isPending ? 'Approving…' : 'Approve & bind'}
          </button>
          <button
            type="button"
            disabled={busy}
            onClick={() => setReasoning(true)}
            className="rounded-md border border-border-strong bg-surface px-3.5 py-2 text-[13px] font-medium text-ink disabled:opacity-45"
          >
            Decline
          </button>
        </div>
      )}
      {errorText && <p className="mt-2 text-[13px] text-[color:var(--dc-fg)]">{errorText}</p>}
    </div>
  )
}

function QuotePanel({ quote, submissionId }: { quote: Quote; submissionId: string }) {
  const render = useRenderQuote(submissionId)
  const rows: [string, string][] = [
    ['Limit', poundsFromPence(quote.limit_pence)],
    ['Excess', poundsFromPence(quote.excess_pence)],
    ['Gross premium', poundsFromPence(quote.gross_premium_pence)],
  ]
  return (
    <div className="overflow-hidden rounded-lg border border-border">
      <div className="flex items-center justify-between border-b border-border bg-surface-2 px-3.5 py-2.5">
        <span className="tnum text-[13px] font-medium text-ink">{quote.quote_ref}</span>
        <span className="tnum text-xs text-ink-subtle">valid until {quote.valid_until}</span>
      </div>
      <dl className="flex flex-col gap-2 px-3.5 py-3 text-[13px]">
        {rows.map(([label, value]) => (
          <div key={label} className="flex justify-between">
            <dt className="text-ink-muted">{label}</dt>
            <dd className="tnum text-ink">{value}</dd>
          </div>
        ))}
      </dl>
      <div className="border-t border-border px-3.5 py-2.5">
        {quote.pdf_s3_key ? (
          <a
            href={`/api/submissions/${submissionId}/quote.pdf`}
            target="_blank"
            rel="noreferrer"
            className="text-[13px] font-medium text-[color:var(--accent-text)] hover:underline"
          >
            Download quote (PDF) ↗
          </a>
        ) : (
          <div className="flex items-center gap-3">
            <button
              type="button"
              disabled={render.isPending}
              onClick={() => render.mutate()}
              className="rounded-md border border-border-strong bg-surface px-3 py-1.5 text-[13px] font-medium text-ink disabled:opacity-45"
            >
              {render.isPending ? 'Generating…' : 'Generate PDF'}
            </button>
            <span className="text-[13px] text-ink-subtle">
              {render.isError ? (render.error?.message ?? 'Render failed.') : 'PDF not generated yet.'}
            </span>
          </div>
        )}
      </div>
    </div>
  )
}

function Timeline({ events }: { events: AuditEvent[] }) {
  return (
    <ol className="flex flex-col gap-2">
      {events.map((e) => (
        <li key={e.id} className="flex items-baseline justify-between gap-3 text-[13px]">
          <span className="text-ink">
            {eventLabel(e.event_type)}
            {e.actor_name && <span className="text-ink-muted"> · {e.actor_name}</span>}
          </span>
          <span className="tnum shrink-0 text-xs text-ink-subtle">{relativeTime(e.occurred_at)} ago</span>
        </li>
      ))}
    </ol>
  )
}

function DrawerBody({ s }: { s: SubmissionDetail }) {
  const { extraction, enrichment, rating } = s
  const referReasons = rating?.refer_reasons ?? []
  const declineReasons = rating?.decline_reasons ?? []
  // An incomplete extraction refers without ever reaching the engine, so there are no rating
  // reasons — the missing fields are the reason. See UW-025 error model.
  const missingFields = !rating ? (extraction?.missing_fields ?? []) : []
  const empty = !extraction && !rating

  return (
    <div className="overflow-y-auto px-6 pb-8 pt-5">
      {empty && (
        <p className="mt-2 text-[13px] text-ink-muted">
          This submission failed before it could be extracted or rated.
        </p>
      )}

      {extraction && enrichment && (
        <Section title="Extracted vs Companies House">
          <Comparison extraction={extraction} enrichment={enrichment} />
        </Section>
      )}

      {rating && (
        <Section title="Pricing — how the premium was built">
          <FactorLadder rating={rating} />
        </Section>
      )}

      {s.quote && (
        <Section title="Quote">
          <QuotePanel quote={s.quote} submissionId={s.id} />
        </Section>
      )}

      {declineReasons.length > 0 && (
        <Section title="Why it declined">
          <Reasons reasons={declineReasons} tone="decline" />
        </Section>
      )}
      {declineReasons.length === 0 && referReasons.length > 0 && (
        <Section title="Why it referred">
          <Reasons reasons={referReasons} tone="refer" />
        </Section>
      )}
      {missingFields.length > 0 && (
        <Section title="Why it referred">
          <MissingInfo fields={missingFields} />
        </Section>
      )}

      {s.audit_events && s.audit_events.length > 0 && (
        <Section title="Activity">
          <Timeline events={s.audit_events} />
        </Section>
      )}
    </div>
  )
}

function Header({ s, onClose, closeRef }: { s: SubmissionDetail; onClose: () => void; closeRef: React.Ref<HTMLButtonElement> }) {
  const meta = [
    s.extraction?.sector ? sectorLabel(s.extraction.sector) : null,
    inputModeLabel(s.input_mode),
    `received ${relativeTime(s.created_at)} ago`,
    s.rating ? `rating ${s.rating.rating_version}` : null,
  ]
    .filter(Boolean)
    .join(' · ')

  return (
    <div className="border-b border-border px-6 pb-4 pt-5">
      <div className="flex items-start justify-between gap-3">
        <div className="text-xs uppercase tracking-[0.04em] text-ink-subtle">
          Submission · <span className="tnum">{s.id.slice(0, 8)}</span>
        </div>
        <button
          ref={closeRef}
          type="button"
          onClick={onClose}
          aria-label="Close"
          className="-mt-1 rounded p-1 text-ink-subtle hover:text-ink"
        >
          ✕
        </button>
      </div>
      <div className="mt-2 flex items-center gap-3">
        <h2 id="drawer-title" className="text-[18px] font-semibold tracking-tight text-ink">
          {s.extraction?.company_name ?? 'Untitled submission'}
        </h2>
        <StatusBadge status={s.status} />
      </div>
      <p className="mt-1.5 text-[13px] text-ink-muted">{meta}</p>
      {/* A referral is the only thing an operator decides; other states are terminal. */}
      {s.status === 'referred' && <Actions s={s} />}
    </div>
  )
}

export function Drawer({ id, onClose }: { id: string; onClose: () => void }) {
  const { data, isPending, isError } = useSubmission(id)
  const panelRef = useRef<HTMLDivElement>(null)
  const closeRef = useRef<HTMLButtonElement>(null)
  const ready = Boolean(data) || isError

  // Slide in on the frame after mount; slide out on close, unmounting only once the panel
  // transition finishes (see onPanelTransitionEnd).
  const [open, setOpen] = useState(false)
  const closing = useRef(false)
  const openRef = useRef(false)
  const onCloseRef = useRef(onClose)
  useEffect(() => {
    openRef.current = open
  }, [open])
  useEffect(() => {
    onCloseRef.current = onClose
  })

  // Double rAF: paint the closed state once before flipping to open, so the enter transition runs.
  useEffect(() => {
    let inner = 0
    const outer = requestAnimationFrame(() => {
      inner = requestAnimationFrame(() => setOpen(true))
    })
    return () => {
      cancelAnimationFrame(outer)
      cancelAnimationFrame(inner)
    }
  }, [])

  const requestClose = useCallback(() => {
    // Closed before it ever opened (still off-screen): nothing to animate, unmount now.
    if (!openRef.current) {
      onCloseRef.current()
      return
    }
    closing.current = true
    setOpen(false)
  }, [])

  // Tailwind v4 animates the `translate` property (not `transform`); accept either.
  function onPanelTransitionEnd(e: React.TransitionEvent) {
    const prop = e.propertyName
    if (e.target === panelRef.current && (prop === 'translate' || prop === 'transform') && closing.current) {
      onClose()
    }
  }

  // Land focus on the close button once the header (or error) is actually rendered.
  useEffect(() => {
    if (ready) closeRef.current?.focus()
  }, [ready])

  useEffect(() => {
    const restore = document.activeElement as HTMLElement | null
    document.body.style.overflow = 'hidden'

    function onKey(e: KeyboardEvent) {
      if (e.key === 'Escape') {
        requestClose()
        return
      }
      if (e.key !== 'Tab' || !panelRef.current) return
      const focusables = Array.from(
        panelRef.current.querySelectorAll<HTMLElement>(
          'button:not([disabled]), [href], [tabindex]:not([tabindex="-1"])',
        ),
      )
      if (focusables.length === 0) return
      const first = focusables[0]
      const last = focusables[focusables.length - 1]
      if (e.shiftKey && document.activeElement === first) {
        e.preventDefault()
        last.focus()
      } else if (!e.shiftKey && document.activeElement === last) {
        e.preventDefault()
        first.focus()
      }
    }

    document.addEventListener('keydown', onKey)
    return () => {
      document.removeEventListener('keydown', onKey)
      document.body.style.overflow = ''
      restore?.focus()
    }
  }, [requestClose, id])

  return (
    <div className="fixed inset-0 z-50">
      <button
        type="button"
        aria-label="Close"
        tabIndex={-1}
        onClick={requestClose}
        className={`absolute inset-0 bg-[oklch(0.2_0.02_260/.38)] transition-opacity duration-200 ease-out ${open ? 'opacity-100' : 'opacity-0'}`}
      />
      <aside
        ref={panelRef}
        role="dialog"
        aria-modal="true"
        aria-labelledby="drawer-title"
        onTransitionEnd={onPanelTransitionEnd}
        className={`absolute inset-y-0 right-0 flex w-full max-w-[600px] flex-col bg-surface shadow-[var(--float)] transition-transform duration-200 ease-out will-change-[translate] ${open ? 'translate-x-0' : 'translate-x-full'}`}
      >
        {isPending && (
          <div className="grid flex-1 place-items-center text-sm text-ink-muted">Loading…</div>
        )}
        {isError && (
          <div className="grid flex-1 place-items-center px-6 text-center text-sm text-[color:var(--dc-fg)]">
            Could not load this submission.
            <button ref={closeRef} type="button" onClick={requestClose} className="mt-3 underline">
              Close
            </button>
          </div>
        )}
        {data && (
          <>
            <Header s={data} onClose={requestClose} closeRef={closeRef} />
            <DrawerBody s={data} />
          </>
        )}
      </aside>
    </div>
  )
}
