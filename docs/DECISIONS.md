# Engineering decisions

Running log of non-obvious technical choices. Domain and pricing decisions live in
`RATING_SPEC.md`.

---

## D-001 · Python 3.13 everywhere

**Ticket:** UW-002 · **Date:** 2026-07-21

`requires-python = ">=3.13,<3.14"` with a `.python-version` pin, rather than an open
`>=3.13`.

Left open, `uv lock` resolved against CPython 3.14 while the container runs 3.13 — a silent
mismatch between the lockfile and the runtime. The upper bound also keeps the API on the same
minor version as the PDF Lambda's base image, `public.ecr.aws/lambda/python:3.13`. That image is
constrained: the `python:3.10`/`3.11` Lambda images are Amazon Linux 2 and ship Pango 1.42,
while WeasyPrint 69 requires Pango ≥ 1.44, so only the AL2023-based 3.12+ images can render PDFs
at all.

One Python version across API, Lambdas, and local dev.

---

## D-002 · Staying on `httpx`, not `httpx2`

**Ticket:** UW-002 · **Date:** 2026-07-21 · **Revisit:** when respx ships httpx2 support

Starlette 1.2+ prefers `httpx2` for `TestClient` and warns when only `httpx` is present.
The warning is legitimate: `httpx` has had no stable release since 0.28.1 (Dec 2024), and on
2026-02-27 the maintainer closed all issues and discussions. `httpx2` is a rename-fork
maintained by Pydantic Services, API-compatible, currently 2.7.0.

**We are staying on `httpx` anyway**, because the mocking ecosystem hasn't followed:

- `respx` does **not** support httpx2 — issues [#316](https://github.com/lundberg/respx/issues/316)
  and [#324](https://github.com/lundberg/respx/issues/324) are open with no maintainer position.
- The bridge, `pytest-httpx2`, is at 1.0.0 with 3 commits and ~0.5% of `pytest-httpx`'s
  download volume.

UW-022's Companies House client is tested through respx at the transport layer specifically to
cover 404, 429 rate-limit headers, and payloads with `sic_codes` absent. Betting that suite on
a 3-commit package trades a cosmetic warning for real fragility.

**Mitigations:**
- The warning is filtered by exact message in `pyproject.toml`, not blanket-suppressed, and
  `filterwarnings = ["error", ...]` makes every *other* warning fail the build.
- All Companies House calls sit behind a `CompaniesHouseClient` service class, so switching to
  httpx2 is a one-file change plus a mocking-library swap.

**Note if this is revisited:** httpx2 2.3.0 replaced `certifi` with `truststore`, so TLS
verification uses the OS trust store — slim/distroless images then need `ca-certificates`
installed or outbound HTTPS fails.

---

## D-003 · Postgres published on host port 55432

**Ticket:** UW-002 · **Date:** 2026-07-21

Default host port is `55432`, not `5432`. Port 5432 was already held by another project's
container on the dev machine, and 5433/54322 by two more. Inside the compose network the port
is always 5432, so only the published port differs. Override with `POSTGRES_PORT`.

Defaulting to a port nobody else takes means `make up` works on a machine that already runs
other stacks — which is the normal case, not the exception.

---

## D-004 · Rating goldens are regenerated deliberately, never automatically

**Ticket:** UW-011b · **Date:** 2026-07-21

`tests/goldens/rating_v1_0.json` freezes the full `RatingResult` for 32 representative risks.
It only rewrites under `make regen-goldens`, and the test asserts the file's `rating_version`
matches `RATING_VERSION` before comparing.

A golden file that self-heals is worse than no golden file: the diff is the deliverable. A
factor change should arrive in review as "these 11 risks moved, this one flipped to REFER",
which is a question a human can answer. Auto-regeneration turns that into a green tick.

Multipliers and running premiums serialise as **strings**. `json.dumps` refuses `Decimal`, and
the reflex fix — `float(...)` — puts a float in the money path against D6 and stops the stored
trace folding back to the premium. The same constraint applies to the `factors` JSONB column
in UW-012.
