# Single-image build: Vite static assets and Python venv are built in separate stages,
# then copied into a lean runtime image without bun or uv.
# Build context must be the repository root.
FROM oven/bun:1-alpine AS ui-build
WORKDIR /app

COPY webui/frontend/package.json webui/frontend/bun.lock ./
RUN bun install --frozen-lockfile

COPY webui/frontend/ .
RUN bun run build

FROM python:3.14-slim AS venv-build
COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/
WORKDIR /app

ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy
COPY webui/backend/pyproject.toml webui/backend/uv.lock ./
RUN uv sync --frozen --no-dev --no-install-project --no-cache

FROM python:3.14-slim AS runner
WORKDIR /app

# Install system dependencies (OCR for PDF processing)
RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        ocrmypdf tesseract-ocr tesseract-ocr-deu tesseract-ocr-eng ghostscript \
    && rm -rf /var/lib/apt/lists/*

ENV PATH="/app/.venv/bin:$PATH"
COPY --from=venv-build /app/.venv /app/.venv

# Copy application code
COPY vendor/dfs-aip/aip.py .
COPY vendor/dfs-aip/aip/ aip/
COPY webui/backend/main.py webui/backend/db.py webui/backend/rollover.py ./
COPY --from=ui-build /app/dist static/

# Create data directories
RUN mkdir -p data output cache

EXPOSE 8000

CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000", "--proxy-headers", "--forwarded-allow-ips", "*"]
