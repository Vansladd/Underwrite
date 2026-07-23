# Engineering decisions

Running log of non-obvious technical choices. Domain and pricing decisions live in
`RATING_SPEC.md`.

---

## D-027 · Operator-console visual system — refined desk, copper accent, token-swap themes

**Ticket:** console redesign · **Date:** 2026-07-23

The frontend gets a committed visual system, captured in root **`PRODUCT.md`** (register: product) and
**`DESIGN.md`** (tokens), with the shaping process in `design/`. Direction: a **refined product desk**
(Linear/Stripe-dashboard register) — crisp cool-neutral canvas, quiet 1px structure, one warm
**copper** accent, IBM Plex Sans + Mono, shipping **light and dark**.

**Themes are a pure token swap.** Every colour is a CSS variable; Tailwind v4 `@theme inline` maps
`--color-*` onto them so utilities (`bg-surface`, `text-ink-muted`) resolve live. `:root` holds light;
`@media (prefers-color-scheme: dark) :root:not([data-theme=light])` follows the OS; `:root[data-theme]`
lets the toggle override either way. An inline `<head>` script stamps `data-theme` before first paint,
so there is no light/dark flash. No per-component `dark:` classes. Fonts self-host via `@fontsource`
(offline-safe, matches the clone-and-run ethos).

**Copper is interaction and identity only; amber is the `referred` status.** Named Rule 1 —
different hue (47 vs 85), different treatment (copper = saturated solid/underline; amber = soft pill),
so the brand accent never reads as a status. Numbers are mono + tabular everywhere (premium, score,
company number, time). Status is a dot + word pill; the row stays neutral (no row-fills, no
side-stripes). Signals never rely on colour alone (status = dot+word; discrepancy = red + ▲ + label).

**The queue row defends its own decision** — the upgrade over a plain list. A read-only
`SubmissionListItem` flattens what the operator scans before opening a row: company, sector, revenue,
limit, number, premium, decision, and a **one-line `headline`** derived server-side from the rating's
first refer/decline reason (or the first missing field, humanised). The list endpoint eager-loads
extraction+rating+enrichment and maps to it; the detail endpoint is unchanged. So each row previews
the machine's reason in the status hue, making the deterministic-pricing thesis visible at the queue
level. The detail drawer (the extracted-vs-CH + factor-ladder centrepiece) is mocked in
`design/operator-console/mockups/drawer.html` and lands with UW-035.

---

## D-026 · Operator identity — session cookie, Argon2id, and the money paths behind login

**Ticket:** UW-019 · **Date:** 2026-07-23 · **Supersedes:** D-012 (applicant-anonymous)

The single shared Basic credential (`ops`/`changeme`) is gone, replaced by a `users` table
(Argon2id via `argon2-cffi`), a **signed-cookie session** (Starlette `SessionMiddleware` +
`itsdangerous`, `HttpOnly` + `SameSite=Lax`, `Secure` in prod), and a `CurrentUser` dependency.
Revocation is a `SECRET_KEY` rotation; a sessions table is the upgrade path if logout-everywhere is
ever needed. Not a hosted IdP (the demo must run with no external network), not JWT (no refresh
dance), not `fastapi-users` (registration/verification/reset/OAuth we don't have, and it constrains
the `User` shape `actor_id` points at).

**The money paths moved behind the login — this supersedes D-012.** D-012 let applicants
`POST /api/submissions` and read a submission by UUID capability with no account. But an
unauthenticated POST burns Anthropic credit and the Companies House key, so the cost boundary wins:
POST, the detail GET, the queue, and `/api/documents` all now require `CurrentUser`. Only `/health`,
`/api/auth/login`, `/api/auth/logout`, and the OpenAPI/docs routes are public. A **structural test**
(`test_route_gating.py`) fails if any route is neither classified public nor gated — "no code path
skips authentication" is enforced, not asserted per-route. The shared credential is deleted, not
left as a second way in.

**The deployed URL has proper auth, not a public password.** The seeded operator's password is a
setting (`SEED_OPERATOR_PASSWORD`): the local default `underwrite-demo` keeps `make up && make seed`
instantly usable, but `.env.prod` sets a **strong secret** shared with reviewers privately — never a
`DEMO_MODE` bypass (one env var from an open admin panel), never a README-published password on the
public box. `seed_operator` **upserts** (re-hashes on reseed) so the operator always tracks the
configured secret; a lifespan guard warns loudly if a `session_secure` (prod) deployment still runs
the public default. Login is constant-time — a username miss verifies a dummy hash so it is not
timing-distinguishable from a wrong password.

**Attribution is wired now, asserted at #34.** `audit_events.actor_id` (nullable FK → `users`,
`ON DELETE RESTRICT` per D-007) and a `record_event(actor_id=…)` param exist and round-trip in a
test, but this ticket writes no operator-attributed events — approve/decline is the first ops action
(UW-034), so "the trail names the underwriter" is proven there, not here. Existing pipeline /
`submission_received` events stay `system`/`applicant` with a null `actor_id`.

---

## D-025 · Frontend scaffold — same-origin proxy, generated types, containerised dev

**Ticket:** UW-030 · **Date:** 2026-07-22

The operator UI is Vite 8 + React 18 + TS + Tailwind v4 + TanStack Query 5 in `web/`, talking to a
**typed** `openapi-fetch` client whose types are generated by `openapi-typescript` from the live
`/api/openapi.json` — never hand-written. A wrong field name or param fails `tsc`, not production.

**No CORS, in dev or prod.** Prod already serves same-origin: Caddy serves the static bundle and
reverse-proxies `/api/*` to the API. Dev mirrors that with a **Vite proxy** (`/api` → `http://api:8000`),
so the browser only ever calls same-origin `/api/...` and the FastAPI app needs no CORS middleware —
one fewer thing to misconfigure into an open cross-origin surface.

