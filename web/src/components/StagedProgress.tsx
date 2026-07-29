import { STAGES } from '../hooks/useStagedProgress'

export function StagedProgress({ stage }: { stage: number }) {
  return (
    <ol className="flex w-full flex-col py-1">
      {STAGES.map((s, i) => {
        const state = i < stage ? 'done' : i === stage ? 'active' : 'pending'
        return (
          <li
            key={s.running}
            className={`flex h-8 items-center gap-3 text-[13px] transition-colors duration-150 ease-out ${
              state === 'done'
                ? 'text-ink-muted'
                : state === 'active'
                  ? 'font-medium text-ink'
                  : 'text-ink-subtle'
            }`}
          >
            {/* Fixed box so the column never reflows as glyphs swap. No colour: copper is
                interaction and identity only, and the status hues are submission verdicts. */}
            <span className="grid w-4 flex-none place-items-center leading-none">
              {state === 'done' ? (
                <span className="font-medium">✓</span>
              ) : state === 'active' ? (
                <span className="block h-1.5 w-1.5 rounded-full bg-current motion-safe:animate-stage-pulse" />
              ) : (
                <span aria-hidden>·</span>
              )}
            </span>
            {/* Past tense once done: the same labels the drawer's activity timeline uses, so the
                loader reads as the audit trail being written rather than a progress bar. */}
            <span>{state === 'done' ? s.done : s.running}</span>
          </li>
        )
      })}
    </ol>
  )
}
