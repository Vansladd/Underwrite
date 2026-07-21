from bisect import bisect_right
from decimal import ROUND_HALF_UP, Decimal

from app.domain.enums import (
    TERMINAL_COMPANY_STATUSES,
    CompanyStatus,
    DataVolume,
    Decision,
    ReasonCode,
    RequestedLimit,
    Sector,
)
from app.domain.rating import (
    Application,
    Enrichment,
    FactorApplication,
    RatingResult,
    Reason,
)

RATING_VERSION = "v1.0"

BASE_RATE_PENCE = 90_000
PREMIUM_ROUNDING_PENCE = 1_000

MIN_EXTRACTION_CONFIDENCE = 0.7
MIN_NAME_MATCH_SCORE = 0.85
REVENUE_AUTHORITY_LIMIT_PENCE = 1_000_000_000

LIMIT_FACTORS: dict[RequestedLimit, Decimal] = {
    RequestedLimit.GBP_250K: Decimal("1.0"),
    RequestedLimit.GBP_500K: Decimal("1.4"),
    RequestedLimit.GBP_1M: Decimal("1.9"),
    RequestedLimit.GBP_2M: Decimal("2.6"),
}

REVENUE_EDGES_PENCE = (10_000_000, 50_000_000, 200_000_000, 1_000_000_000)
REVENUE_FACTORS = (
    Decimal("0.8"),
    Decimal("1.0"),
    Decimal("1.3"),
    Decimal("1.7"),
    Decimal("2.2"),
)
REVENUE_LABELS = (
    "under £100k",
    "£100k – £500k",
    "£500k – £2m",
    "£2m – £10m",
    "£10m or more",
)

MONTHS_TRADING_EDGES = (6, 24)
MONTHS_TRADING_FACTORS = (Decimal("1.2"), Decimal("1.2"), Decimal("1.0"))
MONTHS_TRADING_LABELS = (
    "under 6 months",
    "6 months – under 2 years",
    "2 years or more",
)

SECTOR_FACTORS: dict[Sector, Decimal] = {
    Sector.SAAS: Decimal("1.0"),
    Sector.ECOMMERCE: Decimal("1.1"),
    Sector.MARKETPLACE: Decimal("1.1"),
    Sector.AI_ML: Decimal("1.2"),
    Sector.FINTECH: Decimal("1.35"),
    Sector.HEALTHTECH: Decimal("1.35"),
    Sector.OTHER: Decimal("1.35"),
    Sector.CRYPTO: Decimal("1.5"),
}

DATA_VOLUME_FACTORS: dict[DataVolume, Decimal] = {
    DataVolume.UNDER_10K: Decimal("0.9"),
    DataVolume.TEN_K_TO_100K: Decimal("1.0"),
    DataVolume.HUNDRED_K_TO_1M: Decimal("1.25"),
    DataVolume.OVER_1M: Decimal("1.5"),
}

PRIOR_CLAIMS_EDGES = (1, 2)
PRIOR_CLAIMS_FACTORS = (Decimal("1.0"), Decimal("1.4"), Decimal("1.4"))
PRIOR_CLAIMS_LABELS = (
    "no prior claims",
    "1 prior claim",
    "2 or more prior claims",
)


def _validate_band(
    name: str,
    edges: tuple[int, ...],
    factors: tuple[Decimal, ...],
    labels: tuple[str, ...],
) -> None:
    if list(edges) != sorted(set(edges)):
        raise ValueError(f"{name}: edges must be strictly increasing, got {edges}")
    if len(factors) != len(edges) + 1:
        raise ValueError(
            f"{name}: expected {len(edges) + 1} factors for {len(edges)} edges, got {len(factors)}"
        )
    if len(labels) != len(factors):
        raise ValueError(f"{name}: expected {len(factors)} labels, got {len(labels)}")


def _validate_lookup(name: str, table: dict, members) -> None:
    missing = set(members) - set(table)
    if missing:
        raise ValueError(f"{name}: no factor defined for {sorted(missing)}")


