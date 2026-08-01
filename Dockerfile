# ==============================================================================
# Stage 1: Build & Dependency Wheel Generator
# ==============================================================================
FROM python:3.11-slim AS builder

WORKDIR /build

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

# Install build-essential and PostgreSQL C libraries required for compiling native extensions
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    libpq-dev \
    gcc \
    curl \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .

RUN pip install --upgrade pip setuptools wheel && \
    pip wheel --no-cache-dir --wheel-dir /build/wheels -r requirements.txt

# ==============================================================================
# Stage 2: Minimal & Hardened Production Runtime
# ==============================================================================
FROM python:3.11-slim AS runtime

WORKDIR /app

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PATH="/home/appuser/.local/bin:${PATH}" \
    PYTHONPATH="/app"

# Install runtime dependencies (libpq5 for asyncpg/psycopg, curl for healthcheck)
RUN apt-get update && apt-get install -y --no-install-recommends \
    libpq5 \
    curl \
    ca-certificates \
    && rm -rf /var/lib/apt/lists/*

# Create dedicated non-root security user & group (UID/GID 10001)
RUN groupadd -g 10001 appgroup && \
    useradd -u 10001 -g appgroup -m -s /bin/bash appuser

# Copy pre-compiled python wheels from builder stage
COPY --from=builder /build/wheels /tmp/wheels
COPY --from=builder /build/requirements.txt .

# Install dependencies as appuser
RUN pip install --no-cache-dir --user /tmp/wheels/* && \
    rm -rf /tmp/wheels

# Copy application source code and migrations
COPY --chown=appuser:appgroup . /app

# Ensure proper permissions
RUN chown -R appuser:appgroup /app

USER appuser

EXPOSE 8000

# Container Healthcheck
HEALTHCHECK --interval=15s --timeout=5s --start-period=10s --retries=3 \
    CMD curl -f http://localhost:8000/health || exit 1

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "4"]
