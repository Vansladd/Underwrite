import type { SubmissionDetail } from '../hooks/useSubmissions'
import { factorLabel, poundsFromPence } from '../lib/format'

type Rating = NonNullable<SubmissionDetail['rating']>
type Reason = Rating['refer_reasons'][number]

const COLUMNS = 'grid grid-cols-[1fr_88px_60px_92px] items-center gap-2 px-3.5 py-2 text-[13px]'

/** The drawer and the result screen show the same ladder; only the frame differs.
 *
 * `framed` boxes it for the drawer, where it sits directly on the panel. The result screen is
 * already inside a card, and DESIGN.md's elevation ladder forbids nesting a second one.
 */
export function FactorLadder({ rating, framed = true }: { rating: Rating; framed?: boolean }) {
  const final = rating.annual_premium_pence ?? rating.indicative_premium_pence
  return (
    <div className={framed ? 'overflow-hidden rounded-lg border border-border' : ''}>
      <div
        className={`grid grid-cols-[1fr_88px_60px_92px] gap-2 border-b border-border px-3.5 py-2 text-[11px] uppercase tracking-[0.05em] text-ink-subtle ${
          framed ? 'bg-surface-2' : ''
        }`}
      >
        <div>Factor</div>
        <div>Band</div>
        <div className="text-right">×</div>
        <div className="text-right">Running</div>
      </div>
      <div className={`${COLUMNS} border-b border-border`}>
        <div className="text-ink">Base rate</div>
        <div />
        <div />
        <div className="tnum text-right text-ink">{poundsFromPence(rating.base_premium_pence)}</div>
      </div>
      {rating.factors.map((f) => (
        <div key={f.code} className={`${COLUMNS} border-b border-border`}>
          <div className="text-ink">{factorLabel(f.code)}</div>
          <div className="text-xs text-ink-muted">{f.band_label}</div>
          <div className="tnum text-right text-[color:var(--accent-text)]">{f.multiplier}</div>
          <div className="tnum text-right text-ink">{poundsFromPence(f.premium_after_pence)}</div>
        </div>
      ))}
      <div
        className={`grid grid-cols-[1fr_88px_60px_92px] items-center gap-2 border-t border-border px-3.5 py-2.5 font-semibold ${
          framed ? 'bg-surface-2' : 'border-border-strong'
        }`}
      >
        <div className="text-ink">Indicative premium</div>
        {/* The running column stops a few pounds above this: RATING_SPEC rounds once, at the end.
            Said out loud because the screen's whole job is to look defensible. */}
        <div className="col-span-2 text-xs font-normal text-ink-subtle">
          rounded to the nearest £10
        </div>
        <div className="tnum text-right text-[15px] text-ink">{poundsFromPence(final)}</div>
      </div>
    </div>
  )
}

/** `codes` shows the reason taxonomy, which is what an underwriter adjudicating wants. The result
 *  screen drops it: there the operator is relaying an outcome, and PRODUCT.md wants plain language.
 */
export function Reasons({
  reasons,
  tone,
  codes = true,
}: {
  reasons: Reason[]
  tone: 'refer' | 'decline'
  codes?: boolean
}) {
  const chip =
    tone === 'decline'
      ? 'bg-[color:var(--dc-bg)] text-[color:var(--dc-fg)]'
      : 'bg-[color:var(--rf-bg)] text-[color:var(--rf-fg)]'
  const glyph = tone === 'decline' ? 'text-[color:var(--dc-fg)]' : 'text-[color:var(--rf-fg)]'
  return (
    <div className={`flex flex-col ${codes ? 'gap-1.5' : 'gap-2.5'}`}>
      {reasons.map((r, i) => (
        <div key={`${r.code}-${i}`} className="flex items-baseline gap-2 text-[13px]">
          {codes ? (
            <span className={`tnum whitespace-nowrap rounded px-1.5 py-px text-[11px] ${chip}`}>
              {r.code}
            </span>
          ) : (
            <span aria-hidden className={`flex-none ${glyph}`}>
              ▲
            </span>
          )}
          <span className="text-ink">{r.message}</span>
        </div>
      ))}
    </div>
  )
}
