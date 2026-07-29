import { type FormEvent, useRef, useState } from 'react'

import type { components } from './api/schema'
import { StagedProgress } from './components/StagedProgress'
import { type NewSubmission, useCreateSubmission } from './hooks/useCreateSubmission'
import { useStagedProgress } from './hooks/useStagedProgress'
import { dataVolumeLabel, poundsLabel, sectorLabel } from './lib/format'

type Mode = 'form' | 'paste' | 'pdf'

const MODES: { key: Mode; label: string; hint: string }[] = [
  { key: 'form', label: 'Fill form', hint: 'Typed answers go straight to rating — no model reads them.' },
  { key: 'paste', label: 'Paste submission', hint: "Paste the broker's email; the model extracts the fields." },
  { key: 'pdf', label: 'Upload PDF', hint: 'Text is read from the PDF, then extracted the same way.' },
]

const SECTORS: components['schemas']['Sector'][] = [
  'saas',
  'fintech',
  'healthtech',
  'ecommerce',
  'ai_ml',
  'marketplace',
  'crypto',
  'other',
]
const DATA_VOLUMES: components['schemas']['DataVolume'][] = [
  'under_10k',
  '10k_100k',
  '100k_1m',
  'over_1m',
]
const LIMITS: components['schemas']['RequestedLimit'][] = [250_000, 500_000, 1_000_000, 2_000_000]

// Mirrors api/app/services/pdf_text.py MAX_UPLOAD_BYTES, so the obvious rejection costs no round trip.
const MAX_UPLOAD_BYTES = 10 * 1024 * 1024

const FIELD =
  'mt-1.5 h-9 w-full rounded-md border border-border-strong bg-surface px-3 text-sm text-ink outline-none placeholder:text-ink-subtle focus:border-accent'
const LABEL = 'block text-[13px] font-medium text-ink'

type Fields = {
  company_name: string
  company_number: string
  sector: string
  annual_revenue_gbp: string
  years_trading: string
  prior_claims_count: string
  data_records_held: string
  requested_limit_gbp: string
}

const EMPTY: Fields = {
  company_name: '',
  company_number: '',
  sector: '',
  annual_revenue_gbp: '',
  years_trading: '',
  prior_claims_count: '',
  data_records_held: '',
  requested_limit_gbp: '',
}

// Sector labels read as inline meta elsewhere ("SaaS · £1.8m · …"); a select wants them capitalised.
function capitalise(label: string): string {
  return label[0].toUpperCase() + label.slice(1)
}

function toApplication(fields: Fields) {
  return {
    company_name: fields.company_name.trim(),
    company_number: fields.company_number.trim() || null,
    sector: fields.sector as components['schemas']['Sector'],
    annual_revenue_gbp: Number(fields.annual_revenue_gbp),
    years_trading: Number(fields.years_trading),
    prior_claims_count: Number(fields.prior_claims_count),
    data_records_held: fields.data_records_held as components['schemas']['DataVolume'],
    requested_limit_gbp: Number(
      fields.requested_limit_gbp,
    ) as components['schemas']['RequestedLimit'],
  }
}

function ModeTabs({
  active,
  onChange,
  disabled,
}: {
  active: Mode
  onChange: (mode: Mode) => void
  disabled: boolean
}) {
  return (
    <div role="tablist" aria-label="Choose how to submit" className="mt-6 flex gap-6 border-b border-border">
      {MODES.map((mode) => {
        const isActive = mode.key === active
        return (
          <button
            key={mode.key}
            type="button"
            role="tab"
            aria-selected={isActive}
            // The mode cannot change once a submission is in flight; it decides what was sent.
            disabled={disabled}
            onClick={() => onChange(mode.key)}
            className={`relative pb-3 text-[13px] font-medium transition-colors disabled:opacity-50 ${
              isActive ? 'text-ink' : 'text-ink-muted hover:text-ink'
            }`}
          >
            {mode.label}
            {isActive && (
              <span className="absolute inset-x-0 -bottom-px h-0.5 rounded-full bg-accent" />
            )}
          </button>
        )
      })}
    </div>
  )
}

