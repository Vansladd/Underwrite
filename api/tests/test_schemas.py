import json
from decimal import Decimal

import pytest
from pydantic import ValidationError
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from app.domain.enums import DataVolume, Decision, InputMode, RequestedLimit, Sector
from app.models import Extraction, Submission
from app.schemas import (
    AuditEventRead,
    EnrichmentRead,
    ExtractedApplication,
    ExtractionRead,
    IncompleteExtraction,
    QuoteRead,
    RatingRead,
    SubmissionCreate,
    SubmissionDetail,
    SubmissionRead,
    to_months,
    to_pence,
)
from tests.factories import make_full_submission, make_submission

BROKER_EMAIL = {
    "company_name": "Example Ltd",
    "company_number": "00000006",
    "sector": Sector.SAAS,
    "annual_revenue_gbp": 750_000.0,
    "years_trading": 3.0,
    "prior_claims_count": 0,
    "data_records_held": DataVolume.HUNDRED_K_TO_1M,
    "requested_limit_gbp": RequestedLimit.GBP_1M,
    "extraction_confidence": 0.94,
}


def extracted(**overrides) -> ExtractedApplication:
    return ExtractedApplication(**{**BROKER_EMAIL, **overrides})


async def load_full(db, submission_id) -> Submission:
    return await db.scalar(
        select(Submission)
        .where(Submission.id == submission_id)
        .options(
            selectinload(Submission.extraction),
            selectinload(Submission.enrichment),
            selectinload(Submission.rating),
            selectinload(Submission.quote),
            selectinload(Submission.audit_events),
        )
    )


# --- the conversion, which is the whole point of the boundary --------------------------


@pytest.mark.parametrize(
    ("pounds", "pence"),
    [(8.7, 870), (0.29, 29), (1234.56, 123_456), (750_000.0, 75_000_000), (0.0, 0)],
)
def test_pounds_convert_to_exact_pence(pounds, pence):
    assert to_pence(pounds) == pence


@pytest.mark.parametrize(("pounds", "pence"), [(8.7, 870), (0.29, 29)])
def test_the_obvious_conversion_would_have_been_wrong(pounds, pence):
    # int(8.7 * 100) is 869. This is why to_pence goes through Decimal(str(x)).
    assert int(pounds * 100) != pence
    assert to_pence(pounds) == pence


def test_two_calendar_years_of_trading_lands_in_the_two_year_band():
    # RATING_SPEC D5: the float mis-bands a business that has traded exactly two years.
    date_derived = 730 / 365.25

    assert date_derived < 2.0
    assert to_months(date_derived) == 24


@pytest.mark.parametrize(
    ("years", "months"),
    [(0.0, 0), (0.5, 6), (1.0, 12), (2.0, 24), (3.0, 36), (0.208333, 2)],
)
def test_years_convert_to_months(years, months):
    assert to_months(years) == months


def test_conversion_rounds_half_up_like_the_rating_engine():
    # Python's round() is half-even, so round(1.5) is 2 but round(2.5) is also 2.
    assert to_months(0.125) == 2
    assert to_months(0.208334) == 3
    assert to_pence(0.005) == 1


def test_a_complete_extraction_converts_to_a_rateable_application():
    application = extracted().to_domain()

    assert application.annual_revenue_pence == 75_000_000
    assert application.months_trading == 36
    assert application.sector is Sector.SAAS
    assert application.requested_limit is RequestedLimit.GBP_1M


@pytest.mark.parametrize(
    ("missing", "expected"),
    [
        ({"annual_revenue_gbp": None}, ("annual_revenue_gbp",)),
        ({"years_trading": None}, ("years_trading",)),
        ({"sector": None}, ("sector",)),
        (
            {"annual_revenue_gbp": None, "prior_claims_count": None},
            ("annual_revenue_gbp", "prior_claims_count"),
        ),
    ],
)
def test_an_incomplete_extraction_refuses_to_invent_a_value(missing, expected):
    with pytest.raises(IncompleteExtraction) as raised:
        extracted(**missing).to_domain()

    assert raised.value.missing == expected


def test_a_missing_company_number_does_not_block_rating():
    application = extracted(company_number=None).to_domain()

    assert application.months_trading == 36


def test_orm_kwargs_cover_every_extraction_column():
    kwargs = set(extracted().to_orm_kwargs("claude-sonnet-5"))
    columns = {c.name for c in Extraction.__table__.columns} - {"id", "submission_id", "created_at"}

    # Derived from the schema, so a new field cannot silently miss the converter.
    assert kwargs == columns


def test_infinite_money_is_rejected_before_it_reaches_the_converter():
    # inf satisfies ge=0; Decimal(str(inf)).quantize() then raises InvalidOperation.
    with pytest.raises(ValueError, match="finite number"):
        extracted(annual_revenue_gbp=float("inf"))


def test_a_hallucinated_field_name_is_an_error_not_a_silent_null():
    # Otherwise "annual_revenue" instead of "annual_revenue_gbp" looks like never-guess working.
    with pytest.raises(ValueError, match="Extra inputs are not permitted"):
        extracted(annual_revenue="750k")


def test_orm_kwargs_keep_nulls_null_rather_than_defaulting_them():
    kwargs = extracted(annual_revenue_gbp=None, years_trading=None).to_orm_kwargs("claude-sonnet-5")

    assert kwargs["annual_revenue_pence"] is None
    assert kwargs["months_trading"] is None
    assert kwargs["requested_limit"] is RequestedLimit.GBP_1M
    assert kwargs["model"] == "claude-sonnet-5"


