# Design Synthesis — Operator Console

Target: the login + submissions queue now, shaped so the dashboard tabs (#32) and detail drawer (#33)
drop in without a redesign. Reconciles three taste lenses onto DESIGN.md's tokens (tokens win on
colour/type/elevation; the lenses earn composition, hierarchy, spacing, motion).

## The one committed direction

A **working column, not a landing page.** A faint cool canvas; a slim sticky top bar; a left-aligned
working header with **live filter tabs carrying mono counts**; and the **queue table as the hero** —
where each row *defends its own decision* (status + priced premium + the one reason that matters).
Copper appears exactly three times: the wordmark mark, the active-tab underline, the primary button.
Everything else is ink, hairline, and tabular numerals.

## What each lens contributed

- **Anti-slop (design-taste-frontend):** kill the reflex layout — centered card, eyebrow, three stat
  tiles. There are **no stat tiles and no hero metric**; the count lives *in the tabs* where it's
  actionable. Distinctiveness comes from the **data treatment** (mono match-score `0.75`, in-row
  discrepancy hint, right-aligned premium column), not ornament. The table is full-width inside the
  column, not boxed in a rounded card.
- **Typographic/spatial discipline (gpt-taste):** one family, tight rem scale; a hard left alignment
  rail; a 3-tier row hierarchy — **company (500) → summary/meta (muted) → status pill + mono premium**.
  Generous air *between* header and table, dense *within* rows. Numbers get their own right-aligned
  columns so they lock into a vertical line.
- **Premium craft (high-end-visual-design):** the expensive feel is restraint — 1px hairlines doing
  the structural work, a single copper accent, a real **skeleton** (not a spinner), and the detail
  drawer arriving on a proper `--e-float` shadow. No shadow soup, no glass, no gradient.

## Layout & composition

- **Shell:** `--bg` canvas. Sticky **top bar** (`--surface-2`, 56px, 1px bottom border): copper
  square mark + "Underwrite" wordmark (left); theme toggle · operator mono-initials avatar + name ·
  Sign out (right). One working column, `max-width ~1100px`, centered, `px-6`.
- **Header block:** "Submissions" (22px/600) + a muted one-liner. Below it, **filter tabs** —
  `All · Referred·3 · Declined·2 · Approved·1 · Received` — text tabs, 2px copper underline on the
  active one (slides between tabs), each with a mono count chip. `Referred` is the default landing.
- **Queue table:** header row in `--surface-2`, 12px `--ink-subtle` caps labels
  (`SUBMISSION · STATUS · PREMIUM · RECEIVED`). Each data row (~52px):
  - **col 1 (flex):** company name (500 ink) over a one-line summary (`--ink-muted`, truncated) with
    a mono id chip; when a row carries a signal, a compact hint sits under the summary
    (e.g. `▲ name match 0.75` in amber-fg, `● CH strike-off` — the machine's reason, previewed).
  - **col 2:** status pill (dot + word).
  - **col 3 (right, mono):** premium `£3,630` or an `—` em-dash for declines.
  - **col 4 (right, mono, muted):** relative time `18h`.
  - Row hover → `--surface-2`; whole row is a button into the drawer (#33), focus ring inset.
- **States:** loading → 6 skeleton rows (shimmering hairline blocks, not a spinner). Empty → a taught
  message ("No submissions yet — run `make seed`."). Error → honest inline, not a bounce to login.

## Login

Not a marketing hero. A single **`--surface` panel** (`--r`, `--e-panel`), `max-w ~380px`, centered
on the `--bg` canvas, with the copper mark + "Underwrite" wordmark above two labelled inputs and a
copper primary button. Theme toggle in the corner. Generic placeholders (never the demo password).
Inline error under the button. This is the reviewer's first frame — calm, exact, obviously a serious
tool.

## Type hierarchy (the row is the test)

`SUBMISSION` caps-label 12/subtle → **Acme Robotics Ltd** 14/500/ink → `SaaS · £2.5m · CH matched`
13/400/muted → `▲ name match 0.75` 12/mono/amber-fg. Status pill 12/500. Premium 14/mono/tabular/ink.
Time 13/mono/muted. Nothing shouts; the eye lands on the name, then the status, then the number.

## Colour application

Ink + hairline canvas. Status colour only in pills. Copper only on: wordmark mark, active-tab
underline, primary button, links, focus ring. Discrepancy red only in the drawer, always with a ▲ +
label. Both themes are the same layout with swapped tokens — verify each status pill and the copper
button at AA in dark too.

## Motion

Tab underline slides (160ms ease-out). Row hover tint instant. Drawer (#33) slides in from the right
+ fades (200ms ease-out-expo) over a dim backdrop. Skeleton→content crossfade. Theme toggle
crossfades the token values (respect `prefers-reduced-motion`: no translate, crossfade only).

## Element list (build order)

1. Token layer in `index.css` (`:root` + `[data-theme=dark]`), fonts via `@fontsource/ibm-plex-*`.
2. `ThemeToggle` (persists to `localStorage`, sets `data-theme`, defaults to system).
3. `TopBar` (mark, wordmark, toggle, operator, sign-out).
4. `StatusBadge` refit to the status tokens (dot + word).
5. `Login` panel refit.
6. `Queue`: header + `FilterTabs` (with counts) + table + skeleton + empty/error states.
7. (Later, #33) `DetailDrawer`: extracted-vs-CH two-column + factor table.
