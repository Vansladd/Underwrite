# Design

Visual system for the Underwrite operator console. Follows the DESIGN.md spec. **Register: product**
— design serves the task. Restrained colour, one type superfamily, tokens swap for light/dark.

## Theme

A **refined product desk**: crisp cool-neutral canvas, quiet 1px structure, one warm **copper** accent
spent only on interaction and identity. Ships **light and dark** as a pure token swap. The physical
scene: an underwriter at a desk under office light, side-by-side with a broker email, adjudicating
referrals for a shift — calm surface, sharp signal, numbers that read as data.

Commitment axis: **Restrained** (tinted-neutral surface + one accent ≤ 10% of surface). Colour beyond
neutral appears only as status, discrepancy, and the copper accent.

## Color

OKLCH throughout. Neutrals carry a faint cool tint (hue 250). The accent is a **copper/terracotta**
(hue ~47) chosen to sit clearly apart from the semantic **amber** used for the `referred` status
(hue ~85) and the **red** for declines (hue ~26).

### Light (`:root`)
```css
--bg:            oklch(0.985 0.002 250);  /* app canvas */
--surface:       oklch(1.000 0.000 0);    /* panels, rows, drawer */
--surface-2:     oklch(0.972 0.004 250);  /* top bar, toolbars, table header, hover */
--border:        oklch(0.918 0.005 250);  /* hairlines */
--border-strong: oklch(0.855 0.006 250);  /* inputs, dividers that must read */
--ink:           oklch(0.235 0.012 260);  /* primary text  (~13:1 on bg) */
--ink-muted:     oklch(0.470 0.012 260);  /* secondary     (~5.4:1) */
--ink-subtle:    oklch(0.520 0.012 260);  /* placeholder/meta — still ≥4.5:1 */
--accent:        oklch(0.530 0.130 47);   /* copper — primary btn bg (white text ~5:1) */
--accent-hover:  oklch(0.480 0.130 45);
--accent-text:   oklch(0.500 0.140 45);   /* copper as link/text on light (~5.6:1) */
--accent-ring:   oklch(0.530 0.130 47);   /* focus ring */
--on-accent:     oklch(0.995 0.000 0);    /* text/icons on copper */
```

### Dark (`:root[data-theme="dark"]`)
```css
--bg:            oklch(0.180 0.008 260);
--surface:       oklch(0.212 0.008 260);
--surface-2:     oklch(0.242 0.009 260);
--border:        oklch(0.300 0.010 260);
--border-strong: oklch(0.380 0.012 260);
--ink:           oklch(0.950 0.004 260);
--ink-muted:     oklch(0.730 0.007 260);
--ink-subtle:    oklch(0.640 0.007 260);
--accent:        oklch(0.580 0.135 48);   /* copper solid; white text holds ~4.6:1 */
--accent-hover:  oklch(0.640 0.135 50);
--accent-text:   oklch(0.760 0.120 55);   /* brighter copper for links on dark */
--accent-ring:   oklch(0.680 0.130 52);
--on-accent:     oklch(0.170 0.010 260);  /* near-black on copper reads cleaner in dark */
```

### Status (semantic — dot + word in a soft tinted pill; the ROW stays neutral)
Each status has `-bg` (pill fill) and `-fg` (dot + text). Light values; dark uses the same hue at a
low-lightness translucent fill with a brightened `-fg` (define the dark set at build via the same hues).

| status | hue | light `-bg` | light `-fg` |
|---|---|---|---|
| `auto_approved` | 155 green | `oklch(0.950 0.040 155)` | `oklch(0.420 0.110 155)` |
| `referred` | 85 amber | `oklch(0.960 0.055 88)` | `oklch(0.455 0.090 78)` |
| `declined` | 26 red | `oklch(0.952 0.035 26)` | `oklch(0.500 0.165 27)` |
| `failed` | 26 red | `oklch(0.952 0.020 26)` | `oklch(0.470 0.120 27)` |
| `quoted` | 250 blue | `oklch(0.950 0.032 250)` | `oklch(0.480 0.120 255)` |
| `received` | neutral | `var(--surface-2)` | `var(--ink-muted)` |

**Discrepancy red** (detail drawer): inline emphasis — `--fg` red text + a `oklch(… / 0.12)` tint
behind, **always** paired with a triangle icon + label. Never colour alone (decision-bearing).

## Typography

One superfamily, self-hosted (offline-safe, via `@fontsource`): **IBM Plex Sans** for all UI/prose,
**IBM Plex Mono** for every number and identifier. Institutional and precise; deliberately not the
Inter/Geist monoculture. Fixed **rem** scale (product UI — never fluid `clamp` headings).

