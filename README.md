# Underwrite — AI Underwriting Workbench

Submission-to-quote pipeline for Tech E&O / Cyber.

## Local development

```
make up        # build + start the stack, migrate, wait for health
make test      # pytest, containerised
make lint fmt  # ruff
```

Postgres is on host port **55432**; the API on **8000**.

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

### CD (GitHub Actions)

`cd.yml` federates AWS via OIDC — no static keys. Build-and-push runs on every merge to `main`;
rollout is a manual `workflow_dispatch`. Set these repo **variables** (Settings → Actions):

- `AWS_ROLE_ARN` — `terraform output github_actions_role_arn`
- `ECR_API_REPO` — `terraform output api_ecr_repository_url`
