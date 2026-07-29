import json
import os
import urllib.request

TIMEOUT_SECONDS = 15


def handler(event, context):
    # The sweep runs API-side because Postgres lives inside the box's Compose network and is not
    # reachable from Lambda; this holds the schedule, not the logic. See DECISIONS D-031.
    url = os.environ["UNDERWRITE_API_URL"].rstrip("/") + "/api/internal/quotes/expire"
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

    print(f"expired {result['expired']} quote(s) on {result['swept_on']}: {result['quote_refs']}")
    return result


if __name__ == "__main__":
    # `make expiry-lambda-test`: a zip Lambda with no dependencies runs anywhere python3 does.
    handler({}, None)
