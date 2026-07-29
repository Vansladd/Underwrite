import csv
import io
from datetime import UTC, date, datetime, timedelta

import pytest
from sqlalchemy import select

from app.domain.enums import (
    AuditActor,
    AuditEventType,
    CompanyStatus,
    DataVolume,
    QuoteStatus,
    RequestedLimit,
    Sector,
    SubmissionStatus,
)
from app.domain.period import YearMonth
from app.models import AuditEvent, Enrichment, Extraction, Quote, Rating, Submission
from app.schemas import rating_to_orm_kwargs
from app.services.bordereau import COLUMNS, build_csv, export_bordereau, storage_key
from app.services.rating import rate
from tests.factories import make_submission
from tests.fakes import FakeStorage
from tests.rating_baseline import CLEAN_ENRICHMENT, application

JULY = YearMonth(2026, 7)


def utc(text: str) -> datetime:
    return datetime.fromisoformat(text).replace(tzinfo=UTC)


async def make_quoted(db, *, created_at: datetime, ref: str, **overrides):
    """A submission with the full relation set, whose quote was issued at `created_at`."""
    submission = await make_submission(db, status=SubmissionStatus.QUOTED)
    db.add_all(
        [
            Extraction(
                submission_id=submission.id,
                company_name=overrides.get("company_name", "Ledgerline Capital Ltd"),
                company_number=overrides.get("company_number", "SC123456"),
                sector=Sector.FINTECH,
                annual_revenue_pence=420_000_000,
                months_trading=60,
                prior_claims_count=0,
                data_records_held=DataVolume.OVER_1M,
                requested_limit=RequestedLimit.GBP_2M,
                extraction_confidence=0.9,
                missing_fields=[],
                model="claude-sonnet-5",
            ),
            Enrichment(
                submission_id=submission.id,
                ch_found=True,
                ch_company_number=overrides.get("ch_company_number", "SC654321"),
                ch_company_name="LEDGERLINE HOLDINGS LIMITED",
                ch_company_status=CompanyStatus.ACTIVE,
                ch_date_of_creation=date(2021, 7, 23),
                ch_name_match_score=0.75,
                sic_codes=overrides.get("sic_codes", ["64191", "64999"]),
                discrepancies=[],
            ),
            Rating(
                submission_id=submission.id,
                **rating_to_orm_kwargs(rate(application(), CLEAN_ENRICHMENT)),
            ),
            Quote(
                submission_id=submission.id,
                quote_ref=ref,
                created_at=created_at,
                limit_pence=200_000_000,
                excess_pence=250_000,
                gross_premium_pence=806_000,
                inception_date=date(2026, 7, 15),
                valid_until=date(2026, 8, 14),
            ),
        ]
    )
    await db.flush()
    return submission


def rows_of(body: bytes) -> list[dict[str, str]]:
    return list(csv.DictReader(io.StringIO(body.decode())))


# --- period selection ---


async def test_a_quote_issued_inside_the_period_is_reported(db):
    await make_quoted(db, created_at=utc("2026-07-15T12:00:00"), ref="Q-2026-AAAAAA")

    run = await export_bordereau(db, FakeStorage(), period=JULY)

    assert run.quotes == 1


async def test_a_quote_issued_in_another_month_is_not_reported(db):
    await make_quoted(db, created_at=utc("2026-08-15T12:00:00"), ref="Q-2026-BBBBBB")

    assert (await export_bordereau(db, FakeStorage(), period=JULY)).quotes == 0


async def test_the_first_instant_of_a_bst_month_belongs_to_that_month(db):
    # 23:30 UTC on 30 June is 00:30 on 1 July in London. UTC bounds would file this under June.
    await make_quoted(db, created_at=utc("2026-06-30T23:30:00"), ref="Q-2026-CCCCCC")

    storage = FakeStorage()
    run = await export_bordereau(db, storage, period=JULY)

    assert run.quotes == 1
    assert rows_of(storage.read(storage_key(JULY)))[0]["quote_ref"] == "Q-2026-CCCCCC"