```
--font-sans: "IBM Plex Sans", ui-sans-serif, system-ui, sans-serif;
--font-mono: "IBM Plex Mono", ui-monospace, "SF Mono", monospace;
```

Scale (ratio ~1.2): `12 · 13 · 14(base) · 16 · 18 · 22 · 28`px. Weights: 400 body, 500 labels/UI,
600 headings/emphasis. Line-height 1.5 prose / 1.35 dense rows. `-0.006em` tracking on ≥18px;
`0` elsewhere.

**Mono is mandatory for data:** premium (`£3,630`), match score (`0.75`), company number
(`SC123456`), counts, and timestamps all use `--font-mono` + `font-variant-numeric: tabular-nums` so
columns align and digits don't jitter between rows.

## Spacing & Radius

4px base grid: `4 · 8 · 12 · 16 · 24 · 32 · 48`. Row height comfortable-efficient (~52px, two lines).
Radii: `--r-sm 6px` (buttons, inputs, pills-on-square), `--r 8px` (panels, drawer, rows-group),
`--r-full 999px` (status pills, avatar). No radius above 12px — refined, not consumer-round.

## Elevation

A three-rung ladder; borders do most of the work. **No nested cards, no side-stripes.**
```
--e-flat:  none;                                   /* canvas, rows */
--e-panel: 0 1px 0 var(--border);                  /* + 1px border: panels, table */
--e-float: 0 8px 24px -8px oklch(0.2 0.02 260 / .18), 0 1px 0 var(--border); /* drawer, popover, dialog */
```
Dark: the float shadow deepens (`/ .45`) and elevation is carried by the surface-lightness step.

## Components

State-complete: every interactive element defines default · hover · focus-visible · active ·
disabled · loading.

- **Top bar** — `--surface-2`, 1px bottom border, 56px. Left: copper mark + "Underwrite". Right:
  theme toggle, operator name (mono initials avatar), sign-out.
- **Filter tabs** — text tabs with a 2px **copper** active underline (animated), a mono count chip
  per tab; `referred` is the default landing tab. Not pill-buttons.
- **Queue table** — `--surface`, header in `--surface-2` with `--ink-subtle` 12px caps labels. Row:
  company name (500) + one-line summary (`--ink-muted`); status pill; mono premium (right-aligned);
  mono relative time. Row hover `--surface-2`, focus ring inset. Skeleton rows for loading; a
  teaching empty state ("Run `make seed`…").
- **Status pill** — dot + word, `--r-full`, status tokens above. The only place status colour lives.
- **Detail drawer (#33)** — right-side `<dialog>`/panel, `--e-float`, ~560px. Two-column
  **Extracted vs Companies House** with a middle match/▲-discrepancy gutter (discrepancies red +
  icon). **Factor breakdown** table: name · band · ×multiplier (mono) · running premium (mono),
  base → indicative. Decision reasons as a labelled list.
- **Buttons** — primary: copper solid, `--on-accent`, `--r-sm`, 500. Secondary: `--surface` + border.
  Ghost: text + hover tint. Focus-visible: 2px `--accent-ring` + 2px offset.
- **Inputs** — `--surface`, `--border-strong`, `--r-sm`; focus → copper border + ring. Placeholder
  `--ink-subtle` (contrast-checked).

## Motion

150–200ms, `ease-out` (quart/expo), state-only — no page-load choreography. Drawer slides + fades in
(`transform: translateX` + opacity); tab underline slides; row hover/press are instant-ish tints;
list load is a skeleton→content crossfade (optional 20ms stagger on rows). **`prefers-reduced-motion`:
drawer + tabs crossfade, no translate.** z-scale: `dropdown 100 · sticky 200 · drawer-backdrop 300 ·
drawer 400 · dialog 500 · toast 600 · tooltip 700`.

## Named Rules

1. **Copper is interaction and identity only** — primary buttons, links, focus rings, active-tab
   underline, the wordmark mark. **Amber is reserved for the `referred` status.** They never share a
   treatment: copper is a saturated solid/underline; amber is a soft tinted pill. Different hue (47 vs
   85), different job.
2. **Numbers are mono + tabular.** Every premium, score, company number, count, and timestamp.
3. **Status is a dot + word in a soft pill; the row stays neutral.** No full-row fills, no side-stripes.
4. **Theme is a token swap.** All colour via CSS variables; light/dark differ only in the `:root` /
   `:root[data-theme="dark"]` block. No per-component `dark:` overrides beyond tokens.
5. **Signals never rely on colour alone.** Status = dot + word; discrepancy = red + triangle + label.
6. **Elevation ladder only** (flat → panel → float). No nested cards, no decorative glass, no shadow
   soup.
