# Underwrite — AI Underwriting Workbench

A submission-to-quote pipeline for **Technology E&O / Cyber** insurance. A broker sends in a risk;
Underwrite turns it into a priced, reviewable quote in seconds — an LLM reads the submission, the
company is verified against Companies House, a deterministic engine prices it, and an operator
approves or declines from a console that shows exactly how every number was reached.

## What it does

Insurance intake is unstructured — a broker pastes an email, fills a form, or attaches a PDF.
Underwrite ingests that and runs it through a fixed pipeline:

```
submission ──▶ extract ──▶ enrich ──▶ rate ──▶ operator decision ──▶ quote PDF
              (LLM)      (Companies    (rules      (approve /          (Lambda →
                          House)        engine)     decline)            S3)
```

- **Extract** — `claude-sonnet-5` parses the raw submission into a validated `ExtractedApplication`
  (structured outputs, no free-text scraping). Missing fields are recorded, not guessed.
- **Enrich** — the company is looked up at Companies House; the submitted name/number/status are
  reconciled and discrepancies (name mismatch, strike-off, dissolved) are flagged.
- **Rate** — a **pure, deterministic** engine prices the risk from table-driven factors (limit,
  revenue band, sector, data volume, claims, trading history). It emits an auditable factor trace
  that folds back to the premium, plus a decision: **auto-approve**, **refer** to a human, or
  **decline**.
- **Decide** — an operator reviews referrals in the console (extracted-vs-Companies-House
  side-by-side, the premium build-up, the reasons) and approves or declines. Every action is
  written to an append-only audit trail that names the underwriter.
- **Quote** — an approved submission renders a specimen quote PDF (WeasyPrint in a Lambda) stored
  in S3 and served via a presigned URL.

**The core design principle:** the LLM only ever *parses* (probabilistic, so anything uncertain is
referred to a human); the engine *prices* (deterministic, table-driven, and asserted
character-for-character against `docs/RATING_SPEC.md`). Nothing an LLM says sets a price.

## Architecture & stack

Three tiers, same-origin in dev via a Vite proxy:

**Backend** (`api/`) — **FastAPI** (async, `lifespan`), **SQLAlchemy 2 async** + **asyncpg** on
**Postgres**, migrations via **Alembic**. Money is integer **pence** end to end; rate factors are
`Decimal`. Domain enums/value-objects (`app/domain/`) import only stdlib; the rating engine
(`app/services/rating.py`) is import-pure and AST-tested for it. External calls — **Anthropic**
(extraction), **Companies House** (enrichment, fuzzy-matched with **rapidfuzz**) — go through
`httpx` and are `respx`-mocked in tests. PDF rendering is **WeasyPrint**, kept out of the API image
and run as a **Lambda** (the API only builds the HTML). ~360 tests, property-based invariants
(**Hypothesis**) + golden files on the engine.

**Frontend** (`web/`) — **React** + **TypeScript** + **Vite**, **Tailwind v4**, **TanStack Query**,
typed against the API's OpenAPI schema (`openapi-fetch`, `openapi-typescript`). The operator console:
a status-filtered queue, a detail drawer (comparison, factor ladder, timeline, quote), and the
approve/decline actions. Design tokens are authoritative (`DESIGN.md`, `PRODUCT.md`) — light/dark is
a pure CSS-var swap.

**Infra** (`infra/`, `deploy/`, `lambdas/`) — **Terraform** on AWS: a single **EC2** box running
`docker compose` under a `systemd` unit, **Caddy** fronting the API with automatic TLS, **Postgres**
on the container network, **S3** for documents, and the arm64 container-image **Lambda** for PDFs.
Images are tagged by git SHA in **ECR** (immutable, never `latest`). **CD** (`cd.yml`) federates AWS
via **GitHub OIDC** — no static keys — building on every merge to `main` with a gated deploy. Deploy
tickets follow **apply → verify → destroy**: nothing runs between verifications, so the idle bill is
≈ $0.

## Repository layout

| Path | What's there |
|---|---|
| `api/` | FastAPI app — `app/api/routes`, `app/services` (extraction, enrichment, rating, quote, pdf), `app/models`, `app/domain`, `app/schemas`; `tests/` |
| `web/` | React operator console (Vite + Tailwind) |
| `infra/` | Terraform (EC2, S3, Lambda, IAM, ECR, OIDC, budgets) |
| `lambdas/pdf_render/` | WeasyPrint container Lambda (HTML → PDF → S3) |
| `deploy/` | prod compose, Caddyfile, systemd unit |
| `docs/` | `RATING_SPEC.md` (authoritative pricing) + `DECISIONS.md` (committed rationale) |

