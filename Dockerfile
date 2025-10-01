# Python 3.10 기반 이미지 사용
FROM python:3.10-slim AS base

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

# 작업 디렉토리 설정
WORKDIR /app

# 시스템 패키지 업데이트 및 필요한 패키지 설치
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    g++ \
    libpq-dev \
    netcat-openbsd \
    && rm -rf /var/lib/apt/lists/*

# Python 의존성 파일 복사 및 설치
COPY requirements.txt ./
RUN pip install -r requirements.txt

# 애플리케이션 코드 복사
COPY . .

# 권한 분리를 위한 비루트 사용자 생성
RUN useradd -m appuser && chown -R appuser:appuser /app
USER appuser

# 포트 노출
EXPOSE 8000

# 애플리케이션 실행
ENTRYPOINT ["/app/docker-entrypoint.sh"]

