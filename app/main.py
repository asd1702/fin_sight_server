"""
FinSight API Server의 진입점 모듈

이 파일은 FastAPI 애플리케이션 인스턴스를 생성하고 다음을 설정합니다:
 - 애플리케이션 메타데이터(title, description, version)
 - CORS 미들웨어 (프론트엔드와의 통신 허용)
 - Prometheus 계측을 위한 Instrumentator 설정 및 /metrics 노출
 - 주기적인 시스템 메트릭 수집(백그라운드 태스크)
 - API 라우터 포함(articles, health, letters)
"""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from prometheus_fastapi_instrumentator import Instrumentator
from app.api import articles, health, letters
from app.core.monitoring import log_system_metrics
import asyncio


# FastAPI 애플리케이션 생성 (메타데이터 포함)
app = FastAPI(
    title="FinSight API Server",
    description="금융 뉴스 수집 및 분석 시스템",
    version="1.0.0",
)


# ---------------------------
# CORS 설정
# ---------------------------
# 프론트엔드(로컬 개발 서버 또는 배포된 앱)에서 API에 접근할 수 있도록 허용합니다.
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:3000",
        "http://localhost:3001",
        "https://finsight-c-tctt.vercel.app",
        "https://www.finview.kr",
        "https://finview.kr",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ---------------------------
# Prometheus 계측 설정
# ---------------------------
# Instrumentator를 사용해 라우트/응답 메트릭을 수집하고 `/metrics` 엔드포인트로 노출합니다.
instrumentator = Instrumentator()
instrumentator.instrument(app)
instrumentator.expose(app, endpoint="/metrics")


# ---------------------------
# 백그라운드 시스템 모니터링
# ---------------------------
async def periodic_system_monitoring():
    """주기적으로 시스템 메트릭을 수집하는 백그라운드 태스크.

    기본 동작은 5분(300초)마다 `log_system_metrics()`를 호출합니다.
    다만 로깅 레벨이 DEBUG 이하로 설정된 경우에만 실제 메트릭을 로깅하도록
    하여 운영 환경에서는 과도한 로그를 피합니다.
    """
    while True:
        import logging

        # 로거 레벨이 DEBUG일 때만 실제 메트릭 수집/로깅 수행
        if logging.getLogger().level <= logging.DEBUG:
            # `app.core.monitoring.log_system_metrics`에 구현된 메트릭 수집 함수 호출
            log_system_metrics()

        # 5분 간격으로 반복
        await asyncio.sleep(300)


@app.on_event("startup")
async def startup_event():
    """애플리케이션 시작 시 실행되는 이벤트 핸들러.

    백그라운드 태스크(`periodic_system_monitoring`)를 비동기 태스크로 생성합니다.
    """
    # 백그라운드에서 주기적 모니터링 태스크 시작
    asyncio.create_task(periodic_system_monitoring())


# ---------------------------
# API 라우터 등록
# ---------------------------
# 각 모듈에서 정의한 라우터를 포함시켜 엔드포인트를 활성화합니다.
app.include_router(articles.router)
app.include_router(health.router)
app.include_router(letters.router)


@app.get("/")
def read_root():
    """루트 헬스 체크 엔드포인트(간단 메시지 반환)."""
    return {"message": "FinSight API Server is running."}