async def test_the_last_instant_before_a_bst_month_belongs_to_the_previous_one(db):
    # 22:30 UTC on 30 June is 23:30 on 30 June in London — still June.
    await make_quoted(db, created_at=utc("2026-06-30T22:30:00"), ref="Q-2026-DDDDDD")

    assert (await export_bordereau(db, FakeStorage(), period=JULY)).quotes == 0


async def test_the_end_of_a_bst_month_is_exclusive(db):
    # 23:00 UTC on 31 July is 00:00 on 1 August in London — the first instant of the next month.
    await make_quoted(db, created_at=utc("2026-07-31T23:00:00"), ref="Q-2026-EEEEEE")

    assert (await export_bordereau(db, FakeStorage(), period=JULY)).quotes == 0


async def test_an_expired_quote_is_still_the_months_business(db):
    # Written in July, lapsed since. A bordereau the carrier reconciles must not retract it.
    submission = await make_quoted(db, created_at=utc("2026-07-10T09:00:00"), ref="Q-2026-FFFFFF")
    quote = await db.scalar(select(Quote).where(Quote.submission_id == submission.id))
    quote.status = QuoteStatus.EXPIRED
    await db.flush()

    assert (await export_bordereau(db, FakeStorage(), period=JULY)).quotes == 1


# --- the CSV itself ---


async def test_the_csv_carries_the_agreed_columns_and_values(db):
    await make_quoted(db, created_at=utc("2026-07-15T12:00:00"), ref="Q-2026-111111")

    storage = FakeStorage()
    await export_bordereau(db, storage, period=JULY)

    body, content_type = storage.objects[storage_key(JULY)]
    (row,) = rows_of(body)
    assert content_type == "text/csv"
    assert list(row) == list(COLUMNS)
    assert row["quote_ref"] == "Q-2026-111111"
    assert row["insured_name"] == "Ledgerline Capital Ltd"
    assert row["inception_date"] == "2026-07-15"
    assert row["expiry_date"] == "2026-08-14"
    assert row["sector"] == "fintech"
    assert row["sic_codes"] == "64191 64999"
    assert row["rating_version"]


async def test_money_columns_are_bare_pounds_to_two_places(db):
    await make_quoted(db, created_at=utc("2026-07-15T12:00:00"), ref="Q-2026-222222")

    storage = FakeStorage()
    await export_bordereau(db, storage, period=JULY)

    (row,) = rows_of(storage.read(storage_key(JULY)))
    assert row["limit"] == "2000000.00"
    assert row["excess"] == "2500.00"
    assert row["gross_premium"] == "8060.00"


async def test_the_verified_register_number_is_reported_over_the_extracted_one(db):
    await make_quoted(
        db,
        created_at=utc("2026-07-15T12:00:00"),
        ref="Q-2026-333333",
        company_number="SC123456",
        ch_company_number="SC654321",
    )

    storage = FakeStorage()
    await export_bordereau(db, storage, period=JULY)

    assert rows_of(storage.read(storage_key(JULY)))[0]["company_number"] == "SC654321"


async def test_an_empty_period_still_writes_a_header_only_csv(db):
    # A month with no business is a real report, not a missing one — the carrier expects a file.
    storage = FakeStorage()

    run = await export_bordereau(db, storage, period=JULY)

    assert run.quotes == 0
    assert storage.read(storage_key(JULY)).decode() == ",".join(COLUMNS) + "\r\n"