**Generated types are committed.** `src/api/schema.d.ts` is checked in (with a "do not edit" header)
so a fresh clone and CI `build` need no running API; `make web-types` regenerates it against the dev
API when the schema changes. Reproducibility over purity.

**Dev runs in a container, on `node:22-slim`.** A `web` compose service keeps the "docker + make is
all you need" story — a stranger clones, `make up`, `make seed`, and gets the dashboard with no host
Node. Debian slim (glibc), not alpine (musl), so the one committed `package-lock.json` satisfies
`npm ci` in both the container and the glibc CI runner; a macOS-generated lockfile omits the linux
native optionals (`@emnapi/*`) and breaks `npm ci` — the lockfile is generated on linux glibc. A
named volume holds `/app/node_modules` so the source bind-mount doesn't hide the installed deps.

**Basic-auth in the client is deliberately interim.** `GET /api/submissions` is HTTP Basic
(`ops`/`changeme`) today; the client attaches it via one openapi-fetch middleware from Vite env vars.
**#31b (UW-019) replaces it** with the real cookie session — this scaffold is the shell it hangs off,
not the auth story. A dev-only `openapi-typescript` transitive advisory (`js-yaml` under
`@redocly/openapi-core`) is left unpatched: it runs only at type-gen time, never in the bundle or CI
output, and the only fix is a breaking major bump.

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

---

## D-005 · Native enums store member *values* — except the two IntEnums

**Ticket:** UW-012 · **Date:** 2026-07-21

SQLAlchemy's `Enum` persists the member **name** by default. For a `StrEnum` written as
`SAAS = "saas"` that means `'SAAS'` on disk, so `WHERE sector = 'saas'` matches nothing, seed
files disagree with the API, and nothing raises — it is a silent data bug, not a crash.

Every `StrEnum` column therefore goes through `pg_enum()`, which sets
`values_callable=lambda cls: [m.value for m in cls]`. A test reads the raw column back with
`::text` and asserts the literal, because the failure is invisible from Python.

Two columns deliberately store names, via `pg_enum_by_name()`:

- **`Decision`** — D7 in `RATING_SPEC.md` requires `'DECLINE'` on disk so that reordering the
  `IntEnum` cannot silently reinterpret historical rows.
- **`RequestedLimit`** — its values are integers, which a Postgres enum cannot hold.

## D-006 · `RequestedLimit`'s integer value is pounds, not pence

**Ticket:** UW-012 · **Date:** 2026-07-21

D6 makes integer money pence everywhere. `RequestedLimit.GBP_250K = 250_000` is the single
exception: it is a **label**, chosen so the enum renders directly (`£250,000 limit`), and it is
never arithmetic in the money path.

`Quote.limit_pence` holds the actual money. A `.pence` property exists for the one conversion
anyone should ever need, so nobody reaches for `limit * 100` at a call site and nobody assumes
the raw value is already pence.

## D-007 · The audit trail is append-only at the database, not by convention

**Ticket:** UW-012 · **Date:** 2026-07-21

`audit_events.submission_id` is `ON DELETE RESTRICT`, while the four component tables are
`ON DELETE CASCADE`. Deleting a submission that has history is refused by Postgres.

UW-016 already states the model exposes no update or delete path. That is a promise about
code; this is a property of the schema. An append-only trail that a stray `DELETE` can erase
is not an audit trail, and the regulatory value of the whole feature rests on that.

---

## D-008 · The migration DSN comes from Settings, and downgrade drops the enum types

**Ticket:** UW-013 · **Date:** 2026-07-21

`alembic.ini` ships with `sqlalchemy.url` **empty**. `migrations/env.py` fills it from
`Settings` only when no caller has set one, so there is a single source of truth for the DSN,
no credentials in a committed ini, and the tests can still point a run at a scratch database.
Setting it unconditionally is the obvious version of this and it is wrong — it silently
overrode the test URL and ran the suite's migration against the dev database.

**`DROP TABLE` does not drop the enum types the table used.** Verified in psql: create a type,
create a table using it, drop the table, and the type is still there. Alembic's autogenerated
`downgrade()` emits only `op.drop_table`, so all ten enum types survive and the next
`upgrade head` fails with `type "sector" already exists`. `0001` therefore ends its downgrade
with an explicit `sa.Enum(name=...).drop()` per type, and `test_downgrade_leaves_no_tables_and_
no_enum_types` fails if that loop is removed.

**Two settings that are off by default and matter here:** `compare_type` and
`compare_server_default`. Without the second, autogenerate does not notice a changed
`server_default` — and five columns depend on one.

**Tests run migrations, not `Base.metadata.create_all`.** Otherwise nothing in the suite ever
executes `0001` and it is free to drift. `alembic check` runs as a test, so adding a mapped
column without a migration fails CI by name.

**When a later migration reuses an existing enum**, pass
`postgresql.ENUM(..., create_type=False)` or it will try to `CREATE TYPE` a second time.
`ALTER TYPE ... ADD VALUE` has its own transaction rules. Neither applies to an initial
migration; both will apply around UW-020.

---

## D-009 · The extraction schema speaks broker units; one function converts

**Ticket:** UW-014 · **Date:** 2026-07-21

`ExtractedApplication` carries `annual_revenue_gbp` and `years_trading`, not pence and months.
It is the `messages.parse()` output format, and a rambling broker email says "£750k, trading
about three years" — asking the model to emit pence is asking it to do arithmetic it has no
reason to get right. `RATING_SPEC` D5 already fixed the direction: convert once, at the schema
boundary, and never compare the float again.

