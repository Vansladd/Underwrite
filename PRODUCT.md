# Product

## Register

product

## Users

Commercial-lines **underwriters and underwriting ops** at a specialist Tech E&O / Cyber insurer.
They work a queue: a broker submission arrives (usually a pasted email), the system extracts it,
enriches it against Companies House, and prices it deterministically. The operator's job is to
**adjudicate the referrals** — read the machine's reasoning, check the extracted facts against the
official record, and approve, decline, or send back. They are logged in for a shift, moving through
many submissions; speed, trust, and legibility of *why* matter more than delight.

Context: desktop, indoor office lighting, focused task-work, often side-by-side with a broker email
in another window. This is also a **portfolio / interview piece** — a reviewer will open it cold and
judge whether it reads as a serious risk desk, so first-impression craft counts double.

## Product Purpose

Turn an unstructured submission into a **defensible, explainable quote decision** with a full audit
trail. The thesis the whole product defends: the LLM is confined to parsing; pricing is
deterministic, versioned, and explainable. The UI's job is to make that explainability *visible* —
every decision shows its factors, every discrepancy is surfaced, every action names the human who
took it. Success is an underwriter trusting the screen enough to bind or decline in seconds, and an
auditor able to reconstruct exactly how and why.

## Brand Personality

**Precise · trustworthy · quietly serious.** The voice of a well-made instrument, not a consumer
app. Plain language over fintech jargon. Confidence through clarity, never decoration. It should
feel like Linear or a Stripe dashboard sat down at an insurance desk: fast, exact, legible, and calm
under a pile of numbers. Nothing cute; nothing that undermines the sense that real money and real
liability move through here.

## Anti-references

- **Navy-and-gold "fintech trust" theme** — the category reflex; reads dated and generic.
- **Bloomberg-terminal cosplay** — dark, dense, monospace-everything for flavour rather than need.
- **Consumer-fintech gradients, big rounded cards, emoji, playful illustration** — undermines gravity.
- **Marketing-page moves inside the app** — hero metrics, oversized display type, scroll choreography,
  eyebrow kickers, section numbers. This is a tool, not a landing page.
- **Status as full-row colour fills or left side-stripes** — noisy and imprecise.

## Design Principles

1. **Explainability is the interface.** The reason is never hidden behind a click when it can sit in
   the row. Show the factor, the discrepancy, the score — the machine defends its own decision.
2. **Numbers are first-class.** Premiums, match scores, company numbers, and money align in tabular
   figures and read as data, not prose. Precision is legible at a glance.
3. **Earned familiarity.** Standard affordances (tabs, tables, drawers, dialogs) done exactly right.
   The tool disappears into the task; surprise is a bug, not a feature.
4. **Every state is designed.** Loading is a skeleton, empty teaches, error is honest, the audit trail
   names the actor. Half-built states are how ops tools lose trust.
5. **Quiet by default, sharp on signal.** The canvas recedes; colour and weight are spent only where
   a decision hinges — a discrepancy in red, a referral that needs a human, a premium that priced.

## Accessibility & Inclusion

WCAG 2.1 AA. Body text ≥ 4.5:1, large/UI text ≥ 3:1, in **both** light and dark themes. Status and
discrepancy signals never rely on colour alone — always paired with a dot, icon, or label
(protanopia/deuteranopia safe, since red/green/amber carry decision meaning). Full keyboard operation
of the queue, tabs, drawer, and dialogs; visible focus rings. `prefers-reduced-motion` honoured on
every transition (drawer, tabs, row hover → crossfade or instant).