_validate_band("revenue", REVENUE_EDGES_PENCE, REVENUE_FACTORS, REVENUE_LABELS)
_validate_band(
    "months_trading",
    MONTHS_TRADING_EDGES,
    MONTHS_TRADING_FACTORS,
    MONTHS_TRADING_LABELS,
)
_validate_band(
    "prior_claims",
    PRIOR_CLAIMS_EDGES,
    PRIOR_CLAIMS_FACTORS,
    PRIOR_CLAIMS_LABELS,
)
_validate_lookup("limit", LIMIT_FACTORS, RequestedLimit)
_validate_lookup("sector", SECTOR_FACTORS, Sector)
_validate_lookup("data_volume", DATA_VOLUME_FACTORS, DataVolume)


def _band_index(edges: tuple[int, ...], value: int) -> int:
    return bisect_right(edges, value)


def _format_gbp(pence: int) -> str:
    return f"£{Decimal(pence) / 100:,.2f}".removesuffix(".00")


def _round_to_nearest(value: Decimal, step: int) -> int:
    units = (value / step).quantize(Decimal(1), rounding=ROUND_HALF_UP)
    return int(units) * step


def _apply(
    running: Decimal,
    code: str,
    band_label: str,
    multiplier: Decimal,
    reason: str,
    factors: list[FactorApplication],
) -> Decimal:
    after = running * multiplier
    factors.append(
        FactorApplication(
            code=code,
            band_label=band_label,
            multiplier=multiplier,
            reason=reason,
            premium_before_pence=running,
            premium_after_pence=after,
        )
    )
    return after


def _refer_reasons(application: Application, enrichment: Enrichment) -> list[Reason]:
    reasons: list[Reason] = []

    if application.extraction_confidence < MIN_EXTRACTION_CONFIDENCE:
        reasons.append(
            Reason(
                ReasonCode.LOW_EXTRACTION_CONFIDENCE,
                f"Extraction confidence {application.extraction_confidence:.2f} is below "
                f"{MIN_EXTRACTION_CONFIDENCE:.2f}.",
            )
        )

    if application.missing_fields:
        reasons.append(
            Reason(
                ReasonCode.MISSING_FIELDS,
                "Could not find " + ", ".join(application.missing_fields) + " in the submission.",
            )
        )

    if application.annual_revenue_pence >= REVENUE_AUTHORITY_LIMIT_PENCE:
        reasons.append(
            Reason(
                ReasonCode.REVENUE_ABOVE_AUTHORITY,
                "Revenue is at or above £10m, which exceeds binding authority.",
            )
        )

    if application.sector is Sector.OTHER:
        reasons.append(
            Reason(
                ReasonCode.SECTOR_UNCLASSIFIED,
                "Sector could not be classified, so it is priced at the highest "
                "in-appetite sector rate pending review.",
            )
        )

    if application.prior_claims_count == 1:
        reasons.append(Reason(ReasonCode.PRIOR_CLAIM, "One prior claim was disclosed."))

    # Not necessarily match-derived, so checked before the ch_found gate.
    if enrichment.discrepancies:
        reasons.append(
            Reason(
                ReasonCode.CH_DISCREPANCY,
                "Submission conflicts with Companies House: "
                + "; ".join(enrichment.discrepancies)
                + ".",
            )
        )

    # Score and status are absent without a match; CH_NOT_FOUND covers it.
    if not enrichment.ch_found:
        reasons.append(
            Reason(
                ReasonCode.CH_NOT_FOUND,
                "No matching company was found at Companies House.",
            )
        )
        return reasons

    if (
        enrichment.ch_name_match_score is not None
        and enrichment.ch_name_match_score < MIN_NAME_MATCH_SCORE
    ):
        reasons.append(
            Reason(
                ReasonCode.CH_NAME_MISMATCH,
                f"Submitted name matches the Companies House record at only "
                f"{enrichment.ch_name_match_score:.0%}.",
            )
        )

    if enrichment.ch_company_status is None:
        reasons.append(
            Reason(
                ReasonCode.CH_STATUS_NOT_ACTIVE,
                "Companies House did not return a company status.",
            )
        )
    elif enrichment.ch_company_status is not CompanyStatus.ACTIVE:
        reasons.append(
            Reason(
                ReasonCode.CH_STATUS_NOT_ACTIVE,
                f"Companies House status is {enrichment.ch_company_status}, not active.",
            )
        )

    return reasons


