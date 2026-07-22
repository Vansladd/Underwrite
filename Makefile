COMPOSE := docker compose
API_PORT ?= 8000

# One place for the profile; Terraform reads credentials from the environment, never HCL.
# ?= yields to an exported AWS_PROFILE, so tf-account asserts which account we reached.
AWS_PROFILE ?= underwrite
AWS_ACCOUNT ?= 564250611758
REGION ?= eu-west-2
ECR_API := $(AWS_ACCOUNT).dkr.ecr.$(REGION).amazonaws.com/underwrite/api
PROD_COMPOSE := $(COMPOSE) -f docker-compose.prod.yml
TF := AWS_PROFILE=$(AWS_PROFILE) terraform -chdir=infra

.PHONY: help up down restart logs ps health test lint fmt regen-goldens migrate migration downgrade seed psql shell clean tf-bootstrap tf-account tf-init tf-fmt tf-check tf-plan tf-apply push-api prod-up prod-down deploy smoke

help:
	@echo "Underwrite — available targets"
	@echo ""
	@echo "  make up        build + start the stack, migrate, wait for health"
	@echo "  make down      stop the stack (keeps the database volume)"
	@echo "  make restart   down + up"
	@echo "  make logs      tail all logs"
	@echo "  make ps        service status"
	@echo "  make health    curl /health"
	@echo ""
	@echo "  make test      run pytest inside the api container"
	@echo "  make lint      ruff check"
	@echo "  make fmt       ruff format + fix imports"
	@echo "  make regen-goldens  rewrite the rating golden file"
	@echo ""
	@echo "  make migrate   alembic upgrade head"
	@echo "  make migration m=\"...\"  autogenerate a revision"
	@echo "  make downgrade one revision back"
	@echo "  make seed      insert the 6 canned submissions (UW-027)"
	@echo ""
	@echo "  make tf-bootstrap  create the state bucket (idempotent)"
	@echo "  make tf-init   terraform init against the S3 backend"
	@echo "  make tf-check  fmt -check + validate, no credentials needed"
	@echo "  make tf-fmt    terraform fmt"
	@echo "  make tf-plan   terraform plan"
	@echo "  make tf-apply  terraform apply"
	@echo ""
	@echo "  make push-api  buildx arm64 + push the API image to ECR (tag = git sha)"
	@echo "  make prod-up   run docker-compose.prod.yml locally (build + health check)"
	@echo "  make prod-down stop the local prod stack"
	@echo "  make deploy image=...  SSM the box to pull the tag and restart the unit"
	@echo "  make smoke DOMAIN=...  curl https://DOMAIN/health (cold-box check)"
	@echo ""
	@echo "  make psql      open a psql shell on the database"
	@echo "  make shell     open a bash shell in the api container"
	@echo "  make clean     down + delete the database volume"

.env:
	@cp .env.example .env
	@echo "created .env from .env.example"

up: .env
	$(COMPOSE) up -d --build
	@$(MAKE) --no-print-directory migrate
	@printf "waiting for api"
	@for i in $$(seq 1 40); do \
		if curl -fsS http://localhost:$(API_PORT)/health >/dev/null 2>&1; then \
			echo " ok"; \
			curl -fsS http://localhost:$(API_PORT)/health; echo; \
			exit 0; \
		fi; \
		printf "."; sleep 1; \
	done; \
	echo " timed out"; $(COMPOSE) logs --tail=40 api; exit 1

down:
	$(COMPOSE) down

restart: down up

logs:
	$(COMPOSE) logs -f

ps:
	$(COMPOSE) ps

health:
	@curl -fsS http://localhost:$(API_PORT)/health && echo

test:
	$(COMPOSE) run --rm api uv run --frozen pytest -q

regen-goldens:
	$(COMPOSE) run --rm --no-deps api uv run --frozen pytest -q --regen-goldens tests/test_rating_goldens.py

lint:
	$(COMPOSE) run --rm --no-deps api uv run --frozen ruff check .