Conversion goes through `Decimal(str(value))`, never the float:

```
int(8.7 * 100)  = 869      to_pence(8.7)  = 870
int(0.29 * 100) = 28       to_pence(0.29) = 29
```

Rounding is `ROUND_HALF_UP`, matching §4. Python's `round()` is half-even, so it would disagree
with the rating engine on exact halves.

**`to_domain()` raises `IncompleteExtraction` rather than substituting.** The never-guess rule
produces nulls, but `Application` requires every rated field. Defaulting a missing revenue to
zero would price the risk in the 0.8 band and bury that decision in a converter. What an
unratable submission becomes — failed, or referred to a human — is UW-025's call.

**`Decision` serialises by name.** It is an `IntEnum`, so the default would render `1`, which is
opaque to a reader and reintroduces the ordering dependency D7 stores the name to avoid.
Decimals serialise as strings for the same reason they are stored as strings (D-004): a JSON
number is a double again by the time it reaches the browser.

---

## D-010 · Audit payloads are coerced, never rejected

**Ticket:** UW-016 · **Date:** 2026-07-21

JSONB serialises at **flush**, not at construction. Verified against a real database, one
savepoint per case: `Decimal`, `datetime`, `date`, `UUID`, dataclasses, `RatingResult`, `set`
and tuple-valued dict keys all raise `StatementError: TypeError … not JSON serializable`.
`StrEnum` and `IntEnum` survive only because they subclass `str` and `int`.

So the obvious call — `record_event(..., {"output": rating_result})` — raises at flush and
poisons the transaction, **rolling back the rating it was recording**. An audit trail that can
destroy the thing it documents is worse than no audit trail, and the traceback points at the
commit rather than at the payload.

`jsonable()` is therefore total: it coerces what it knows and falls back to `repr()` for
everything else. Losing fidelity on an exotic object is acceptable; losing an approved quote
because its audit payload held a `Decimal` is not. A genuine foreign-key error still raises —
that is a programming error, not a payload problem.

**Enum checks come before the primitive check.** `Decision` is an `IntEnum`, so
`isinstance(value, int)` matches first and writes `0` — exactly the integer that D7 stores the
name to avoid. This was caught by reading the serialised output, not by a test that already
existed.

**Append-only is enforced by `before_update` and `before_delete` listeners** that raise. The
`ON DELETE RESTRICT` from UW-012 only stops a submission from taking its history with it;
nothing stopped `session.delete(event)`.

They live in `app/models/audit_event.py`, not the service. Registered in the service they were
a side effect of importing it: with only `app.models` imported the mapper had **zero**
`before_delete` listeners, so the sweeper and bordereau Lambdas — which import models and never
touch `app.services` — would have deleted freely.

**Migration `0002` adds two triggers** (UW-018), because the listeners are ORM-only — mapper
events do not fire for Core or raw SQL, so `session.execute(update(...))` and anything a Lambda
writes with `text()` bypassed them entirely.

