import json
import os
import urllib.request
from datetime import date, timedelta

TIMEOUT_SECONDS = 60


def previous_month(today: date) -> str:
    return f"{today.replace(day=1) - timedelta(days=1):%Y-%m}"


def handler(event, context):
    # The API builds and stores the CSV because Postgres is unreachable from Lambda; this holds
    # the schedule. See DECISIONS D-031/D-032.
    #
    # date.today() is UTC here, while the period is a Europe/London month — safe only because the
    # schedule fires at 03:00, when both are on the same calendar day. Moving it before 01:00 would
    # report the wrong month every summer. An explicit `period` in the event backfills.
    period = event.get("period") or previous_month(date.today())
    url = os.environ["UNDERWRITE_API_URL"].rstrip("/") + f"/api/internal/bordereaux/{period}"
    request = urllib.request.Request(
        url,
        data=b"",
        method="POST",
        headers={
            "X-Sweeper-Token": os.environ["SWEEPER_TOKEN"],
            "Accept": "application/json",
        },
    )
    # Unhandled by design: a raised HTTPError fails the invocation, which is what Scheduler retries.
    with urllib.request.urlopen(request, timeout=TIMEOUT_SECONDS) as response:
        result = json.load(response)

    print(f"bordereau {result['period']}: {result['quotes']} quote(s) -> {result['s3_key']}")
    return result


if __name__ == "__main__":
    # `make bordereau-lambda-test`: a zip Lambda with no dependencies runs anywhere python3 does.
    handler({"period": os.environ.get("PERIOD", "")}, None)