fmt:
	$(COMPOSE) run --rm --no-deps api uv run --frozen ruff format .
	$(COMPOSE) run --rm --no-deps api uv run --frozen ruff check --fix .

migrate:
	$(COMPOSE) run --rm -w /app api uv run --frozen alembic upgrade head

migration:
	@test -n "$(m)" || (echo 'usage: make migration m="what changed"'; exit 1)
	$(COMPOSE) run --rm -w /app api uv run --frozen alembic revision --autogenerate -m "$(m)"

downgrade:
	$(COMPOSE) run --rm -w /app api uv run --frozen alembic downgrade -1

tf-account:
	@got=$$(AWS_PROFILE=$(AWS_PROFILE) aws sts get-caller-identity --query Account --output text 2>/dev/null); \
	if [ "$$got" != "$(AWS_ACCOUNT)" ]; then \
		echo "refusing: profile $(AWS_PROFILE) is account $${got:-<none>}, expected $(AWS_ACCOUNT)"; \
		exit 1; \
	fi; \
	echo "account $$got via profile $(AWS_PROFILE)"

tf-bootstrap: tf-account
	AWS_PROFILE=$(AWS_PROFILE) ./infra/bootstrap.sh

tf-init: tf-account
	$(TF) init

tf-fmt:
	$(TF) fmt

tf-check:
	$(TF) fmt -check
	$(TF) init -backend=false -input=false
	$(TF) validate

tf-plan: tf-account
	$(TF) plan

tf-apply: tf-account
	$(TF) apply

push-api: tf-account
	@sha=$$(git rev-parse --short HEAD); \
	AWS_PROFILE=$(AWS_PROFILE) aws ecr get-login-password --region $(REGION) \
	  | docker login --username AWS --password-stdin $(ECR_API); \
	docker build --platform linux/arm64 -t $(ECR_API):$$sha ./api; \
	docker push $(ECR_API):$$sha; \
	echo "pushed $(ECR_API):$$sha"

prod-up: .env
	docker build -t underwrite/api:local ./api
	API_IMAGE=underwrite/api:local DOMAIN=localhost $(PROD_COMPOSE) up -d
	@printf "waiting for api via caddy (https, internal cert)"; \
	for i in $$(seq 1 40); do \
		if curl -fsSk https://localhost/health >/dev/null 2>&1; then \
			echo " ok"; curl -fsSk https://localhost/health; echo; \
			printf "http->https redirect: "; curl -s -o /dev/null -w '%{http_code}\n' http://localhost/health; \
			exit 0; \
		fi; \
		printf "."; sleep 1; \
	done; \
	echo " timed out"; API_IMAGE=underwrite/api:local DOMAIN=localhost $(PROD_COMPOSE) logs --tail=40; exit 1

prod-down:
	API_IMAGE=underwrite/api:local DOMAIN=localhost $(PROD_COMPOSE) down

smoke:
	@test -n "$(DOMAIN)" || (echo 'usage: make smoke DOMAIN=<host>'; exit 1)
	@curl -fsS https://$(DOMAIN)/health && echo

deploy: tf-account
	@test -n "$(image)" || (echo 'usage: make deploy image=$(ECR_API):<sha>'; exit 1)
	@iid=$$($(TF) output -raw instance_id); \
	cid=$$(AWS_PROFILE=$(AWS_PROFILE) aws ssm send-command --region $(REGION) \
		--instance-ids $$iid --document-name AWS-RunShellScript \
		--parameters commands="bash /opt/underwrite/deploy/remote-deploy.sh $(image)" \
		--query Command.CommandId --output text); \
	echo "sent $$cid to $$iid; poll: aws ssm get-command-invocation --command-id $$cid --instance-id $$iid"

seed:
	@echo "not implemented yet — see UW-027 (seed data)"
	@exit 1

psql:
	$(COMPOSE) exec db psql -U underwrite -d underwrite

shell:
	$(COMPOSE) exec api bash

clean:
	$(COMPOSE) down -v
