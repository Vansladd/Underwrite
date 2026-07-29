import { useCallback, useEffect, useRef, useState } from 'react'

// Optimistic and client-side: the submission is one synchronous request, so nothing here is
// streamed from the server. The schedule below is a timed guess at a pipeline we cannot observe.
// Measured from 11 real submissions (2026-07-29): extraction ~4.0-4.6s, enrichment ~0.1-0.3s,
// rating ~0.02s. See design/synthesis/uw-032-staged-loading.md.
export const STAGES = [
  { at: 0, running: 'Extracting…', done: 'Extracted' },
  { at: 3400, running: 'Verifying with Companies House…', done: 'Companies House checked' },
  { at: 4100, running: 'Rating…', done: 'Rated' },
]

// Below this the request is over before a loading state would earn its place; form mode lands at
// ~350ms and so never shows one. Once shown it stays, so a 450ms response cannot flash it away.
export const APPEAR_AFTER_MS = 400
export const MIN_VISIBLE_MS = 600

export function useStagedProgress(pending: boolean) {
  const [visible, setVisible] = useState(false)
  const [stage, setStage] = useState(0)
  const shownAt = useRef<number | null>(null)

  useEffect(() => {
    if (!pending) return
    const timers = [
      window.setTimeout(() => {
        shownAt.current = Date.now()
        setVisible(true)
      }, APPEAR_AFTER_MS),
      // The last stage never completes on a timer: we do not know when the server will answer, and
      // showing every stage done before it does would be the one actively misleading state.
      ...STAGES.slice(1).map((s, i) => window.setTimeout(() => setStage(i + 1), s.at)),
    ]
    // Reset on the way out, not on the way in: a retry after an error starts from stage one.
    return () => {
      timers.forEach(window.clearTimeout)
      shownAt.current = null
      setVisible(false)
      setStage(0)
    }
  }, [pending])

  // Hiding the panel is the caller's move (it navigates away), so the caller owns the floor: a
  // response landing just after the panel appeared must not rip it away one frame later.
  const remainingHold = useCallback(() => {
    if (shownAt.current === null) return 0
    return Math.max(0, MIN_VISIBLE_MS - (Date.now() - shownAt.current))
  }, [])

  return { visible: pending && visible, stage, remainingHold }
}
