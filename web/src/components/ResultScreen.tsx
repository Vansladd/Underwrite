import type { SubmissionDetail } from '../hooks/useSubmissions'
import { formatPremium, poundsFromPence, validityLabel } from '../lib/format'
import { FactorLadder, Reasons } from './Evidence'
import { StatusBadge } from './StatusBadge'

const BTN_PRIMARY =
  'h-10 rounded-md bg-accent px-4 text-sm font-medium text-on-accent transition-colors hover:bg-accent-hover disabled:opacity-50'
const BTN_GHOST =
  'h-10 rounded-md border border-border px-4 text-sm font-medium text-ink transition-colors hover:bg-surface-2'
const BTN_LINK = 'px-1 text-[13px] font-medium text-ink-muted transition-colors hover:text-ink'

export function ResultScreen({
  submission,
  onSubmitAnother,
  onOpenInQueue,
  onPasteInstead,
  quotePending,
  onGenerateQuote,
}: {
  submission: SubmissionDetail
  onSubmitAnother: () => void
  onOpenInQueue: () => void
  onPasteInstead: () => void
  quotePending: boolean
  onGenerateQuote: () => void
}) {
  const { status, extraction, rating, quote } = submission
  const referReasons = rating?.refer_reasons ?? []
  const declineReasons = rating?.decline_reasons ?? []

  return (
    <div>
      <div className="flex items-center gap-2.5">
        <StatusBadge status={status} />
        <span className="text-sm font-medium text-ink">
          {extraction?.company_name ?? 'Untitled submission'}
        </span>
        <span className="tnum ml-auto text-xs text-ink-subtle">
          {submission.id.slice(0, 8).toUpperCase()}
        </span>
      </div>

      {status === 'auto_approved' && rating && (
        <>
          <p className="mt-5 text-[13px] text-ink-muted">Indicative annual premium</p>
          <p className="tnum mt-0.5 text-[28px] leading-tight tracking-tight text-ink">
            {formatPremium(rating.annual_premium_pence ?? rating.indicative_premium_pence)}
          </p>
          {quote && (
            <p className="mt-1.5 text-[13px] text-ink-muted">
              {poundsFromPence(quote.excess_pence)} excess · {validityLabel(quote)}
            </p>
          )}
          <div className="mt-5">
            <FactorLadder rating={rating} framed={false} />
          </div>
        </>
      )}

      {status === 'referred' && (
        <>
          <p className="mt-5 text-sm text-ink">
            An underwriter will review this before a price is confirmed.
          </p>
          {referReasons.length > 0 && (
            <div className="mt-3.5">
              <Reasons reasons={referReasons} tone="refer" codes={false} />
            </div>
          )}
          {/* A referral has no bound price, so an indicative number here would read as an offer. */}
          <p className="mt-4 text-[13px] text-ink-muted">
            No indicative price is shown while a submission is with an underwriter — nothing here is
            an offer.
          </p>
        </>
      )}

      {status === 'declined' && (
        <>
          <p className="mt-5 text-sm text-ink">
            This submission falls outside what this product can write.
          </p>
          {declineReasons.length > 0 && (
            <div className="mt-3.5">
              <Reasons reasons={declineReasons} tone="decline" codes={false} />
            </div>
          )}
          <p className="mt-4 text-[13px] text-ink-muted">
            There is no price to show — the risk was not rated.
          </p>
        </>
      )}

      {(status === 'failed' || status === 'received') && (
        <>
          <p className="mt-5 text-sm text-ink">
            This submission could not be read, so nothing was rated.
          </p>
          <p className="mt-4 text-[13px] text-ink-muted">
            The extraction step did not complete. Pasting the text directly is the quickest way
            through — it skips whatever the document was doing.
          </p>
        </>
      )}

      <div className="mt-6 flex items-center gap-3">
        {status === 'auto_approved' && quote?.pdf_s3_key && (
          <a
            href={`/api/submissions/${submission.id}/quote.pdf`}
            // New tab, as the drawer does: the PDF is served inline, so navigating in place would
            // unload the app and take the result with it.
            target="_blank"
            rel="noreferrer"
            className={`${BTN_PRIMARY} grid place-items-center`}
          >
            Download quote
          </a>
        )}
        {status === 'auto_approved' && quote && !quote.pdf_s3_key && (
          <button type="button" onClick={onGenerateQuote} disabled={quotePending} className={BTN_PRIMARY}>
            {quotePending ? 'Generating…' : 'Generate quote PDF'}
          </button>
        )}
        {(status === 'failed' || status === 'received') && (
          <button type="button" onClick={onPasteInstead} className={BTN_PRIMARY}>
            Try pasting it
          </button>
        )}
        <button
          type="button"
          onClick={onSubmitAnother}
          className={status === 'referred' || status === 'declined' ? BTN_PRIMARY : BTN_GHOST}
        >
          Submit another
        </button>
        <button type="button" onClick={onOpenInQueue} className={BTN_LINK}>
          Open in queue
        </button>
      </div>
    </div>
  )
}
