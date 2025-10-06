    ## =============================
    ## Multi-stage build (smaller + faster rebuilds)
    ## =============================

    ## --- Builder stage: install dependencies into wheels layer ---
    FROM python:3.10-slim AS builder
    ENV PYTHONDONTWRITEBYTECODE=1 \
        PYTHONUNBUFFERED=1 \
        PIP_NO_CACHE_DIR=1
    WORKDIR /app

    # Build deps only here (will not be in final image)
    RUN apt-get update && apt-get install -y --no-install-recommends \
        build-essential \
        gcc \
        libpq-dev \
        curl \
        && rm -rf /var/lib/apt/lists/*

    COPY requirements.txt .
    # If BuildKit available, caching speeds up (optional hint)
    RUN pip install --upgrade pip && pip wheel --wheel-dir /wheels -r requirements.txt

    ## --- Runtime stage: minimal runtime with wheels installed ---
    FROM python:3.10-slim AS runtime
    ENV PYTHONDONTWRITEBYTECODE=1 \
        PYTHONUNBUFFERED=1 \
        PIP_NO_CACHE_DIR=1
    WORKDIR /app

    # Only runtime libs (no compilers)
    RUN apt-get update && apt-get install -y --no-install-recommends \
        libpq-dev \
        netcat-openbsd \
        curl \
        && rm -rf /var/lib/apt/lists/*

    # Copy wheels from builder and install
    COPY --from=builder /wheels /wheels
    RUN pip install --no-cache-dir /wheels/* && rm -rf /wheels

    # Copy application source
    COPY . .

    # Ensure entrypoint is executable (in case git perms lost)
    RUN chmod +x /app/docker-entrypoint.sh

    # Create non-root user
    RUN useradd -m -r appuser && chown -R appuser:appuser /app
    USER appuser

    EXPOSE 8000

    # (Optional) Container healthcheck (FastAPI health endpoint)
    HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
    CMD curl -f http://127.0.0.1:8000/health || exit 1

    ENTRYPOINT ["/app/docker-entrypoint.sh"]

