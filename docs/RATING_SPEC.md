# Rating Specification v1.0

**Status:** decided · **Ticket:** UW-001 · **Blocks:** UW-010, UW-011
**Rating version constant:** `RATING_VERSION = "v1.0"`

This document is the authoritative source for the rating engine. Where it conflicts with the
original product spec, this document wins — those deltas are listed in §6 with reasoning.

Every value here is encoded in tests (UW-011). Changing a number means changing a test, which
is the point.

---

## 1. Decisions

### D1 · Revenue > £10m → multiplier **2.2**, always refer

**Not 1.7 (the roadmap's original proposal).**

The reframing that settles this: **appetite and authority are orthogonal axes.** Lloyd's
delegated-authority practice distinguishes what a carrier *wants* to write (appetite,
commercial) from what an MGA is *permitted* to bind (authority, contractual — line size, class,
territory). A >£10m-revenue applicant is not unattractive; it exceeds the binder's line size.
The correct outcome is a referral to the carrier's underwriter, who may well want the risk.

That has a direct implementation consequence: in a real referral the risk is routed to the
carrier "with a pre-populated submission summary" — so the referral underwriter needs a
**technically sound indicative price to work from**, not a clamped one.

Clamping at 1.7 prices a £50m-revenue applicant identically to a £3m one. Extrapolating the
curve is both more honest and more defensible:

| Band | Factor | Ratio to previous |
|---|---|---|
| < £100k | 0.8 | — |
| £100k – £500k | 1.0 | ×1.25 |
| £500k – £2m | 1.3 | ×1.30 |
| £2m – £10m | 1.7 | ×1.31 |
| **≥ £10m** | **2.2** | **×1.29** (extrapolated) |

The existing bands progress at a near-constant ~1.3×. 2.2 continues that curve. It is marked in
code as an extrapolation, and it **always refers**, so a human validates the number before it
reaches anyone.

> Sources: [Lloyd's Code of Practice — Delegated Authority](https://assets.lloyds.com/assets/pdf-code-of-practice-delegated-underwriting-v2/1/pdf-code-of-practice-delegated-underwriting-v2.pdf)

### D2 · Sector `other` → multiplier **1.35**, always refer

**Not 1.2 (the roadmap's original proposal). This is the most substantive change.**

1.2 creates an arbitrage: an applicant who honestly says "fintech" pays 1.35, while one who
describes themselves vaguely enough to land in `other` pays 1.2. **Being unclear becomes
cheaper than being accurate.** That is a textbook adverse-selection incentive, and it points the
wrong way.

Two established principles apply:

- **Adverse selection.** The American Academy of Actuaries' *Risk Classification Statement of
  Principles* holds that when insurers cannot charge risk-differentiated premiums, higher risks
  buy more and lower risks buy less, pushing the pooled price above a population-weighted
  average of true risk premiums. The `other` bucket is **self-selecting** — the risks that don't
  fit your named classes are disproportionately the odd ones — so pricing it at the *average* of
  known classes is structurally wrong.
- **Ambiguity loading.** *Pricing Ambiguity in Catastrophe Risk Insurance* (Geneva Risk and
  Insurance Review, 2020) documents that insurers charge higher premiums under ambiguity. Under
  maxmin expected utility, the insurer prices against the **worst case** in the plausible set.

So: `other` = **1.35**, equal to the highest non-declined sector. It always refers, so an
underwriter who learns the real sector can price it *down*. Pricing unknowns at the ceiling and
correcting downward on information is the right direction of travel; the reverse is not.

> **Honesty note for the README:** the specific rule *"price the unknown at or above the worst
> known class"* is practitioner reasoning, not a codified standard — I could not find it named
> in any actuarial standard. It follows from maxmin ambiguity pricing plus adverse selection in
> a self-selecting residual bucket. Present it as reasoning, not as a citable rule.

> Sources: [AAA Risk Classification SoP](https://actuary.org/wp-content/uploads/2025/05/risk.pdf) ·
> [Geneva Risk & Insurance Review (2020)](https://link.springer.com/article/10.1057/s10713-020-00051-2)

### D3 · Declined risks get an `indicative_premium_pence`, never an `annual_premium_pence`

**Refined from "compute, store, never display".** Both fields exist; only one is ever populated
for a given outcome.

The insurance industry already has vocabulary for exactly this hazard — the distinction between
an **indication** ("an estimated, non-binding rate… an appetite signal, not a coverage
commitment") and a **bindable quote** ("the final offer… with a statement of premium, coverage
information, and subjectivities"). Brokers are explicitly warned to know which one they're
holding, because a number in an email gets treated as an offer.

I found **no rule, regulatory or industry, either way** on storing a premium against a decline.
So the decision rests on engineering risk management:

```python
annual_premium_pence:     int | None   # populated ⟺ decision != DECLINE
indicative_premium_pence: int          # always populated
```

**Why store it at all:** portfolio analytics (what am I turning away, and at what technical
price?), appetite calibration, retrospective what-if when appetite widens, and consistency
auditing across the rater.

**Why the two-field split rather than one:** a single always-populated `annual_premium_pence`
next to `decision = DECLINE` is the exact artefact that leaks — exported to a spreadsheet,
surfaced in an API response, rendered by a template that forgot to branch. The mitigation must
be **structural, not procedural**. With the split, the customer-facing serializer only ever
reads `annual_premium_pence`, and for a decline there is nothing there to leak.

**Invariant (test in UW-011):** `decision == DECLINE ⟺ annual_premium_pence is None`.

Declines also carry **structured reason codes**, not free text. This matches the direction of
travel in adverse-underwriting-decision law — a 2026 Texas statute makes "declined due to
underwriting guidelines" an *illegal* answer, requiring identification of the precise factors —
and it satisfies FCA TR24/2, whose central criticism was firms "unable to adequately evidence
how and why."

> Sources: [Access One80 — Quote vs. Indication](https://accessone80.com/bigfootblogs/quote-vs-indication) ·
> [FCA TR24/2](https://www.fca.org.uk/publication/thematic-reviews/tr24-2.pdf)

### D4 · Half-open bands `[lower, upper)` throughout

Standard convention, per Dijkstra's EWD831: the difference between bounds equals the interval
length, and adjacent bands share exactly one boundary value, so gaps and overlaps are impossible
by construction.

**Every boundary value belongs to the band it opens.** £100,000 revenue is band 2. 24 months
trading is the 1.0 band. There are no ambiguous values.

Implementation is an **edges array + `bisect_right`**, not `(min, max)` pairs:

```python
REVENUE_EDGES_PENCE = (10_000_00, 50_000_000, 200_000_000, 1_000_000_000)
REVENUE_FACTORS     = (D("0.8"), D("1.0"), D("1.3"), D("1.7"), D("2.2"))
factor = REVENUE_FACTORS[bisect.bisect_right(REVENUE_EDGES_PENCE, revenue_pence)]
```

A boundary stored once cannot disagree with itself. `(min, max)` pairs can drift when someone
edits one row's `max` and not the next row's `min` — this pattern makes that class of bug
structurally impossible rather than merely tested-for.

Table invariants (edges strictly increasing, factor count == edge count + 1) are asserted at
**import time**, so a malformed table fails the process rather than a quote.

> Source: [Dijkstra EWD831](https://www.cs.utexas.edu/~EWD/transcriptions/EWD08xx/EWD831.html)

---

## 2. Schema changes this forces

Two changes to `ExtractedApplication` and `RatingResult` beyond the original spec. Both land in
the model and schema layers up front, rather than as later migrations.

### D5 · `years_trading: float` → `months_trading: int`

**This is a latent bug in the original schema, not a style preference.**

0.5 and 2.0 *are* exactly representable in IEEE 754 binary64 (both are dyadic rationals), so the
band edges themselves are safe. The danger is entirely upstream: a `years_trading` float invites
a date-derived division somewhere, and

```
730 days / 365.25 = 1.998631…   →  >= 2.0 ?  False
```

**A business that has traded exactly two calendar years gets priced in the under-two band.** No
epsilon fixes this — the value genuinely *is* less than 2.0. The bug is that "2 years" in the
business sense and `730/365.25` are different quantities.

Storing integer months removes the ambiguity at the source: edges become `6` and `24`, exactly
comparable by construction, and the whole domain (0–600 months) is exhaustively testable in 601
cases.

The LLM still extracts a human-shaped value; convert **once, at the schema boundary**
(`months = round(years * 12)`), and never compare the float again.

### D6 · All money as integer **pence**

Fowler's Money pattern: store money in the currency's minor unit as an integer, or as fixed-point
decimal — "absolutely avoid any kind of floating point type."

Consistent with your existing decisions on Saipay (kobo) and Splitem (minor units); same
reasoning, and cross-codebase consistency is worth something on its own.

The split that works:
- **Storage and band comparison:** `int` pence.
- **Factor arithmetic:** `Decimal`, constructed from string literals (`Decimal("1.35")`, never
  `Decimal(1.35)`).
- **`float`:** nowhere in the money path.

Rounding to the nearest £10 becomes rounding to the nearest 1,000 pence, applied **once at the
end** — see §4.

> Sources: [Fowler — Money](https://martinfowler.com/eaaCatalog/money.html) ·
> [Python docs — Floating-Point Arithmetic](https://docs.python.org/3/tutorial/floatingpoint.html)

### D7 · Outcome as an ordered `IntEnum`; combine with `max()`

```python
class Decision(IntEnum):
    AUTO_APPROVE = 0
    REFER        = 1
    DECLINE      = 2
```

`AUTO_APPROVE = 0` is the identity element, so an empty rule set correctly yields auto-approve
with no special-casing. `max()` is the combinator, which makes the join **associative,
commutative, and idempotent** — therefore **order-independent**. That property is what
eliminates the entire "which rule ran first" class of bug, and it's cheap to prove in a test.

**Never short-circuit on the first decline.** Evaluate every rule and collect every reason. The
full reason set is the product; early exit destroys the thing the engine exists to produce.

**Store the enum *name* in the database** (`"DECLINE"`), not the integer. Reordering the enum
later must not silently reinterpret history.

### D8 · `RatingResult` is a trace, not a number

Each applied factor records the premium **before and after**, so the per-factor delta is
computable without re-deriving anything:

```python
@dataclass(frozen=True)
class FactorApplication:
    code: str              # "REVENUE_BAND"
    band_label: str        # "£500k – £2m"
    input_value: int       # 75_000_000 (pence)
    multiplier: Decimal    # Decimal("1.3")
    reason: str            # user-facing copy, rendered verbatim
    premium_before_pence: int
    premium_after_pence: int
```

**Invariant (test in UW-011):** folding `factors` from `base_premium_pence` reproduces
`indicative_premium_pence` exactly. This guarantees the explanation shown to the ops user *is*
the calculation, not a parallel reconstruction that can drift from it.

This also makes NAIC-style "factors in descending order of dollar impact" disclosure a
`sorted()` call rather than a project.

---

## 3. The rating table

**Base rate:** £900 (`90_000` pence) at the £250k limit.

### Limit factor (ILF)

| Limit | Factor |
|---|---|
| £250,000 | 1.0 |
| £500,000 | 1.4 |
| £1,000,000 | 1.9 |
| £2,000,000 | 2.6 |

Discrete lookup, not a band — `requested_limit_gbp` is an enum.

### Revenue band

| Band (pence, half-open) | Label | Factor | Outcome |
|---|---|---|---|
| `[0, 10_000_00)` | < £100k | 0.8 | — |
| `[10_000_00, 50_000_000)` | £100k – £500k | 1.0 | — |
| `[50_000_000, 200_000_000)` | £500k – £2m | 1.3 | — |
| `[200_000_000, 1_000_000_000)` | £2m – £10m | 1.7 | — |
| `[1_000_000_000, ∞)` | ≥ £10m | 2.2 | **REFER** |

### Sector

| Sector | Factor | Outcome |
|---|---|---|
| `saas` | 1.0 | — |
| `ecommerce`, `marketplace` | 1.1 | — |
| `ai_ml` | 1.2 | — |
| `fintech`, `healthtech` | 1.35 | — |
| `other` | **1.35** | **REFER** |
| `crypto` | 1.5 *(indicative only)* | **DECLINE** |

### Data records held

| Value | Factor |
|---|---|
| `under_10k` | 0.9 |
| `10k_100k` | 1.0 |
| `100k_1m` | 1.25 |
| `over_1m` | 1.5 |

### Prior claims

| Count | Factor | Outcome |
|---|---|---|
| 0 | 1.0 | — |
| 1 | 1.4 | **REFER** *(multiplier applies **and** refers)* |
| ≥ 2 | 1.4 *(indicative only)* | **DECLINE** |

### Months trading

| Band (half-open) | Label | Factor | Outcome |
|---|---|---|---|
| `[0, 6)` | under 6 months | 1.2 *(indicative only)* | **DECLINE** — "too new" |
| `[6, 24)` | 6 months – under 2 years | 1.2 | — |
| `[24, ∞)` | 2 years or more | 1.0 | — |

### Hard referral rules (any → at least REFER)

| Code | Condition |
|---|---|
| `LOW_EXTRACTION_CONFIDENCE` | `extraction_confidence < 0.7` |
| `MISSING_FIELDS` | `missing_fields` non-empty |
| `CH_NOT_FOUND` | `ch_found == false` |
| `CH_NAME_MISMATCH` | `ch_name_match_score < 0.85` |
| `CH_STATUS_NOT_ACTIVE` | `ch_company_status != "active"` |
| `CH_DISCREPANCY` | `discrepancies` non-empty |
| `REVENUE_ABOVE_AUTHORITY` | `revenue_pence >= 1_000_000_000` |
| `SECTOR_UNCLASSIFIED` | `sector == "other"` |
| `PRIOR_CLAIM` | `prior_claims_count == 1` |

### Hard decline rules (any → DECLINE)

| Code | Condition |
|---|---|
| `SECTOR_OUT_OF_APPETITE` | `sector == "crypto"` |
| `CLAIMS_HISTORY` | `prior_claims_count >= 2` |
| `TOO_NEW` | `months_trading < 6` |
| `CH_STATUS_TERMINAL` | `ch_company_status in {dissolved, liquidation, receivership, administration, converted-closed, removed, closed}` |

`CH_STATUS_NOT_ACTIVE` (refer) and `CH_STATUS_TERMINAL` (decline) can both fire. Decline wins by
D7. Both reasons are retained.

---

## 4. Calculation order

1. `premium = BASE_RATE_PENCE` (90,000)
2. Apply **limit** factor
3. Apply **revenue** factor
4. Apply **sector** factor
5. Apply **data volume** factor
6. Apply **claims** factor
7. Apply **months trading** factor
8. **Round once**, at the end, to the nearest 1,000 pence (£10), `ROUND_HALF_UP`

All arithmetic in `Decimal`. **Rounding at intermediate steps is forbidden** — it makes the
result order-dependent and breaks the trace-folding invariant in D8.

### Worked example

SaaS · £750k revenue · 100k–1m records · 0 claims · 36 months trading · £1m limit

| Step | Factor | Running (pence) |
|---|---|---|
| Base | — | 90,000 |
| Limit £1m | 1.9 | 171,000 |
| Revenue £500k–£2m | 1.3 | 222,300 |
| Sector saas | 1.0 | 222,300 |
| Data 100k–1m | 1.25 | 277,875 |
| Claims 0 | 1.0 | 277,875 |
| Trading ≥ 2y | 1.0 | 277,875 |
| **Round to nearest £10** | | **278,000 = £2,780** |

**Decision: AUTO_APPROVE.**

*Market sanity check:* published UK guidance puts £1m of cyber cover at £500k–£2m turnover in
the **£1,500–£4,000** range. £2,780 sits mid-band. The engine produces commercially plausible
numbers.

---

## 5. Documented deviations from convention

Two places where this spec knowingly departs from published practice. Both belong in the
README — a deviation you can name and justify reads as rigour; the same deviation unnoticed
reads as ignorance.

### 5.1 The ILF curve is steep — deliberately kept

The original limit factors are structurally sound: concave, with marginal premium per unit of limit
falling 1.60 → 1.00 → 0.70, so they pass the standard consistency test. They are almost exactly
a **Riebesell power curve** (constant ~1.36–1.40 per doubling, α ≈ 0.46).

But the calibration is aggressive:

| Source | Implied per-doubling | Implied `r` |
|---|---|---|
| Riebesell convention, liability | ×1.20 – ×1.30 | 20–30% |
| **Hiscox UK PI, actual published pricing** (£250k ≈ £400, £1m ≈ £600) | **×1.225** | **22.5%** |
| Texas filed auto liability (TDI, 2000) | ×1.08 – ×1.12 | 8–12% |
| **This spec** | **×1.36 – ×1.40** | **37.5%** |

**Decision: keep the original numbers.** Rationale: the Hiscox figure blends *all* professions
including low-severity ones (bookkeepers, coaches), and Hiscox's own guidance notes IT security
consultants pay more "because the potential for catastrophic claims is higher." A pure tech
E&O / cyber book genuinely carries a heavier tail — cyber severity is modelled with generalized
Pareto / log-skew-normal for the ransomware tail. A steeper curve is arguable; 37.5% is at the
aggressive end of arguable.

Changing the headline table mid-build buys churn, not credibility. Being able to say *"I
benchmarked my ILF curve against Riebesell and Hiscox's published PI pricing, it's steep at
r≈37.5% versus the 20–30% convention, and here's why that's defensible for tech E&O"* is worth
considerably more than quietly having used 1.25.

> If you ever want to sit inside convention: r = 25% gives 250k=1.0, 500k=1.25, 1m=1.56, 2m=1.95.

### 5.2 ILFs are being applied to a full premium, not a loss cost

Strictly, an ILF is a ratio of **loss costs** (limited average severity + ALAE + ULAE + risk
load). Applying it to a premium that already contains fixed per-policy expense **overcharges at
high limits**, because fixed expense does not scale with limit. The correct structure is:
apply the ILF to the loss-cost component, then add expense.

**Decision: accept for v1**, and say so. Fixing it means splitting `BASE_RATE` into loss cost +
expense, which is a v1.1 refinement with no demo value. An actuary would flag this in the first
five minutes — better that the README flags it first.

> Sources: [Palmer, *Increased Limits Ratemaking for Liability Insurance*, CAS](https://www.casact.org/sites/default/files/database/studynotes_palmer.pdf) ·
> [Hiscox UK PI pricing](https://www.hiscox.co.uk/business-insurance/professional-indemnity-insurance/faq/how-much-does-professional-indemnity-insurance-cost) ·
> [MatBlas — ILF power curves](https://matblas.com/understanding-ilf-curves-in-insurance-how-power-curves-shape-casualty-excess-pricing/)

---

## 6. Deviations from the original product spec

Six places where this spec departs from the first-pass requirements. Each was a gap or a latent
bug found while writing the rules down, not a preference.

| # | Originally | This spec | Why |
|---|---|---|---|
| 1 | Revenue `>£10m` → refer | `>= £10m` → refer | Half-open consistency (D4). Exactly £10m refers. |
| 2 | Revenue >£10m multiplier undefined | 2.2 | D1 — extrapolate the curve, don't clamp |
| 3 | Sector `other` multiplier undefined | 1.35 | D2 — pricing unknowns below a known class rewards vagueness |
| 4 | `years_trading: float` | `months_trading: int` | D5 — `730/365.25 < 2.0` mis-bands a two-year-old business |
| 5 | Money as `int` pounds | `int` pence | D6 — premium × multipliers produces sub-pound amounts |
| 6 | `annual_premium_gbp` always set | `annual_premium_pence: int \| None` + `indicative_premium_pence: int` | D3 — a premium beside a decline is the artefact that leaks |

---

## 7. Test obligations (UW-011)

Beyond one test per table row:

**Boundary tests — generated from the edges arrays, not hand-written.** For every edge `e`,
assert at `e-1`, `e`, `e+1` in integer units. Generated tests can't rot when a band is added;
hand-written lists always do.

**Invariants — property-based (Hypothesis), with `@example` pins on every band edge.** Hypothesis
is poor at hitting exact boundaries by chance; the pins are not optional.

| Invariant | Catches |
|---|---|
| **Trace folds to premium** — folding `factors` from base reproduces `indicative_premium_pence` | The explanation drifting from the calculation. *Write this one first.* |
| **Decline consistency** — `DECLINE ⟺ annual_premium_pence is None` | "Declined, but we quoted them £412" |
| **Totality** — every input in the domain yields a result, never `None`, never raises | Band gaps |
| **Determinism** — same inputs + version ⇒ byte-identical result | Hidden `now()`, dict-ordering, set-iteration leaks |
| **Order independence** — shuffling rule evaluation never changes the outcome | Proves the D7 lattice join |
| **Monotonic in revenue** — higher revenue never costs less, all else equal | A mistyped factor row (1.05 where 0.95 belonged) that no single example test would notice |
| **Monotonic in limit** — more cover never costs less | Commercially embarrassing if it escapes |
| **Monotonic (inverse) in months trading** — longer history never costs more | Would have caught the `730/365.25` bug if the generator emitted day counts |
| **Precedence** — simultaneously decline- and refer-eligible resolves to `DECLINE`, retaining both reasons | Reason-set truncation |
| **Bounds** — `0 < premium`, and premium is a whole number of pence divisible by 1,000 | Sign flips, float leakage, missed rounding |

**Golden-file regression** on the full `RatingResult` for ~30 representative risks. Any factor
change surfaces as a reviewable JSON diff — this turns "what did this change do to prices?" into
a code-review artefact rather than a spreadsheet exercise. Freeze the goldens once `v1.0` is
tagged; `--force-regen` applies only to a version under development.