# --- the LLM contract ------------------------------------------------------------------


def test_the_extraction_schema_is_shaped_for_messages_parse():
    schema = ExtractedApplication.model_json_schema()

    assert set(schema["required"]) == {"extraction_confidence"}
    assert set(schema["$defs"]) == {"Sector", "DataVolume", "RequestedLimit"}
    assert schema["properties"]["annual_revenue_gbp"]["default"] is None
    # Broker units, not storage units: a rambling email says "£750k", never "75000000 pence".
    assert "annual_revenue_pence" not in schema["properties"]
    assert "months_trading" not in schema["properties"]


def test_extraction_confidence_stays_a_probability():
    with pytest.raises(ValueError, match="less than or equal to 1"):
        extracted(extraction_confidence=1.4)


def test_negative_money_is_rejected_at_the_boundary():
    with pytest.raises(ValueError, match="greater than or equal to 0"):
        extracted(annual_revenue_gbp=-1.0)


# --- ORM round-trips, the ticket's DoD ---------------------------------------------------


async def test_every_model_round_trips_into_its_read_schema(db):
    submission_id = (await make_full_submission(db)).id
    db.expire_all()

    loaded = await load_full(db, submission_id)

    assert SubmissionRead.model_validate(loaded).status is loaded.status
    assert ExtractionRead.model_validate(loaded.extraction).sector is Sector.SAAS
    assert EnrichmentRead.model_validate(loaded.enrichment).sic_codes == ["62012", "01110"]
    assert RatingRead.model_validate(loaded.rating).decision is Decision.REFER
    assert QuoteRead.model_validate(loaded.quote).quote_ref == "UW-2026-0001"
    assert AuditEventRead.model_validate(loaded.audit_events[0]).actor.value == "system"


async def test_submission_detail_nests_every_relation(db):
    submission_id = (await make_full_submission(db)).id
    db.expire_all()

    loaded = await load_full(db, submission_id)
    detail = SubmissionDetail.model_validate(loaded)

    assert detail.extraction.company_name == "Example Ltd"
    assert detail.enrichment.ch_company_status_detail == "active-proposal-to-strike-off"
    assert detail.rating.refer_reasons[0].code.value == "CH_DISCREPANCY"
    assert detail.quote.limit_pence == 100_000_000
    assert len(detail.audit_events) == 1


async def test_an_empty_submission_serialises_with_null_relations(db):
    submission_id = (await make_submission(db)).id
    db.expire_all()

    loaded = await load_full(db, submission_id)
    detail = SubmissionDetail.model_validate(loaded)

    assert (detail.extraction, detail.rating, detail.quote) == (None, None, None)
    assert detail.audit_events == []


# --- Decimal survives the whole path ------------------------------------------------------


STORED_RATING = {
    "id": "0f9d1e6a-8d3f-4a1c-9d2b-2f9a6c1e4b77",
    "rating_version": "v1.0",
    "decision": "REFER",
    "base_premium_pence": 90_000,
    "indicative_premium_pence": 278_000,
    "annual_premium_pence": 278_000,
    "factors": [
        {
            "code": "DATA_VOLUME",
            "band_label": "100k_1m",
            "multiplier": "1.25",
            "reason": "Holds 100k_1m personal data records.",
            "premium_before_pence": "222300",
            "premium_after_pence": "277875",
        }
    ],
    "refer_reasons": [],
    "decline_reasons": [],
    "created_at": "2026-07-21T12:00:00+00:00",
}


def test_factor_multipliers_stay_exact_from_jsonb_to_json():
    rating = RatingRead.model_validate(STORED_RATING)
    factor = rating.factors[0]

    assert factor.multiplier == Decimal("1.25")
    assert factor.premium_before_pence * factor.multiplier == factor.premium_after_pence

    rendered = json.loads(rating.model_dump_json())["factors"][0]
    assert rendered["multiplier"] == "1.25"
    assert rendered["premium_after_pence"] == "277875"


def test_decision_serialises_by_name_not_as_an_integer():
    rating = RatingRead.model_validate(STORED_RATING)

    # An IntEnum would render as 1, which is opaque and order-dependent (RATING_SPEC D7).
    assert json.loads(rating.model_dump_json())["decision"] == "REFER"


# --- write schemas ------------------------------------------------------------------------


def test_a_pasted_submission_needs_raw_input():
    with pytest.raises(ValueError, match="pasted submissions must carry raw_input"):
        SubmissionCreate(input_mode=InputMode.PASTE)


def test_a_pdf_upload_carries_no_text_until_it_is_extracted():
    created = SubmissionCreate(input_mode=InputMode.PDF_UPLOAD)

    assert (created.raw_input, created.application) == (None, None)


def test_a_form_submission_needs_an_application():
    with pytest.raises(ValueError, match="form submissions must carry an application"):
        SubmissionCreate(input_mode=InputMode.FORM)


def test_a_form_submission_carries_its_application_instead_of_text():
    created = SubmissionCreate(input_mode=InputMode.FORM, application=extracted())

    assert created.raw_input is None
    assert created.application.to_domain().months_trading == 36


def test_an_unknown_decision_name_is_a_validation_error_not_a_keyerror():
    # Decision["APPROVE"] would raise KeyError, which pydantic does not translate.
    with pytest.raises(ValidationError):
        RatingRead.model_validate({**STORED_RATING, "decision": "APPROVE"})
