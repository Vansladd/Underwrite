import json
import os
import urllib.request

TIMEOUT_SECONDS = 15

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
    # The sweep runs API-side because Postgres lives inside the box's Compose network and is not
    # reachable from Lambda; this holds the schedule, not the logic. See DECISIONS D-031.
    url = os.environ["UNDERWRITE_API_URL"].rstrip("/") + "/api/internal/quotes/expire"
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

    print(f"expired {result['expired']} quote(s) on {result['swept_on']}: {result['quote_refs']}")
    return result


if __name__ == "__main__":
    # `make expiry-lambda-test`: a zip Lambda with no dependencies runs anywhere python3 does.
    handler({}, None)
