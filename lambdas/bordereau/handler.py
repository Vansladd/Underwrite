import json
import os
import urllib.request

TIMEOUT_SECONDS = 60

_TOKEN = None


def _token():
    # Env first, so the make targets and `python3 handler.py` need no AWS call and no boto3.
    from_env = os.environ.get("SWEEPER_TOKEN")
    if from_env:
        return from_env

    global _TOKEN
    if _TOKEN is None:
        import boto3  # in the managed runtime, so the zip still packages no dependencies

        name = os.environ["SWEEPER_TOKEN_PARAM"]
        parameter = boto3.client("ssm").get_parameter(Name=name, WithDecryption=True)
        # Held for the container's life: a rotated parameter lands on the next cold start.
        _TOKEN = parameter["Parameter"]["Value"]
    return _TOKEN



def handler(event, context):
    # The API builds and stores the CSV because Postgres is unreachable from Lambda; this holds
    # the schedule. See DECISIONS D-031/D-032.
    #
    # "latest" rather than a month computed here: this clock is UTC and the period is a
    # Europe/London month, so any date arithmetic at this end is wrong for an hour each BST 1st —
    # silently, since the wrong month exports fine. An explicit YYYY-MM in the event backfills.
    period = event.get("period") or "latest"
    url = os.environ["UNDERWRITE_API_URL"].rstrip("/") + f"/api/internal/bordereaux/{period}"
    request = urllib.request.Request(
        url,
        data=b"",
        method="POST",
        headers={
            "X-Sweeper-Token": _token(),
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
