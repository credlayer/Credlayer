FROM python:3.12.8-slim-bookworm

RUN apt-get update && \
    apt-get upgrade -y && \
    apt-get clean && \
    rm -rf /var/lib/apt/lists/*

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_NO_SYNC=1 \
    PYTHONPATH=/app/src \
    PATH="/app/.venv/bin:$PATH"

COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /usr/local/bin/

WORKDIR /app

# Dependencies only — do not install credlayer as an editable package.
# Runtime uses PYTHONPATH=/app/src so uv never writes _editable_impl_*.pth.
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-install-project --no-dev

COPY src ./src
COPY alembic.ini ./
COPY migrations ./migrations
COPY scripts ./scripts

RUN useradd --create-home --uid 1000 credlayer && \
    chown -R credlayer:credlayer /app
USER credlayer

EXPOSE 8000

# Apply migrations (idempotent), then start the server
CMD ["sh", "-c", "alembic upgrade head && exec uvicorn credlayer.main:app --host 0.0.0.0 --port ${PORT:-8000}"]
