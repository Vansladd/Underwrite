# Design Synthesis — UW-032 Staged Loading

Target: the in-flight state of the New submission card, while a synchronous submission runs
(~4.7s for paste/PDF, ~0.35s for form). Reconciles three taste lenses onto DESIGN.md's tokens
(tokens win on colour/type/elevation; the lenses earn composition, hierarchy, spacing, motion).

## Constraints this must honour (from DESIGN.md / PRODUCT.md)

- **Named Rule 1 — "Copper is interaction and identity only."** A completed-stage tick is neither an
  interaction nor identity, so **no copper on the stages**, and no status hue either (amber is
  `referred`, green is `auto_approved` — both are submission verdicts, not progress).
- **Rule 6 / Elevation — "No nested cards."** This replaces the form body *inside* the existing card,
  so it is bare rows on `--surface`. No bordered sub-panel, no second radius.
- **Motion — "150–200ms, ease-out, state-only — no page-load choreography."** Stage advance is a
  crossfade. See the one narrow exception below.
- **PRODUCT.md 4 — "Loading is a skeleton."** The queue already refuses spinners; so does this.
- **Anti-reference — "Marketing-page moves inside the app."** No progress bar, no percentage, no
  elapsed-time counter. Every one of those implies knowledge of a duration we do not have.
- **A11y** — WCAG AA in both themes; `prefers-reduced-motion` honoured; state never colour-alone
  (each stage carries a distinct glyph *and* a distinct label, not just a tint).

## The one committed direction

**The audit trail, being written live — not a progress bar.**

The three stages are not an invented loading metaphor. They are literally the three events the
pipeline is about to record (`extraction_completed`, `enrichment_completed`, `rating_completed`) and
the same three rows the drawer's Activity timeline will show afterwards. So the loading state is
shaped as a *nascent timeline*: the identical glyph rail, row rhythm, and labels the operator will
meet again in the drawer.

The payoff is the completed-stage copy. A finished stage does not stay in the present tense — it
**flips to the timeline's own past-tense label**, the exact strings `eventLabel()` already uses:

| in flight | completed | (drawer timeline says) |
|---|---|---|
| `Extracting…` | `Extracted` | `Extracted` |
| `Verifying with Companies House…` | `Companies House checked` | `Companies House checked` |
| `Rating…` | `Rated` | `Rated` |

So the loader does not merely *represent* the work — it composes the record in front of you and
hands it to the drawer. That is PRODUCT.md's "explainability is the interface" applied to a state
that is normally throwaway, and it is the reason this reads as a risk desk rather than a web form.

## What each lens contributed

- **Anti-slop:** the reflex here is a spinner, a three-dot ellipsis, or a determinate bar with a
  faked percentage. All three are rejected — the bar because it lies, the spinner because the queue
  already established skeletons as this product's loading idiom. Distinctiveness comes from
  *reusing the product's own audit vocabulary*, not from ornament.
- **Typographic/spatial discipline:** one 13px size throughout, three weights doing the hierarchy
  (500 active · 400 muted done · 400 subtle pending). A hard left rail: glyph column at a fixed
  16px so the labels lock into one vertical line, exactly like the timeline. Rows on the 4px grid at
  32px — tighter than a queue row (52px) because these carry no data to scan.
- **Premium craft:** restraint. No colour, no border, no shadow — the card the panel sits in already
  provides `--e-panel`, and adding anything inside it would be shadow soup. The expensive detail is
  the *tense flip* and the fact that nothing jumps: the glyph column never reflows because all three
  glyphs occupy the same box.

## Element spec

**Rail glyphs** (all 16px box, centered, so no reflow between states):

| state | glyph | colour | weight |
|---|---|---|---|
| pending | `·` (middot) | `--ink-subtle` | 400 |
| active | `●` (filled dot, 6px) | `--ink` | — |
| done | `✓` | `--ink-muted` | 500 |

**Rows** — 32px, `gap 12px` between glyph and label, label 13px:
- pending → `--ink-subtle`, 400
- active → `--ink`, 500
- done → `--ink-muted`, 400

**Block** — sits where the form body was: `padding-top 20px`, rows stacked, `padding-bottom 4px`.
No heading, no border, no card. The card's own hint line is replaced (it describes an input mode
that is no longer being chosen).

**No cancel button.** The request cannot be aborted server-side, and offering a control that
abandons the browser's copy while the pipeline keeps running — and keeps spending Anthropic credit —
would be a lie. Five seconds with no exit is the honest trade.

## Motion

- **Stage advance:** 160ms ease-out crossfade on glyph + label. No translate, no height change.
- **Active dot:** the one narrow exception to "state-only" — a 1.6s ease-in-out opacity loop
  (1 → 0.45 → 1) on the active dot only. Rationale: "Extracting…" holds for ~3.4s, and a wholly
  static panel reads as frozen in a product whose users are watching money move. It is one element,
  one property, low amplitude.
- **`prefers-reduced-motion`:** the pulse is removed entirely (static dot) and the crossfade becomes
  instant. Nothing else changes — the panel is fully legible without any motion.

## Timing (client-side, optimistic — this is not streamed)

Measured from 11 real submissions' audit timestamps on 2026-07-29:

| mode | extract | enrich | rate | total |
|---|---|---|---|---|
| form | 24ms | 309ms | 16ms | **349ms** |
| paste | 4626ms | 81ms | 21ms | **4728ms** |
| pdf_upload | 4015ms | 234ms | 18ms | **4267ms** |

- Panel appears only after **400ms** of pending, and once shown stays **≥600ms**. Form mode
  therefore shows no panel at all — which is correct, not a shortcut: form mode skips the LLM by
  design, so there is no extraction to narrate.
- Advance at **t=0 / 3400ms / 4100ms**, then **hold** on `Rating…`. Holding rather than completing
  is deliberate: we do not know when the server will answer, and a panel that shows all three ticks
  before the response lands would be the one actively misleading state.

## States to mock

1. Active — `Extracting…` (the long hold, ~80% of the visible time)
2. Active — `Companies House checked` done, `Verifying…` → `Rating…`
3. Held — all prior done, `Rating…` still pulsing
4. Both themes; reduced-motion variant is state 1 with a static dot
