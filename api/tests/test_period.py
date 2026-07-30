import ast
import sys
from datetime import UTC, date, datetime
from pathlib import Path

import pytest

from app.domain import period
from app.domain.period import InvalidPeriod, YearMonth


def utc(text: str) -> datetime:
    return datetime.fromisoformat(text).replace(tzinfo=UTC)


def test_parses_a_well_formed_period():
    assert YearMonth.parse("2026-07") == YearMonth(2026, 7)


@pytest.mark.parametrize("raw", ["2026-7", "26-07", "2026-13", "2026", "2026-07-01", "", "abcd-ef"])
def test_rejects_a_malformed_period(raw):
    with pytest.raises(InvalidPeriod):
        YearMonth.parse(raw)


def test_str_round_trips_through_parse():
    assert YearMonth.parse(str(YearMonth(2026, 1))) == YearMonth(2026, 1)


def test_before_a_january_day_is_the_previous_december():
    # The wrap is where an off-by-one lands: a run on 1 January reports the old year.
    assert YearMonth.before(date(2026, 1, 1)) == YearMonth(2025, 12)


def test_before_is_the_month_a_first_of_the_month_run_should_report():
    assert YearMonth.before(date(2026, 8, 1)) == YearMonth(2026, 7)


def test_next_wraps_the_year():
    assert YearMonth(2026, 12).next() == YearMonth(2027, 1)


def test_a_summer_month_is_bounded_in_bst_not_utc():
    # July starts at 00:00 London = 23:00 UTC on 30 June. UTC boundaries misfile that hour.
    start, end = YearMonth(2026, 7).bounds()

    assert start == utc("2026-06-30T23:00:00")
    assert end == utc("2026-07-31T23:00:00")


def test_a_winter_month_is_bounded_at_utc_midnight():
    start, end = YearMonth(2026, 1).bounds()

    assert start == utc("2026-01-01T00:00:00")
    assert end == utc("2026-02-01T00:00:00")


def test_months_order_chronologically_across_a_year_boundary():
    assert YearMonth(2025, 12) < YearMonth(2026, 1)


@pytest.mark.parametrize("month", [0, 13, -1])
def test_rejects_an_impossible_month(month):
    with pytest.raises(InvalidPeriod):
        YearMonth(2026, month)


def test_the_domain_package_imports_only_stdlib():
    """Models and schemas depend on `app.domain`, never the reverse."""
    offenders = {}
    for path in sorted(Path(period.__file__).parent.glob("*.py")):
        for node in ast.walk(ast.parse(path.read_text())):
            if isinstance(node, ast.Import):
                names = [alias.name for alias in node.names]
            elif isinstance(node, ast.ImportFrom) and node.module and node.level == 0:
                names = [node.module]
            else:
                continue
            # Siblings are the point of a domain package; anything else is a dependency inversion.
            impure = {
                n
                for n in names
                if not n.startswith("app.domain") and n.split(".")[0] not in sys.stdlib_module_names
            }
            if impure:
                offenders.setdefault(path.name, set()).update(impure)

    assert not offenders, f"app/domain must import only stdlib, found: {offenders}"


def test_the_last_closed_month_is_the_one_before_the_current_one():
    # The invariant that makes /bordereaux/latest correct without freezing the clock.
    assert YearMonth.last_closed().next() == YearMonth.current()


def test_the_current_month_is_read_in_the_reporting_zone():
    # date.today() is UTC; between 00:00 and 01:00 BST on the 1st the two name different months.
    assert YearMonth.current() == YearMonth.containing(datetime.now(period.REPORTING_ZONE).date())
