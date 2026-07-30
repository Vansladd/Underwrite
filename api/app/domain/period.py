from dataclasses import dataclass
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

# A bordereau reports a calendar month as the business keeps it, not as UTC happens to slice it.
REPORTING_ZONE = ZoneInfo("Europe/London")


class InvalidPeriod(ValueError):
    pass


def today() -> date:
    """The reporting zone's date. `date.today()` is UTC, which lags London for an hour each BST day
    and so names the wrong month between midnight and 01:00 on the 1st."""
    return datetime.now(REPORTING_ZONE).date()


# order=True compares fields in order, so chronology depends on year being declared first.
@dataclass(frozen=True, order=True)
class YearMonth:
    year: int
    month: int

    def __post_init__(self) -> None:
        if not 1 <= self.month <= 12:
            raise InvalidPeriod(f"month must be 1-12, got {self.month}")
        if not 1970 <= self.year <= 9999:
            raise InvalidPeriod(f"year out of range: {self.year}")

    @classmethod
    def parse(cls, raw: str) -> "YearMonth":
        year, _, month = raw.partition("-")
        if len(year) != 4 or len(month) != 2 or not (year.isdigit() and month.isdigit()):
            raise InvalidPeriod(f"period must be YYYY-MM, got {raw!r}")
        return cls(int(year), int(month))

    @classmethod
    def containing(cls, day: date) -> "YearMonth":
        return cls(day.year, day.month)

    @classmethod
    def before(cls, day: date) -> "YearMonth":
        """The month preceding `day`'s — what a run on the 1st should report."""
        return cls.containing(day.replace(day=1) - timedelta(days=1))

    @classmethod
    def current(cls) -> "YearMonth":
        return cls.containing(today())

    @classmethod
    def last_closed(cls) -> "YearMonth":
        """The most recent month that has finished — the one a scheduled export should file."""
        return cls.before(today())

    def __str__(self) -> str:
        return f"{self.year:04d}-{self.month:02d}"

    def next(self) -> "YearMonth":
        return YearMonth(self.year + self.month // 12, self.month % 12 + 1)

    def bounds(self) -> tuple[datetime, datetime]:
        """Half-open [start, end) as aware instants — UTC boundaries misfile an hour under BST."""
        return self._first_instant(), self.next()._first_instant()

    def _first_instant(self) -> datetime:
        return datetime(self.year, self.month, 1, tzinfo=REPORTING_ZONE)