def _decline_reasons(application: Application, enrichment: Enrichment) -> list[Reason]:
    reasons: list[Reason] = []

    if application.sector is Sector.CRYPTO:
        reasons.append(
            Reason(
                ReasonCode.SECTOR_OUT_OF_APPETITE,
                "Crypto is outside appetite for this product.",
            )
        )

    if application.prior_claims_count >= 2:
        reasons.append(
            Reason(
                ReasonCode.CLAIMS_HISTORY,
                f"{application.prior_claims_count} prior claims were disclosed.",
            )
        )

    if application.months_trading < MONTHS_TRADING_EDGES[0]:
        reasons.append(
            Reason(
                ReasonCode.TOO_NEW,
                f"Trading for {application.months_trading} months, below the "
                f"{MONTHS_TRADING_EDGES[0]}-month minimum.",
            )
        )

    if enrichment.ch_found and enrichment.ch_company_status in TERMINAL_COMPANY_STATUSES:
        reasons.append(
            Reason(
                ReasonCode.CH_STATUS_TERMINAL,
                f"Companies House status is {enrichment.ch_company_status}.",
            )
        )

    return reasons


def rate(application: Application, enrichment: Enrichment) -> RatingResult:
    factors: list[FactorApplication] = []
    running = Decimal(BASE_RATE_PENCE)

    running = _apply(
        running,
        "LIMIT",
        f"£{application.requested_limit:,} limit",
        LIMIT_FACTORS[application.requested_limit],
        f"Requested limit of £{application.requested_limit:,}.",
        factors,
    )

    revenue_index = _band_index(REVENUE_EDGES_PENCE, application.annual_revenue_pence)
    running = _apply(
        running,
        "REVENUE_BAND",
        REVENUE_LABELS[revenue_index],
        REVENUE_FACTORS[revenue_index],
        f"Annual revenue of {_format_gbp(application.annual_revenue_pence)}.",
        factors,
    )

    running = _apply(
        running,
        "SECTOR",
        application.sector.value,
        SECTOR_FACTORS[application.sector],
        f"Sector is {application.sector.value}.",
        factors,
    )

    running = _apply(
        running,
        "DATA_VOLUME",
        application.data_records_held.value,
        DATA_VOLUME_FACTORS[application.data_records_held],
        f"Holds {application.data_records_held.value} personal data records.",
        factors,
    )

    claims_index = _band_index(PRIOR_CLAIMS_EDGES, application.prior_claims_count)
    running = _apply(
        running,
        "CLAIMS_HISTORY",
        PRIOR_CLAIMS_LABELS[claims_index],
        PRIOR_CLAIMS_FACTORS[claims_index],
        f"Claims history: {PRIOR_CLAIMS_LABELS[claims_index]}.",
        factors,
    )

    months_index = _band_index(MONTHS_TRADING_EDGES, application.months_trading)
    running = _apply(
        running,
        "MONTHS_TRADING",
        MONTHS_TRADING_LABELS[months_index],
        MONTHS_TRADING_FACTORS[months_index],
        f"Trading for {application.months_trading} months.",
        factors,
    )

    indicative_premium_pence = _round_to_nearest(running, PREMIUM_ROUNDING_PENCE)

    refer = _refer_reasons(application, enrichment)
    decline = _decline_reasons(application, enrichment)

    decision = Decision.worst(
        [
            outcome
            for outcome, reasons in ((Decision.REFER, refer), (Decision.DECLINE, decline))
            if reasons
        ]
    )

    return RatingResult(
        rating_version=RATING_VERSION,
        decision=decision,
        base_premium_pence=BASE_RATE_PENCE,
        factors=tuple(factors),
        indicative_premium_pence=indicative_premium_pence,
        annual_premium_pence=(None if decision is Decision.DECLINE else indicative_premium_pence),
        refer_reasons=tuple(refer),
        decline_reasons=tuple(decline),
    )
