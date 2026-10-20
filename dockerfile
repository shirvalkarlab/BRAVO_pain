# Build from this repository root; frontend and backend share one revision.
FROM node:24-bookworm-slim AS frontend
WORKDIR /build
COPY Client/package.json Client/package-lock.json ./
RUN npm ci
COPY Client/ ./
COPY deploy/prepare-frontend.mjs /build/prepare-frontend.mjs
ARG BUILD_REVISION=unverified-local-build
ENV REACT_APP_BUILD_REVISION=$BUILD_REVISION
RUN CI=false GENERATE_SOURCEMAP=false npm run build && node prepare-frontend.mjs

FROM ghcr.io/astral-sh/uv:0.10.2 AS uv

FROM ubuntu:24.04 AS backend
ARG BUILD_REVISION=unverified-local-build
LABEL org.opencontainers.image.revision=$BUILD_REVISION
ENV DEBIAN_FRONTEND=noninteractive PYTHONUNBUFFERED=1 PYTHONDONTWRITEBYTECODE=1 UV_PYTHON_DOWNLOADS=never RPY2_CFFI_MODE=ABI DATASERVER_PATH=/data/bravo/ DJANGO_SETTINGS_MODULE=BRAVO.jetstream_settings BRAVO_BUILD_REVISION=$BUILD_REVISION SAVED_ANSWERS_REFRESH=0 OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 MKL_NUM_THREADS=1 PATH=/app/.venv/bin:$PATH
# Preserve Prasad's R/lme4/lmerTest/emmeans versions; fail if unavailable rather
# than silently substituting a statistical runtime. rpy2 3.5.15 uses ABI mode.
RUN apt-get update && apt-get install -y --no-install-recommends python3 python3-venv python3-dev build-essential pkg-config default-libmysqlclient-dev libffi-dev ca-certificates r-base-core=4.3.3-2build2 r-cran-lme4=1.1-35.1-4 r-cran-lmertest=3.1-3-2 r-cran-emmeans=1.10.0+dfsg-1 && rm -rf /var/lib/apt/lists/*
COPY --from=uv /uv /usr/local/bin/uv
WORKDIR /app
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --extra production --no-dev --python /usr/bin/python3 && uv cache clean
COPY BRAVO/ /app/BRAVO/
COPY deploy/gunicorn.conf.py deploy/entrypoint.sh deploy/refresh-saved-answers.sh /app/deploy/
COPY --from=frontend /build/build/index.html /app/BRAVO/Server/templates/index.html
RUN useradd --system --uid 10001 --create-home bravo && mkdir -p /data/bravo /app/staticfiles /app/BRAVO/static && chown -R bravo:bravo /app /data/bravo
USER bravo
WORKDIR /app/BRAVO
EXPOSE 8000
CMD ["sh", "/app/deploy/entrypoint.sh"]

FROM caddy:2.10-alpine AS web
ARG BUILD_REVISION=unverified-local-build
LABEL org.opencontainers.image.revision=$BUILD_REVISION
COPY --from=frontend /build/build /srv
COPY deploy/Caddyfile /etc/caddy/Caddyfile