def test_a_quote_with_no_relations_renders_empty_cells_not_a_crash():
    # Defensive: the join is left-ish in practice (a quote always has a rating), but a crash here
    # would fail the whole month's export for one bad row.
    bare = Quote(
        quote_ref="Q-2026-444444",
        limit_pence=1,
        excess_pence=0,
        gross_premium_pence=0,
        inception_date=date(2026, 7, 1),
        valid_until=date(2026, 7, 31),
        # Transient, never flushed: build_csv is pure, so this needs no database at all.
        submission=Submission(),
    )

    (row,) = rows_of(build_csv([bare]))

    assert row["insured_name"] == ""
    assert row["company_number"] == ""
    assert row["limit"] == "0.01"


# --- the audit trail ---


async def test_every_reported_submission_gets_its_own_export_event(db):
    first = await make_quoted(db, created_at=utc("2026-07-02T09:00:00"), ref="Q-2026-555555")
    second = await make_quoted(db, created_at=utc("2026-07-03T09:00:00"), ref="Q-2026-666666")

    await export_bordereau(db, FakeStorage(), period=JULY)

    events = list(
        await db.scalars(
            select(AuditEvent).where(AuditEvent.event_type == AuditEventType.BORDEREAU_EXPORTED)
        )
    )
    assert {e.submission_id for e in events} == {first.id, second.id}
    assert all(e.actor is AuditActor.SYSTEM and e.actor_id is None for e in events)
    assert events[0].payload["period"] == "2026-07"
    assert events[0].payload["s3_key"] == "bordereaux/2026-07.csv"


async def test_a_failed_upload_writes_no_audit_trail(db):
    # The object must exist before the trail claims it does; an audited export that is not there
    # is the worse lie, because nobody goes looking for it.
    await make_quoted(db, created_at=utc("2026-07-15T12:00:00"), ref="Q-2026-777777")

    with pytest.raises(RuntimeError):
        await export_bordereau(db, FakeStorage(error=RuntimeError("s3 down")), period=JULY)

    await db.rollback()
    assert (
        await db.scalars(
            select(AuditEvent).where(AuditEvent.event_type == AuditEventType.BORDEREAU_EXPORTED)
        )
    ).all() == []


# --- the endpoint ---


async def test_the_export_endpoint_reports_the_key_and_count(anon_api, db, sweeper_token, storage):
    # Relative to today, not a literal: the only period the endpoint accepts is a closed one.
    closed = YearMonth.before(date.today())
    start, _ = closed.bounds()
    await make_quoted(db, created_at=start + timedelta(days=1), ref="Q-2026-888888")

    response = await anon_api.post(
        f"/api/internal/bordereaux/{closed}", headers={"X-Sweeper-Token": sweeper_token}
    )

    assert response.status_code == 200
    body = response.json()
    assert body["period"] == str(closed)
    assert body["s3_key"] == f"bordereaux/{closed}.csv"
    assert body["quotes"] == 1
    assert body["size_bytes"] == len(storage.read(f"bordereaux/{closed}.csv"))


async def test_the_export_endpoint_refuses_a_month_that_has_not_closed(
    anon_api, sweeper_token, storage
):
    this_month = date.today().strftime("%Y-%m")

    response = await anon_api.post(
        f"/api/internal/bordereaux/{this_month}", headers={"X-Sweeper-Token": sweeper_token}
    )

    assert response.status_code == 422
    assert storage.objects == {}


async def test_the_export_endpoint_refuses_a_future_month(anon_api, sweeper_token, storage):
    later = date.today().replace(day=1) + timedelta(days=62)

    response = await anon_api.post(
        f"/api/internal/bordereaux/{later:%Y-%m}", headers={"X-Sweeper-Token": sweeper_token}
    )

    assert response.status_code == 422


async def test_the_export_endpoint_refuses_a_malformed_period(anon_api, sweeper_token, storage):
    response = await anon_api.post(
        "/api/internal/bordereaux/July-2026", headers={"X-Sweeper-Token": sweeper_token}
    )

    assert response.status_code == 422


async def test_the_export_endpoint_needs_the_machine_token(anon_api, storage, sweeper_token):
    assert (await anon_api.post("/api/internal/bordereaux/2026-07")).status_code == 401
