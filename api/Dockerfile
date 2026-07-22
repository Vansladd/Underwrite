# Multi-stage; runtime carries no uv, no build tools, no WeasyPrint deps. See D-016.
FROM python:3.13-slim AS base

COPY --from=ghcr.io/astral-sh/uv:0.11.8 /uv /uvx /bin/

ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PROJECT_ENVIRONMENT=/opt/venv \
    PATH="/opt/venv/bin:$PATH" \
    PYTHONUNBUFFERED=1

WORKDIR /app

COPY pyproject.toml uv.lock ./

# Dev target for docker-compose.yml: keeps uv and the dev group, source is mounted.
FROM base AS dev
# WeasyPrint's pango stack for the LOCAL_PDF fallback; dev-only, never in the runtime stage.
RUN apt-get update \
 && apt-get install -y --no-install-recommends \
      libpango-1.0-0 libpangoft2-1.0-0 libharfbuzz-subset0 fonts-dejavu-core shared-mime-info \
 && rm -rf /var/lib/apt/lists/*
RUN uv sync --frozen --group local-pdf

# Prod dependency layer: no dev group, cached on the lockfile alone.
FROM base AS build
RUN uv sync --frozen --no-dev

FROM python:3.13-slim AS runtime

ENV PATH="/opt/venv/bin:$PATH" \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1

RUN useradd --system --uid 10001 --no-create-home app

WORKDIR /app

COPY --from=build /opt/venv /opt/venv
COPY . .

USER app

EXPOSE 8000

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