Two, not one: a `FOR EACH ROW` trigger does **not** fire for `TRUNCATE`. The first version of
this migration blocked `UPDATE` and `DELETE` while `truncate audit_events` emptied the table and
reported success — and `truncate submissions cascade` did the same through the `ON DELETE
RESTRICT` foreign key, which does not apply to TRUNCATE. Both defences fell to one statement,
and `make seed` (#30) is required to be idempotent, so project code was the likely first caller.
A `BEFORE TRUNCATE ... FOR EACH STATEMENT` trigger covers it.

A trigger rather than `REVOKE UPDATE, DELETE`: dev and CI connect as `underwrite`, and
`select usesuper` confirms it is a superuser, who bypasses privilege checks. A revoke would
pass a test written against a lesser role and do nothing where we actually run. It becomes the
right second layer once #15–16 provisions a non-owner application role.

The ORM listeners stay. They fire before the flush reaches Postgres, so a developer using the
session still gets `AuditTrailIsAppendOnly` rather than a SQLSTATE — asserted.

**Any migration that must touch `audit_events` has to disable the triggers first**
(`alter table audit_events disable trigger user`, re-enabled after). Repairing payloads written
before a serialisation fix is a real prospect — D-010 has needed two already — and without this
the migration aborts `alembic upgrade head` partway through a deploy.

**This is defence-in-depth, not tamper-proofing.** The table owner can
`ALTER TABLE audit_events DISABLE TRIGGER audit_events_append_only`, and a superuser can drop
it. It stops accidents, bugs and casual `UPDATE`s, not a determined operator with owner rights.
Real tamper-evidence would need hash chaining or append-only storage, which is out of scope.

**Two things that reach JSONB and must not.** `bytes` satisfies `Sequence`, so a 2MB PDF would
serialise as two million integers — they are summarised instead. And Postgres rejects `\u0000`
inside a jsonb string with `UntranslatableCharacterError`, so NUL is escaped in every string;
`bytes(16)` decodes as valid UTF-8 and would otherwise have failed the flush.

**Not addressed:** payloads carry raw broker emails and Companies House data — personal data in
an append-only store with no redaction path. It belongs in the README's design decisions.

---

## D-011 · Row timestamps use `clock_timestamp()`, and listings break ties on `id`

**Ticket:** UW-015 · **Date:** 2026-07-21

D-010 fixed `audit_events.occurred_at` and stopped there. Every other `created_at` kept
`now()`, which is the **transaction** timestamp — so three submissions written in one
transaction get **one distinct value between them**, measured. `make seed` (#30) inserts six in
one transaction, so the ops queue (#32) would have rendered them in planner order.

Migration `0003` moves all six timestamp columns to `clock_timestamp()`. `written_at` is now
the single annotated type for "when this row was written"; `event_at` was an identical
definition under a second name.

**The ordering test was vacuous and hid this.** It compared a list of identical timestamps
against its own sort, which is trivially true — deleting `ORDER BY` entirely left the whole
route suite green. It now asserts identity against creation order, and fails without the clause.

**Listings order by `(created_at desc, id desc)`.** A tiebreaker matters because `LIMIT`/`OFFSET`
over an unstable sort can repeat or skip rows between pages. That one is asserted **structurally**
— against the compiled SQL — because Postgres happens to return tied rows in a stable order at
this size, so a behavioural test passes with or without the tiebreaker and proves nothing.

---

## D-013 · The state bucket is created by hand; locking is native S3

**Ticket:** UW-060 · **Date:** 2026-07-21

Terraform cannot provision the bucket holding its own state, so `underwrite-tfstate` is five
CLI calls — create, versioning, public-access block, encryption, lifecycle — kept in
`infra/bootstrap.sh` and idempotent, because a bootstrap that lives only in prose is not
reproducible and the easiest steps to forget are the two protecting the state file. **Versioning is the substance**
— `terraform state` has no undo, so a bad `state rm` or a truncated write is unrecoverable
without object history. Noncurrent versions expire after 90 days so it does not grow forever.

**`use_lockfile = true`, not a DynamoDB table.** Native S3 locking is GA in Terraform 1.11 and
`dynamodb_table` is deprecated; every tutorial recommending a lock table is stale. The mechanism
is a conditional `PutObject`, which is visible when it fires:

```
Error acquiring the state lock
api error PreconditionFailed: At least one of the pre-conditions you specified did not hold
Lock Info:  Operation: OperationTypeApply
```

That was produced deliberately rather than assumed. With no resources an apply finishes in
milliseconds, so two concurrent runs would not collide and the DoD would have "passed" while
proving nothing — the same vacuous-test trap as D-011's ordering assertion. A temporary
`terraform_data` with a 40-second `local-exec` widened the window, the second operation was
refused, then the probe was destroyed.

**No `profile` in the provider block.** Credentials come from `AWS_PROFILE`, so the same config
works unchanged when CI authenticates through GitHub OIDC — the alternative is editing HCL to
deploy from somewhere else.

**`default_tags`** carries `Project` and `ManagedBy` onto every resource, which is what makes
the billing console answer "what does this project cost" rather than showing one undifferentiated
line.

**Developer credentials are IAM Identity Center**, not an IAM user access key: a session that
expires in 8 hours rather than a static secret in `~/.aws/credentials`. Least privilege belongs
in the workload roles — the instance profile at #15 and the Lambda execution role at #22 — not
in the human's permission set, where scoping it precisely teaches nothing and blocks everything.
## D-012 · The ops gate is a shared password, and the detail route is deliberately open

**Ticket:** UW-017 · **Date:** 2026-07-21 · **Superseded by:** UW-019

A single `OPS_PASSWORD` over HTTP Basic, compared with `secrets.compare_digest`. **A demo
shortcut, labelled as one.** It authenticates nobody: the audit trail records `actor='ops'`
with no identity behind it, which is the gap UW-019 exists to close.

Basic rather than a custom header because browsers prompt for it natively, so the deployed URL
is usable before any frontend exists.

Two details that turn a 401 into something worse if missed. `compare_digest` raises `TypeError`
on non-ASCII `str`, so both sides are encoded to bytes or a `£` in the password becomes a 500.
And both halves of the credential are compared **before** the results are combined — `and`
short-circuits, which restores the timing signal a constant-time compare exists to remove.

**`GET /api/submissions/{id}` stays open.** #38–39 have the applicant watch their own
submission rate and read the result, and applicants have no account until UW-019 — so the UUID
*is* the capability. That is sound against enumeration and weak against leakage, since URLs
reach browser history, proxy logs and `Referer` headers. Acceptable for fabricated data; it
would not be for real submissions.

**`POST /api/submissions` stays open until #29**, which is when it starts spending Anthropic
credit.

**Classification is enforced by a test, not by remembering.** It walks the route tree and fails
on any route that is neither in an explicit public allowlist nor carrying the dependency. The
first version passed while seeing nothing at all — FastAPI 0.139 keeps an `_IncludedRouter`
rather than flattening into `app.routes`, so it was blind to every mounted route. A companion
test asserts the allowlist matches live routes, which is what caught it.

**Known gap:** `ops_password` defaults to `changeme`, so a deployment that forgets to set it is
open. Startup logs a warning; that is visibility, not a control. #16 builds the prod `.env` and
is where a real value belongs.

---

## D-014 · Documents bucket and ECR repo, and why they can be destroyed

**Ticket:** UW-061 · **Date:** 2026-07-22

The bucket name carries the account id (`underwrite-documents-564250611758`) because S3 names
are **globally unique** — a bare name is one namespace collision from a clone whose `apply`
fails. The id comes from `aws_caller_identity`, not a literal.

`aws_s3_bucket` and its four sub-resources are **separate resources** (split out in provider v4):
a monolithic bucket with inline `versioning`/`encryption` blocks silently no-ops on v6.

**`force_destroy = var.allow_destroy`, default false.** Left off, a bucket refuses to delete
while it holds objects, so `terraform destroy` fails once one PDF exists — the right default for
anything holding real documents. Hardcoding `true` is how someone's `destroy` quietly deletes
issued quotes. This is a demo that gets torn down, so a deliberate `-var allow_destroy=true`
enables teardown without making it the default.

**ECR is `IMMUTABLE`.** #21 tags images by git SHA; a SHA that can be overwritten defeats
pinning a deploy to a commit. The lifecycle policy expires untagged after 7 days and keeps the
last 5 tagged, because the 500MB free allowance is 12-month-only and untagged layers accumulate
on every rebuild.

**DoD proven, not asserted.** "Cannot be made public" was tested by an admin attempting both a
public-read ACL and a public bucket policy; both were refused with `AccessDenied` naming the
Block Public Access setting that stopped them. Setting the flag is not evidence the flag works.

**Correction (post-review):** the first version enabled versioning but expired only current
versions, so `bordereaux/` objects were hidden behind a delete marker rather than deleted, and
every render-retry rewrite of a `generated/` PDF left a noncurrent version that never expired.
Each rule that must reclaim storage now also carries `noncurrent_version_expiration`:
`bordereaux/` 365, `generated/` 30. This is the exact omission D-013 documented for the state
bucket and did not carry across.

---

## D-015 · EC2 host: IMDSv2 hop limit 2, no port 22, and a two-budget split

**Ticket:** UW-064 · **Date:** 2026-07-22

`t4g.small`, AL2023 arm64, AMI resolved from the SSM public parameter (latest, region-portable)
with `ignore_changes = [ami]` so a new release does not propose replacing a running box.

**`http_put_response_hop_limit = 2`, not the default 1.** IMDSv2 is `http_tokens = required`, but
at hop limit 1 the AWS SDK inside a Docker container cannot reach IMDS — a container is one
network hop from the host — so the instance role silently yields no credentials and S3 fails.
Set now because it bites at #36 (approve → S3), not here. Proven while the box was up: an IMDSv2
token was fetched from a shell.

**No SSH key, no port 22.** Security group is 80/443 inbound only; access is Session Manager via
`AmazonSSMManagedInstanceCore`. Verified: SSM registered `Online` and a command ran as root with
no key and no open 22.

**Least privilege proven by refusal.** The instance role allows `s3:GetObject`/`PutObject` on
`generated/*` only. A write to `generated/` succeeded and a write to `bordereaux/` was denied
with `AccessDenied` — the scope confines the role, not just permits the happy path.

**The stop-action halts compute, not the whole bill.** `STOP_EC2_INSTANCES` stops the ~$12/mo
instance, but the Elastic IP (~$3.60/mo, charged even while stopped since Feb 2024) and the 20GB
EBS volume persist — the backstop floors cost near ~$4/mo, it does not reach zero. Zeroing means
`terraform destroy`, which is the normal teardown anyway.

**Two budgets, deliberately.** The `$20` account-wide alert budget is created outside this stack
(CLI) so `terraform destroy` never removes cost protection between deploys. The `$30`
stop-action budget references the instance, so it lives and dies with it. `aws_budgets_budget_
action` also requires a top-level `notification_type` — the schema validate caught that before
any apply.

**Security-group descriptions are ASCII-only.** An em-dash in the description passed `validate`
and was rejected by the EC2 API at apply with `Character sets beyond ASCII are not supported` —
an apply-time check no plan can make. This is why deploy tickets apply-verify rather than trust
a clean plan.

---

## D-016 · Prod image, one registry, keyless CD, and reboot survival

**Ticket:** UW-066 · **Date:** 2026-07-22

**The prod image is multi-stage; the runtime carries no build tooling.** A `build` stage runs
`uv sync --frozen --no-dev` into a venv; the runtime stage is a fresh `python:3.13-slim` that
copies only that venv and the source, runs as a non-root user, and has no `uv`, no compiler, and
**no Pango/HarfBuzz/fonts** — the WeasyPrint dependency tree stays out of the API image entirely,
which is the whole point of splitting PDF rendering to the Lambda (#20). The dev stack builds the
same Dockerfile at `target: dev`, which keeps `uv` and the dev group so `make test`/`lint`/
`migrate` still run inside the container; the two targets share a `base` so the split costs no
duplication.

**One registry, both image types, deploy-by-SHA.** The API repo mirrors `pdf-render`:
`IMMUTABLE`, scan-on-push, the same lifecycle policy. Images are tagged by git SHA and never by a
moving `latest` — an immutable tag is what lets a deploy pin to a commit and a rollback re-point
at a prior one. The instance pulls with the ECR **credential helper** configured in
`~/.docker/config.json`, not a `docker login` token: the helper re-fetches credentials via the
instance role on every pull, so auth survives a reboot where a 12-hour token would not.

**Reboot survival is belt-and-suspenders.** Every service is `restart: unless-stopped` (the
Docker daemon restarts them on boot) *and* a `systemd` unit runs `docker compose up` after
`docker.service`. Postgres is a named volume and is **not** published to the host — it is reachable
only on the container network. `user_data` provisions the platform (Docker, the compose plugin —
AL2023 ships none —, git, the credential helper) and clones the **public** repo to
`/opt/underwrite` for the deployment *manifests* only: the compose file, the Caddyfile, and the
unit. The application itself always runs from the immutable ECR image, so cloning the repo never
means running code from a git checkout. Secrets live in `/opt/underwrite/.env` (chmod 600),
placed by the operator, never baked into an image or committed. `user_data_replace_on_change`
recreates the box when the script changes — correct because the box is ephemeral.

**CD is keyless, and delivery is separate from deployment.** GitHub Actions federates an IAM
OIDC provider scoped by the `repository` and `ref` claims to `<owner>/<repo>` on
`refs/heads/main` — no long-lived AWS keys in the repo. This account emits immutable-ID subjects
(`repo:owner@ID/repo@ID:...`), which a plain `repo:owner/repo:...` `StringEquals` never matches —
so a naive `sub` condition silently denies every assume. AWS *requires* a `sub` (or
`job_workflow_ref`) condition on this provider and rejects `repository`+`ref` alone, so the trust
carries both: exact `StringEquals` on `repository`+`ref`, plus a `StringLike` on `sub`
(`repo:owner*/repo*:...`) that tolerates the `@ID` segments and satisfies the requirement. The federation is done by hand (request the runner token, point the AWS CLI at it)
rather than a marketplace action, so the only third-party action is `checkout`, pinned to a SHA
like everything in `ci.yml`. Build-and-push runs on every merge to `main` — an artifact is
always ready — but rollout is a **manual** `workflow_dispatch` that `SendCommand`s the box,
because the environment is deliberately not always-on. `make deploy` and the deploy job invoke
the *same* `deploy/remote-deploy.sh` on the box, so there is one deploy path, not a Makefile copy
drifting from a YAML copy.

The CI role's `SendCommand` is scoped by the `Name=underwrite-app` **tag**, not the instance id.
An earlier version referenced `aws_instance.app.id`, which made the whole policy — including the
ECR-**push** statements — depend on the box; a targeted teardown of the instance then revoked
push access, coupling delivery to the ephemeral environment. Tag-scoping keeps the role and its
policy permanent (free) so build-push works whether or not a box exists.

**Caddy is an HTTP-only reverse proxy here.** The service, its port bindings, and its persisted
`/data` volume land now; the domain block and automatic TLS are #17, where a live box and a DNS
A record make an ACME challenge possible.

---

## D-017 · Caddy automatic TLS, routing, and the Cloudflare grey-cloud requirement

**Ticket:** UW-067 · **Date:** 2026-07-22

The site address is `{$DOMAIN}`, an env var, so one Caddyfile serves the real hostname in prod and
`localhost` locally. A real hostname triggers **automatic Let's Encrypt** (cert + renewal) and the
**HTTP→HTTPS redirect** for free; `localhost` gets Caddy's internal cert, so `make prod-up` proves
routing and the redirect without a public domain or ACME.

**Routing.** `@api path /api/* /health` reverse-proxies to `api:8000`; everything else is
`file_server` over `/srv/static`. `/health` is matched at the **root**, not under `/api`, because
the deploy smoke test (#18) and uptime checks hit `https://<domain>/health` — the API already
namespaces its real endpoints under `/api/submissions`, so the two coexist without an app change.
`/srv/static` is an empty placeholder (`deploy/static/`) until the frontend lands; `web/dist/` is
gitignored, so the committed placeholder lives under `deploy/`.

**Certs persist in the `/data` named volume** (from #16), so a redeploy reuses the issued cert
instead of re-hitting Let's Encrypt — the LE rate limit is low enough that re-issuing on every
deploy would lock issuance out.

**Cloudflare must be DNS-only (grey cloud), not proxied.** The A record points
`underwrite.nexusstechnologies.com` at the Elastic IP with the orange cloud **off**; a proxied
record terminates TLS at Cloudflare and intercepts the ACME HTTP-01 challenge, so Caddy never
gets its cert. The record must exist **before** Caddy first starts. The parent domain sets no
HSTS, so the brief HTTP-first window during issuance is safe.

**The Elastic IP is ephemeral.** It is released on teardown, so each apply gets a new IP and the
A record is re-pointed per verify — the deliberate `$0`-standing-cost trade (D-015). A stable
public URL would mean splitting the EIP into a standing resource (~$3.60/mo even while the box is
down); deferred until the demo needs to stay continuously live.

---

## D-018 · Prod migrations as a one-shot service, and a self-verifying deploy

**Ticket:** UW-068 · **Date:** 2026-07-22

Migrations run as a dedicated `migrate` compose service (`alembic upgrade head`, `restart: "no"`)
that `api` waits on with `depends_on: { condition: service_completed_successfully }`, not as a
step inside `remote-deploy.sh`. The schema is therefore guaranteed current **before** the API
starts, on every `up` — deploy *and* reboot — and `upgrade head` is a no-op once at head, so
re-running it each boot is safe. Keeping it declarative in compose means the ordering is enforced
by the runtime, not by a shell script that a future reboot path might skip. `alembic` is a
runtime dependency (async migrations via `run_async_migrations`, URL from `DATABASE_URL`), so it
is already in the prod image — no dev extras leak in.

`remote-deploy.sh` uses `docker compose up -d --wait`: the deploy **fails** if `migrate` exits
non-zero or the `api`/`db` healthchecks never pass. That is the smoke test — a deploy that
reports success has a migrated database and a healthy API, not just started containers. The
cold-box DoD (`https://<domain>/health` = 200 from a fresh instance) is the same guarantee proven
end to end on an apply-verify-destroy.

---

## D-019 · PDF render Lambda — minimal deps, a writable font cache, and how it's verified

**Ticket:** UW-051 · **Date:** 2026-07-22

The image installs **`pango shared-mime-info` + the DejaVu fonts only** — not the roadmap's
literal `cairo`/`gdk-pixbuf2`. WeasyPrint 69 writes PDFs with `pydyf` (pure Python) and rasterises
with Pillow, so cairo (dropped in WeasyPrint v53) and gdk-pixbuf are dead weight (R6). Verified,
not assumed: the RIE render embeds `DejaVu-Sans` and `DejaVu-Sans-Bold` as subsets.

**Fontconfig needs a writable cache or it renders tofu.** Lambda's filesystem is read-only except
`/tmp`, so `fonts.conf` sets `<cachedir>/tmp/fonts-cache/</cachedir>` and lists `/usr/share/fonts`,
with `FONTCONFIG_PATH=/var/task/fonts` and `XDG_CACHE_HOME=/tmp` (R2.3). Without the writable
cachedir, fontconfig fails with "No writable cache directories" and falls back to tofu boxes.

**arm64 needs `docker buildx build --platform linux/arm64 --provenance=false`** — the provenance
attestation manifest makes Lambda reject the image (R2.4). WeasyPrint is imported at **module
scope** so the ~2-5s init lands in the cold start, not every invoke (R2.5). Memory 2048 / timeout
60 live in the function's Terraform (#22), not the image.

**Handler contract is `{quote_id, html} → {s3_key}`**, deliberately template-independent, so a
hardcoded HTML string proves the whole toolchain. A `PDF_OUTPUT_DIR` env is the no-AWS path: the
handler writes to that dir instead of S3, so `make pdf-lambda-test` renders through the real
Lambda RIE with no credentials or bucket.

**Verifying fonts needs `pdffonts`, not `grep`.** WeasyPrint compresses the PDF streams, so
grepping the raw bytes for "DejaVu" is a false negative even when the font is embedded. `pdffonts`
parses the structure and reports embedded/subset per font — that is the DoD check.

**Render only resolves `data:` URIs, never the network.** WeasyPrint fetches `url()` / `<img src>`
/ `@import` while rendering, so once the quote template interpolates submission data, injected HTML
could SSRF the metadata endpoint or read local files from inside the Lambda. A `url_fetcher` that
allows only `data:` and raises on everything else closes that off. A failed fetch is non-fatal in
WeasyPrint (the render continues without the resource), so the guard is verified by calling the
fetcher directly — an `http:` URL raises, a `data:` URI resolves — not by inspecting the PDF.

---

## D-020 · Local PDF fallback keeps WeasyPrint out of the prod image

**Ticket:** UW-055 · **Date:** 2026-07-22

`LOCAL_PDF=1` renders in-process; `=0` invokes the Lambda. A `PdfRenderer` seam
(`render_and_store(quote_id, html) -> key`) has `LocalPdfRenderer` (WeasyPrint → `LocalStorage`)
and `LambdaPdfRenderer` (`lambda:invoke` → `{s3_key}`), so everything downstream depends on the
interface, not on which one runs. WeasyPrint lives in a **`local-pdf` dependency group**, not the
main deps: the dev image and CI install it (plus the Debian pango stack), the prod runtime stage
(`--no-dev`) never sees it — the API image stays free of Pango/HarfBuzz (R6). This is why the dev
`api/Dockerfile` stage `apt-get`s the pango libs and CI has a matching step, while the runtime
stage does not.

**`default_url_fetcher` is deprecated in WeasyPrint 69; use `URLFetcher`.** The SSRF guard is now
`URLFetcher(allowed_protocols=["data"])` — a callable that raises `ValueError` on any non-`data:`
scheme. The same fetcher is duplicated in `lambdas/pdf_render/handler.py` and
`app/services/pdf.py` because they deploy as separate units and can't share code; they are kept
byte-identical, and the deprecation was fixed in both, not one.

**The demo is the DoD.** `make demo` brings the stack up, POSTs a submission through the real API,
renders a quote PDF in-process, and fetches it back through `/api/documents/*` — a valid PDF with
no AWS credentials, bucket, or deployed Lambda. That "clone → `make up` → PDF" path is worth more
to a reviewer than any single cloud resource, which is why it is built now, not at the end.

---

## D-021 · LLM extraction — Sonnet 5, structured outputs, no retry loop

**Ticket:** UW-020 · **Date:** 2026-07-22

**`claude-sonnet-5`, not the Opus default.** Extraction is schema-constrained and the highest-volume
LLM call in the pipeline (one per submission), so Sonnet 5 is the deliberate cost choice over
Opus 4.8 — it's a config value (`extraction_model`), swappable per environment. **Thinking is
disabled**: the task is mechanical and the output is pinned to a schema, so adaptive thinking (Sonnet
5's default when the field is omitted) would only add tokens.

**Structured outputs, not prompt-parsing.** `messages.parse(output_format=ExtractedApplication)`
constrains the response to the Pydantic model and returns a validated `.parsed_output` — no
`json.loads`, no hand-rolled validation. The system prompt carries a `cache_control` breakpoint;
caching is marginal at demo volume (the prompt is under Sonnet 5's minimum cacheable prefix) but
correct for when the prompt grows.

**No validation-retry loop (R8).** The SDK auto-retries transport 429/5xx with backoff; a persistent
`anthropic.APIStatusError` propagates and the caller leaves the submission `status='received'` and
audits the failure — the pipeline never loops the model to "fix" a bad extraction. A
`stop_reason == "refusal"` raises `ExtractionRefused` before `parsed_output` is read.

**Cost stays out of CI.** Unit tests `respx`-replay a recorded API response fixture — the same
transport-level mock D-002 chose for Companies House, which extends to Anthropic because its SDK is
built on httpx. The live test is `@pytest.mark.llm` and excluded by `-m "not llm"`, so CI never
spends. The genuinely unbounded Anthropic bill is capped account-side before the URL goes public
(#31b). The client is constructor-injected so tests run it with `max_retries=0`.

---

## D-022 · Companies House enrichment — the R5 gotchas, encoded

**Ticket:** UW-022/023/024 · **Date:** 2026-07-22

**Company numbers are 8-char alphanumerics, not integers.** `normalise_company_number` splits the
leading alpha prefix (`SC`/`NI`/`OC`/`FC`/…) and zero-pads only the digits (`6` → `00000006`,
`SC1234` → `SC001234`). Integer parsing silently drops Scotland, NI, and every LLP — R5.1. Lookup
is number-first; on 404 (or no number) it searches, then **refetches the full `/company/{number}`
profile** because search hits carry no `sic_codes` (R5). `sic_codes` is absent (not empty) on many
companies and kept as **strings** (leading zeros).

**429 never blocks the pipeline.** A rate-limited lookup returns `CompaniesHouseLookup(None,
rate_limited=True)` immediately — enrichment is best-effort, and a strict `600 req / 5 min` limit
can't stall a submission. The client is `httpx.AsyncClient` with `BasicAuth(key, "")` (key as
username, empty password).

**Fuzzy-match normalises both sides before scoring.** `LTD`→`LIMITED`, `PLC`→`PUBLIC LIMITED
COMPANY`, `LLP`→`LIMITED LIABILITY PARTNERSHIP`, `&`↔`AND`, drop leading `THE`, strip punctuation,
uppercase — then `rapidfuzz.token_sort_ratio`, scaled 0–1. Without this, `Acme Ltd` vs
`ACME LIMITED` scores below 0.85 and every correct match is wrongly referred (R5.2).

**Discrepancies are sentences, and `active` + `active-proposal-to-strike-off` is its own signal.**
The strings render verbatim in the ops dashboard, so they read as prose. Beyond age-vs-incorporation
(±1 year) and non-active status, a company whose status is `active` but whose
`company_status_detail` says it is being struck off is the sharpest signal in the payload (R5.3) —
four lines that show the spec was read, not just `status == "active"`.

Built standalone; the pipeline assembles a persisted `Enrichment` from these pieces at UW-025.

---

## D-023 · Pipeline orchestration — a three-stage flow with a per-stage error model

**Ticket:** UW-025 · **Date:** 2026-07-22

`run_pipeline` runs **extract → enrich → rate** synchronously inside `POST /api/submissions`,
writing one `AuditEvent` per transition and **committing after each stage**. The submission's
`SUBMISSION_RECEIVED` is committed by the route *before* the pipeline, so a crash mid-pipeline
leaves a durable, recoverable record rather than losing the submission.

**Each stage fails differently, on purpose.** The three failure modes are not the same event and
must not be flattened into one:

- **Extract — hard stop.** A `paste` calls the LLM; `anthropic.APIStatusError` or an
  `ExtractionRefused` is caught, audited as `EXTRACTION_FAILED`, the submission is set `failed`, and
  the pipeline returns. `failed` is recoverable — a retry re-runs the model (no loop-to-fix, per
  D-021). A `form` carries its fields already and skips the model; a `pdf_upload` has no text yet
  (UW-026) and returns early, still `received`.
- **Enrich — best-effort, never a hard stop.** `enrich()` wraps `CompaniesHouseClient.lookup()` in
  `try/except Exception` (the #30-review fix — non-429 errors previously propagated). A CH outage,
  a 429, or no match all degrade to `ch_found=False`, which the engine turns into a `CH_NOT_FOUND`
  **REFER** — the safe underwriting outcome. The failure is recorded as `ENRICHMENT_FAILED` and the
  pipeline **continues to rating**. (Proven live: a real CH `400` from a missing key was swallowed,
  audited, and still produced a rating.)
- **Rate — refer, or fail.** A valid extraction that lacks a required rating input raises
  `IncompleteExtraction`; that is a **referral, not a crash** — status `referred`, audit
  `RATING_FAILED{reason: incomplete_extraction}`, no `Rating` row (the engine can't run without the
  value). An *unexpected* `rate()` exception (a bug — the engine is pure and validated) is caught
  defensively → `failed` + `RATING_FAILED{reason: rating_error}`, leaving extract + enrich durable.

`STATUS_FOR_DECISION` maps `Decision → SubmissionStatus` table-driven (auto_approve→auto_approved,
refer→referred, decline→declined). **The pipeline stops at `Rating`** — no `Quote` is generated
here; quote issuance is ops-gated (UW-036), which is where `quoted` is reached.

**Long-lived clients live in `lifespan`.** The `AsyncAnthropic` and Companies House `httpx`
connection pools are built once per process on `app.state` and closed on shutdown (each service
grew an `aclose()`); FastAPI deps hand them to the route, which forwards them to `run_pipeline`.
Tests inject fakes via `dependency_overrides`, so the suite stays offline — no network, no spend.

---

## D-024 · Seed data — the real pipeline, canned inputs, deterministic ids

**Ticket:** UW-027 · **Date:** 2026-07-22

`make seed` inserts **6 representative submissions** spanning the decision spectrum (1 auto-approve,
3 refer — name-mismatch, missing-revenue, strike-off — and 2 decline — crypto, too-new), so the ops
dashboard has varied data with **no LLM key and no Companies House network**. PRD §11's exact list
was never saved to a file, so the six are a designed set, not a transcription.

**The seed runs the real `run_pipeline`, not hand-written rows.** `app/seed.py` feeds each scenario
a tiny `_CannedExtractor` (returns the canned `ExtractedApplication`) and `_CannedCh` (returns the
canned `CompaniesHouseLookup`) — duck-typed against the same params the route injects. Every
extraction/enrichment/rating row and audit event is therefore exactly what production would write,
and premiums come from the pure `rate()` engine, never a literal. The incomplete-revenue scenario
exercises the `IncompleteExtraction → referred, no Rating` path for free.

**Idempotency is a `uuid5` primary key, not an upsert.** Each submission id is
`uuid5(SEED_NAMESPACE, slug)`; the loop skips any id already present. Re-running is a no-op —
"twice → 6, not 12" (the DoD). A mutation to `uuid4()` makes the second run insert duplicates and
fails `test_seeding_twice_is_idempotent`, so the determinism is load-bearing, not incidental.
