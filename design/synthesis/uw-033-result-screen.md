# Design Synthesis — UW-033 Result Screen

Target: the state the operator lands on once a submission is rated, inside the New submission card,
completing the `form → submitting → result` machine UW-032 started. Reconciles three taste lenses
onto DESIGN.md's tokens (tokens win on colour/type/elevation; the lenses earn composition,
hierarchy, spacing, motion).

## Constraints this must honour (from DESIGN.md / PRODUCT.md)

- **Named Rule 3 — "Status is a dot + word in a soft pill; the ROW stays neutral. No full-row fills,
  no side-stripes."** With PRODUCT.md's anti-reference *"status as full-row colour fills"*, this
  rules out the universal result-screen reflex: a big green or red banner across the card.
- **Anti-reference — "hero metrics, oversized display type."** The scale stops at 28px. The premium
  is the largest thing here and still lives inside the system.
- **Named Rule 2 — numbers are mono + tabular.** Premium, multipliers and running totals all.
- **Named Rule 1 — copper is interaction and identity only.** Exactly one copper control per state.
- **Rule 6 / Elevation — no nested cards.** The ladder is a bare table on the card surface.
- **PRODUCT.md 1 — explainability is the interface.** The ladder and the reasons are inline; nothing
  that justifies the decision sits behind a click.
- **PRODUCT.md 4 — every state designed.** Four states, not the ticket's three: `failed` is reachable
  whenever extraction hard-stops.
- **A11y** — AA in both themes; the verdict is never colour alone (pill = dot + word); the reasons
  carry the meaning in text regardless of hue.

**Where this differs from UW-032:** the loading panel got no colour at all, because progress is not a
signal. This screen states a *verdict*, which is precisely what the status hues exist for. One pill,
spent deliberately.

## The one committed direction

**The same evidence, from the other side.**

The result is not a receipt. It is the first sight of the record an underwriter will later read in
the drawer — so it shows the *same factor ladder* and the *same reasons*, in the same order, with the
same mono treatment. UW-032 began this thread (its stages resolve into the drawer's timeline labels);
UW-033 completes it. The apply flow rehearses the adjudication artefact instead of inventing a
parallel vocabulary for it, which is what "earned familiarity" (PRODUCT.md 3) means in practice.

**One deliberate divergence from the drawer.** The drawer chips every reason with its code
(`CH_NOT_FOUND`, `SECTOR_OUT_OF_APPETITE`) because an underwriter is working the taxonomy. Here the
code is dropped and the sentence stands alone — "plain language over fintech jargon". The operator on
this screen is relaying an outcome, not classifying one.

## What each lens contributed

- **Anti-slop:** the templated result screen is a full-bleed tinted banner, a 48px number, a big
  tick, and confetti-adjacent framing. Every one is rejected by the register — the verdict is the
  same pill the queue uses, at the same size, so the operator reads it with zero relearning. The
  distinctiveness is that the *evidence* is the design: an approved result is mostly a factor ladder.
- **Typographic/spatial discipline:** one step of real hierarchy — 28px mono premium, 22px never
  appears, everything else is 13/14px. A hard left rail shared with the ladder's first column. Air
  above the actions (24px), density inside the table (rows ~36px).
- **Premium craft:** restraint plus one earned moment. The premium sits alone above the ladder with
  nothing competing; the ladder's running column right-aligns into a single vertical line so the
  arithmetic reads down the page. No shadow, no border, no card-in-card — the enclosing card and one
  hairline rule above the total do all the structural work.

## Element spec

**Header row** (all states): `StatusBadge` + company name (14px/500) on the left; submission short
ref in mono `--ink-subtle` 12px on the right — the drawer's `SUBMISSION · AE085F68` idiom.

**auto_approved**
- Premium block: `£3,630` at 28px mono/tabular `--ink`; label "Indicative annual premium" 13px
  `--ink-muted` above it. Excess and validity as one 13px muted line beneath.
- Factor ladder: the drawer's table — factor · band · ×multiplier (mono) · running (mono), base rate
  first, hairline above a bold indicative-premium row.
- Actions: **Download quote** (copper) · Submit another · Open in queue.
  When the PDF has not rendered yet: **Generate quote PDF** takes the copper slot, mirroring the
  drawer's existing Download/Generate pair.

**referred** — no premium anywhere on the screen. A single 14px sentence: *"An underwriter will
review this before a price is confirmed."* Then the reasons as plain sentences with a `▲` in
`--rf-fg`. Actions: Submit another (copper) · Open in queue.

**declined** — decline reasons verbatim, `▲` in `--dc-fg`, and one muted line stating there is no
price to show. Actions: Submit another (copper) · Open in queue.

**failed** — no rating exists. States what could not be done ("This submission could not be read")
and routes back to Paste submission, which is the recovery that actually works. Actions: Try pasting
it (copper) · Open in queue.

## Motion

- Panel → result: 160ms ease-out crossfade, no translate. Same vocabulary as the stage advance.
- The card keeps the held height as a **min**-height, so a short result (declined, failed) cannot
  collapse the card after the staged panel; a tall result (approved, with the ladder) simply grows
  past it. One settle, never a bounce.
- `prefers-reduced-motion`: crossfade becomes instant. Nothing else depends on motion.

## States to mock

1. auto_approved — premium + ladder + Download
2. referred — no premium, reasons
3. declined — reasons verbatim
4. failed — unreadable submission
5. Both themes
