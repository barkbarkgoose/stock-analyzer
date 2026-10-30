# syntax=docker/dockerfile:1
#
# One image for the whole app: the Vue build is served by Django/WhiteNoise,
# the API by gunicorn. Postgres runs in its own container (compose.production.yaml).

# --- Frontend build ----------------------------------------------------------
# pnpm 11 needs Node 22+.
FROM node:22-bookworm-slim AS frontend
WORKDIR /src/frontend
COPY frontend/package.json frontend/pnpm-lock.yaml frontend/pnpm-workspace.yaml ./
RUN npx -y pnpm@11.13.0 install --frozen-lockfile
COPY frontend/ ./
RUN npx -y pnpm@11.13.0 run build

# --- App ---------------------------------------------------------------------
FROM python:3.13-slim-bookworm AS app
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    DJANGO_ENV=production

WORKDIR /app
COPY backend/requirements.lock backend/requirements.lock
RUN pip install -r backend/requirements.lock

COPY stock_rebound_analyzer/ stock_rebound_analyzer/
COPY backend/ backend/
COPY --from=frontend /src/frontend/dist frontend/dist

# Collect admin/static assets at build time. The values are throwaway: they only
# satisfy the production settings' required-variable checks for this one step.
RUN cd backend \
    && SECRET_KEY=collectstatic-only ALLOWED_HOSTS=build.invalid \
       DATABASE_URL=sqlite:////tmp/collectstatic.sqlite3 \
       python manage.py collectstatic --noinput -v0 \
    && useradd --system --uid 10001 --no-create-home app

USER app
WORKDIR /app/backend
EXPOSE 8000

# gthread workers: a few slow profile builds can run while other requests are
# served. The screener runs in a background thread inside a worker.
CMD ["gunicorn", "config.wsgi:application", \
     "--bind", "0.0.0.0:8000", \
     "--workers", "2", "--threads", "4", \
     "--timeout", "180", "--graceful-timeout", "30", \
     "--access-logfile", "-"]