function Select({
  label,
  value,
  onChange,
  options,
  placeholder,
}: {
  label: string
  value: string
  onChange: (value: string) => void
  options: { value: string; label: string }[]
  placeholder: string
}) {
  return (
    <label className={LABEL}>
      {label}
      <select
        required
        value={value}
        onChange={(e) => onChange(e.target.value)}
        className={`${FIELD} ${value ? '' : 'text-ink-subtle'}`}
      >
        <option value="" disabled>
          {placeholder}
        </option>
        {options.map((option) => (
          <option key={option.value} value={option.value} className="text-ink">
            {option.label}
          </option>
        ))}
      </select>
    </label>
  )
}

export function Apply({
  onCreated,
  onCancel,
}: {
  onCreated: (id: string) => void
  onCancel: () => void
}) {
  const [mode, setMode] = useState<Mode>('form')
  const [fields, setFields] = useState<Fields>(EMPTY)
  const [text, setText] = useState('')
  const [file, setFile] = useState<File | null>(null)
  const [tooLarge, setTooLarge] = useState(false)
  const create = useCreateSubmission()
  const { visible: staged, stage, remainingHold } = useStagedProgress(create.isPending)
  // The stages are far shorter than the form they replace, so the card would collapse and yank the
  // page. Hold the height the form had; StagedProgress centres itself in it.
  const bodyRef = useRef<HTMLDivElement>(null)
  const [heldHeight, setHeldHeight] = useState<number>()

  function set(key: keyof Fields, value: string) {
    setFields((current) => ({ ...current, [key]: value }))
  }

  function switchTo(next: Mode) {
    create.reset()
    // The file input unmounts with the panel, so its selection cannot survive the switch either.
    setFile(null)
    setTooLarge(false)
    setMode(next)
  }

  function onSubmit(event: FormEvent) {
    event.preventDefault()
    setHeldHeight(bodyRef.current?.offsetHeight)
    const submission: NewSubmission =
      mode === 'form'
        ? { mode, application: toApplication(fields) }
        : mode === 'paste'
          ? { mode, text: text.trim() }
          : { mode, file: file! }
    create.mutate(submission, {
      onSuccess: (created) => {
        const hold = remainingHold()
        if (hold === 0) onCreated(created.id)
        else window.setTimeout(() => onCreated(created.id), hold)
      },
      onError: () => setHeldHeight(undefined),
    })
  }

  const ready = mode === 'paste' ? text.trim().length > 0 : mode === 'pdf' ? file !== null : true

  return (
    <div className="mx-auto max-w-[680px] px-6 pb-20 pt-8">
      <button
        type="button"
        onClick={onCancel}
        // Locked with the tabs and Cancel: leaving does not stop the pipeline or the spend, so an
        // exit that looks like an escape would be the lie this screen deliberately avoids.
        disabled={create.isPending}
        className="text-[13px] text-ink-muted transition-colors hover:text-ink disabled:opacity-50"
      >
        ← Submissions
      </button>

      <h1 className="mt-4 text-[22px] font-semibold tracking-tight">New submission</h1>
      <p className="mt-0.5 text-[13px] text-ink-muted">
        Tech E&amp;O / Cyber · rated on receipt, referred to an underwriter when it needs one
      </p>

      <ModeTabs active={mode} onChange={switchTo} disabled={create.isPending} />

      <form onSubmit={onSubmit} className="mt-5 rounded-lg border border-border bg-surface p-6">
        {staged && (
          <div className="flex items-center" style={{ minHeight: heldHeight }}>
            <StagedProgress stage={stage} />
          </div>
        )}

        <div ref={bodyRef} className={staged ? 'hidden' : undefined}>
          <p className="text-[13px] text-ink-muted">{MODES.find((m) => m.key === mode)!.hint}</p>

        {mode === 'form' && (
          <div className="mt-5 grid grid-cols-2 gap-x-4 gap-y-4">
            <label className={`${LABEL} col-span-2`}>
              Company name
              <input
                required
                value={fields.company_name}
                onChange={(e) => set('company_name', e.target.value)}
                placeholder="Acme Robotics Ltd"
                className={FIELD}
              />
            </label>

            <label className={LABEL}>
              Company number <span className="font-normal text-ink-subtle">(optional)</span>
              <input
                value={fields.company_number}
                onChange={(e) => set('company_number', e.target.value)}
                placeholder="09876543"
                className={`${FIELD} tnum`}
              />
            </label>

            <Select
              label="Sector"
              value={fields.sector}
              onChange={(value) => set('sector', value)}
              placeholder="Select a sector"
              options={SECTORS.map((value) => ({ value, label: capitalise(sectorLabel(value)!) }))}
            />

            <label className={LABEL}>
              Annual revenue (£)
              <input
                required
                type="number"
                min="0"
                step="1"
                value={fields.annual_revenue_gbp}
                onChange={(e) => set('annual_revenue_gbp', e.target.value)}
                placeholder="2500000"
                className={`${FIELD} tnum`}
              />
            </label>

            <label className={LABEL}>
              Years trading
              <input
                required
                type="number"
                min="0"
                step="0.5"
                value={fields.years_trading}
                onChange={(e) => set('years_trading', e.target.value)}
                placeholder="6"
                className={`${FIELD} tnum`}
              />
            </label>

            <label className={LABEL}>
              Prior claims
              <input
                required
                type="number"
                min="0"
                step="1"
                value={fields.prior_claims_count}
                onChange={(e) => set('prior_claims_count', e.target.value)}
                placeholder="0"
                className={`${FIELD} tnum`}
              />
            </label>

            <Select
              label="Customer records held"
              value={fields.data_records_held}
              onChange={(value) => set('data_records_held', value)}
              placeholder="Select a band"
              options={DATA_VOLUMES.map((value) => ({ value, label: dataVolumeLabel(value) }))}
            />

            <Select
              label="Requested limit"
              value={fields.requested_limit_gbp}
              onChange={(value) => set('requested_limit_gbp', value)}
              placeholder="Select a limit"
              options={LIMITS.map((value) => ({ value: String(value), label: poundsLabel(value) }))}
            />
          </div>
        )}

        {mode === 'paste' && (
          <label className="mt-5 block">
            <span className="sr-only">Broker submission</span>
            <textarea
              required
              rows={14}
              value={text}
              onChange={(e) => setText(e.target.value)}
              placeholder={'Subject: Tech E&O / Cyber quote — Acme Robotics Ltd\n\nPlease can you quote…'}
              className="w-full rounded-md border border-border-strong bg-surface p-3 text-sm leading-relaxed text-ink outline-none placeholder:text-ink-subtle focus:border-accent"
            />
          </label>
        )}

        {mode === 'pdf' && (
          <div className="mt-5">
            <label className={LABEL}>
              <span className="sr-only">Submission PDF</span>
              <input
                required
                type="file"
                accept="application/pdf,.pdf"
                onChange={(e) => {
                  const picked = e.target.files?.[0] ?? null
                  setTooLarge(picked !== null && picked.size > MAX_UPLOAD_BYTES)
                  setFile(picked)
                  create.reset()
                }}
                className="block w-full rounded-md border border-dashed border-border-strong bg-surface p-6 text-sm text-ink-muted outline-none file:mr-4 file:rounded-md file:border-0 file:bg-surface-2 file:px-3 file:py-1.5 file:text-sm file:font-medium file:text-ink focus:border-accent"
              />
            </label>
            <p className="mt-2 text-xs text-ink-subtle">
              Text-based PDFs up to 10MB. A scanned page has no text to read — paste it instead.
            </p>
          </div>
        )}

        {tooLarge && mode === 'pdf' && (
          <p className="mt-4 text-[13px] text-[color:var(--dc-fg)]">
            That PDF is larger than 10MB.
          </p>
        )}

        {create.isError && (
          <p className="mt-4 text-[13px] text-[color:var(--dc-fg)]">{create.error.message}</p>
        )}

          <div className="mt-6 flex items-center gap-3">
            <button
              type="submit"
              disabled={create.isPending || !ready || tooLarge}
              className="h-10 rounded-md bg-accent px-4 text-sm font-medium text-on-accent transition-colors hover:bg-accent-hover disabled:opacity-50"
            >
              {create.isPending ? 'Submitting…' : 'Submit'}
            </button>
            <button
              type="button"
              onClick={onCancel}
              disabled={create.isPending}
              className="h-10 rounded-md border border-border px-4 text-sm font-medium text-ink transition-colors hover:bg-surface-2 disabled:opacity-50"
            >
              Cancel
            </button>
          </div>
        </div>
      </form>
    </div>
  )
}
