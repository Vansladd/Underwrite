COMPOSE := docker compose
API_PORT ?= 8000

.PHONY: help up down restart logs ps health test lint fmt migrate seed psql shell clean

help:
	@echo "Underwrite — available targets"
	@echo ""
	@echo "  make up        build + start the stack, wait for health"
	@echo "  make down      stop the stack (keeps the database volume)"
	@echo "  make restart   down + up"
	@echo "  make logs      tail all logs"
	@echo "  make ps        service status"
	@echo "  make health    curl /health"
	@echo ""
	@echo "  make test      run pytest inside the api container"
	@echo "  make lint      ruff check"
	@echo "  make fmt       ruff format + fix imports"
	@echo ""
	@echo "  make migrate   run alembic migrations        (UW-013)"
	@echo "  make seed      insert the 6 canned submissions (UW-027)"
	@echo ""
	@echo "  make psql      open a psql shell on the database"
	@echo "  make shell     open a bash shell in the api container"
	@echo "  make clean     down + delete the database volume"

.env:
	@cp .env.example .env
	@echo "created .env from .env.example"

up: .env
	$(COMPOSE) up -d --build
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

lint:
	$(COMPOSE) run --rm --no-deps api uv run --frozen ruff check .

fmt:
	$(COMPOSE) run --rm --no-deps api uv run --frozen ruff format .
	$(COMPOSE) run --rm --no-deps api uv run --frozen ruff check --fix .

migrate:
	@echo "not implemented yet — see UW-013 (Alembic async migration)"
	@exit 1

seed:
	@echo "not implemented yet — see UW-027 (seed data)"
	@exit 1

psql:
	$(COMPOSE) exec db psql -U underwrite -d underwrite

shell:
	$(COMPOSE) exec api bash

clean:
	$(COMPOSE) down -v