## Local development

```
make up        # build + start the stack, migrate, wait for health
make test      # pytest, containerised
make lint fmt  # ruff
```

Postgres is on host port **55432**; the API on **8000**.

## Operator console

`make up` also starts a Vite dev server (containerised) at **http://localhost:5173** that proxies
`/api` to the API — same-origin, so there is no CORS. Every data and money-spending route sits
behind a login; only `/health` and `/api/auth/login` are open.

```
make up && make seed        # seeds the sample submissions + a demo operator
make web-types              # regenerate web/src/api/schema.d.ts from the live OpenAPI
make web-lint               # eslint + tsc
```

**Local login:** `demo` / `underwrite-demo` (set by `SEED_OPERATOR_*`, overridable in `.env`). The
**deployed URL uses a strong, private password** from `.env.prod` — never this public default, and
never committed. Auth is a signed-cookie session (Argon2id hashes); rotating `SECRET_KEY` logs
everyone out. See `docs/DECISIONS.md` D-026.

## LLM extraction

Pasted submissions are parsed into a validated `ExtractedApplication` by
`app/services/extraction.py` (`claude-sonnet-5`, structured outputs). `make test` excludes the
live-LLM tests; run them against the real API with `make test-llm` (set `ANTHROPIC_API_KEY` in
`.env` first — this spends). If the rambling-email case underperforms, escalate with
`extraction_model=claude-opus-4-8` in `.env` — that's the lever, not a prompt rewrite.

**`extraction_confidence` is LLM self-reported and weakly calibrated** — a legitimate signal to
refer a risk for human review, not a statistical error rate. Treat a low value as "look at this",
not "this is X% likely wrong".

## Production image & deploy

The API runs from a multi-stage image (`api/Dockerfile`) that carries no build tooling and no
WeasyPrint dependencies — PDF rendering is a separate Lambda. Images are tagged by git SHA and
pushed to an immutable ECR repo; deploys pin to a SHA and never a moving `latest`.

```
make prod-up               # run docker-compose.prod.yml locally (build + health check)
make push-api              # arm64 build + push to ECR, tag = git sha
make deploy image=<ref>    # SSM the box to pull the tag and restart the unit
```

On the box: `docker compose` under a `systemd` unit (`deploy/underwrite.service`), Caddy fronting
the API on 80/443, Postgres on the container network only. `user_data` provisions Docker, the
compose plugin, and the ECR credential helper, and clones this repo for the deploy manifests; the
app always runs from the ECR image. Secrets live in `/opt/underwrite/.env` (chmod 600). See
`docs/DECISIONS.md` D-016.

### PDF render Lambda (staged apply)

The renderer is a container-image Lambda (`lambdas/pdf_render/`). `aws_lambda_function` can't apply
until its image exists in ECR, so deployment is **staged, with the image tag as a Terraform
variable**:

```
terraform apply -target=aws_ecr_repository.pdf_render   # once; the repo (done at #14)
make push-pdf-lambda                                    # buildx arm64, tag = git sha, push
make tf-apply … -var image_tag=$(git rev-parse --short HEAD)
```

The function is gated `count = var.image_tag != "" ? 1 : 0`, so a box-only apply needs no image;
passing `-var image_tag=<sha>` creates it. Verify with `aws lambda invoke` — it writes a PDF to
`s3://…/generated/`.

Why this over the alternatives:
- **`null_resource` + `local-exec`** to `docker push` inside `apply` couples Terraform to a Docker
  daemon and hides the build in state — the push isn't a tracked resource and reruns are murky.
- **A dummy `:bootstrap` image + `lifecycle { ignore_changes = [image_uri] }`** lets the first
  apply succeed, but then Terraform never tracks the tag again, so deploys drift outside state.

An explicit `image_tag` var keeps the image a build artifact and the deploy a plain, reviewable
`apply` pinned to a commit.

### CD (GitHub Actions)

`cd.yml` federates AWS via OIDC — no static keys. Build-and-push runs on every merge to `main`;
rollout is a manual `workflow_dispatch`. Set these repo **variables** (Settings → Actions):

- `AWS_ROLE_ARN` — `terraform output github_actions_role_arn`
- `ECR_API_REPO` — `terraform output api_ecr_repository_url`
