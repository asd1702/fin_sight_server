    ## Dockerfile
    ## Purpose: multi-stage build for FinSight 애플리케이션
    ## - builder 단계에서 빌드 종속성을 설치하고 wheel을 생성
    ## - runtime 단계에서는 런타임에 필요한 최소 패키지만 포함해 이미지 크기를 줄임
    ## Repro tips:
    ## - 빌드 시 BuildKit을 사용하면 레이어 캐시가 빨라집니다.
    ## - ENTRYPOINT는 /app/docker-entrypoint.sh를 사용합니다(권한 필요).

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
    ## Note: 이 단계는 런타임 전용으로 컴파일러를 포함하지 않습니다.
    ## 빌드 아티팩트를 wheels로부터 복사하여 설치합니다.
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

    # Create non-root user to run the app (best practice)
    RUN useradd -m -r appuser && chown -R appuser:appuser /app
    USER appuser

    EXPOSE 8000

    # (Optional) Container healthcheck (FastAPI health endpoint)
    HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
    CMD curl -f http://127.0.0.1:8000/health || exit 1

    # Entrypoint script handles DB wait, migrations, and launching uvicorn
    ENTRYPOINT ["/app/docker-entrypoint.sh"]

