# syntax=docker/dockerfile:1
# Image chung cho API và worker của Hàng Chọn (khác nhau ở lệnh chạy, xem docker-compose.prod.yml).
#
#   docker build -t hangchon-api ./api
#   API:    (lệnh mặc định) kiểm một head Alembic → alembic upgrade head → uvicorn :8000
#   worker: arq app.worker.WorkerSettings

ARG PYTHON_VERSION=3.13
ARG DEBIAN_RELEASE=trixie
ARG UV_VERSION=0.11.14

FROM ghcr.io/astral-sh/uv:${UV_VERSION} AS uv

# ---- tầng dựng: cài thư viện vào /app/.venv bằng uv (chỉ nhóm chạy, không dev) ----------------------------------
FROM python:${PYTHON_VERSION}-slim-${DEBIAN_RELEASE} AS build
COPY --from=uv /uv /usr/local/bin/uv
ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PYTHON_DOWNLOADS=never \
    UV_PROJECT_ENVIRONMENT=/app/.venv
WORKDIR /app
COPY pyproject.toml uv.lock ./
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --no-dev --no-install-project

# ---- tầng chạy ----------------------------------------------------------------------------------------------------
FROM python:${PYTHON_VERSION}-slim-${DEBIAN_RELEASE} AS runtime

# Bản postgresql-client phải cùng bản chính với Postgres trong docker-compose.prod.yml (pg_dump cho sao lưu k4).
ARG PG_MAJOR=16

# postgresql-client lấy từ kho PGDG (Debian chỉ có một bản); ffmpeg dựng video ngắn (f6); DejaVu vẽ phụ đề/ảnh.
RUN set -eux; \
    apt-get update; \
    apt-get install -y --no-install-recommends ca-certificates curl; \
    install -d /usr/share/postgresql-common/pgdg; \
    curl -fsSL -o /usr/share/postgresql-common/pgdg/apt.postgresql.org.asc https://www.postgresql.org/media/keys/ACCC4CF8.asc; \
    . /etc/os-release; \
    echo "deb [signed-by=/usr/share/postgresql-common/pgdg/apt.postgresql.org.asc] https://apt.postgresql.org/pub/repos/apt ${VERSION_CODENAME}-pgdg main" \
      > /etc/apt/sources.list.d/pgdg.list; \
    apt-get update; \
    apt-get install -y --no-install-recommends "postgresql-client-${PG_MAJOR}" ffmpeg fonts-dejavu-core; \
    apt-get purge -y --auto-remove curl; \
    rm -rf /var/lib/apt/lists/*; \
    pg_dump --version | grep -q " ${PG_MAJOR}\."; \
    ffmpeg -hide_banner -version | head -n 1

RUN groupadd --system --gid 10001 app \
 && useradd --system --uid 10001 --gid app --home-dir /app --shell /usr/sbin/nologin app \
 && install -d -o app -g app /data /data/storage

ENV PATH="/app/.venv/bin:${PATH}" \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    APP_ENV=prod \
    STORAGE_LOCAL_DIR=/data/storage \
    PORT=8000 \
    UVICORN_WORKERS=1

WORKDIR /app
COPY --from=build --chown=app:app /app/.venv /app/.venv
COPY --chown=app:app alembic.ini ./
COPY --chown=app:app alembic ./alembic
COPY --chown=app:app app ./app

USER app
VOLUME ["/data"]
EXPOSE 8000

HEALTHCHECK --interval=15s --timeout=5s --start-period=60s --retries=5 \
  CMD python -c "import os,urllib.request; urllib.request.urlopen(f'http://127.0.0.1:{os.environ.get(\"PORT\",\"8000\")}/api/health', timeout=4)" || exit 1

# Một head Alembic duy nhất, migrate, rồi mới nhận request. Worker ghi đè lệnh này.
CMD ["sh", "-c", "set -e; heads=$(alembic heads 2>/dev/null | grep -c '(head)' || true); if [ \"$heads\" != 1 ]; then echo \"Alembic có $heads head (cần đúng 1) — dừng.\" >&2; alembic heads >&2; exit 1; fi; alembic upgrade head; exec uvicorn app.main:app --host 0.0.0.0 --port \"$PORT\" --workers \"$UVICORN_WORKERS\" --proxy-headers --forwarded-allow-ips '*' --no-server-header"]
